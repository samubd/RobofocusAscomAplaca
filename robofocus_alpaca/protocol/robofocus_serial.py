"""
Real serial protocol handler for Robofocus hardware.

Implements SerialProtocolInterface using pyserial for RS-232 communication.

Architecture aligned with INDI driver (robofocus.cpp):
- NEVER send commands during movement (any serial activity stops the hardware!)
- Read one byte at a time for async chars (I/O/F)
- Buffer flush ONLY after complete response
"""

import logging
import threading
import time
from enum import Enum
from typing import List, Optional

import serial
from serial import SerialException

from robofocus_alpaca.protocol.interface import SerialProtocolInterface
from robofocus_alpaca.protocol.encoder import encode_command, parse_response
from robofocus_alpaca.protocol.checksum import validate_checksum
from robofocus_alpaca.protocol.logger import get_protocol_logger
from robofocus_alpaca.config.models import SerialConfig
from robofocus_alpaca.utils.exceptions import (
    NotConnectedError,
    PortNotFoundError,
    PortInUseError,
    HandshakeError,
    SerialTimeoutError,
    ChecksumMismatchError,
    ProtocolError,
    MaxRetriesExceededError,
    MovementInProgressError,
)


logger = logging.getLogger(__name__)


class MovementState(Enum):
    """Movement state machine aligned with INDI driver."""
    IDLE = "idle"
    MOVING_PROGRAMMATIC = "programmatic"  # Started by move_absolute()
    MOVING_EXTERNAL = "external"          # Started by handset (pulsantiera)


class RobofocusSerial(SerialProtocolInterface):
    """
    Real hardware serial protocol implementation.

    Communicates with Robofocus via RS-232 serial port using 9-byte
    command/response packets with checksum validation.

    CRITICAL: No commands are sent during movement. The hardware treats
    any serial activity as an immediate stop command.
    """

    # Serial port settings (fixed by Robofocus protocol)
    BAUD_RATE = 9600
    DATA_BITS = 8
    PARITY = serial.PARITY_NONE
    STOP_BITS = serial.STOPBITS_ONE

    # Retry settings
    MAX_RETRIES = 3
    RETRY_DELAY_MS = 500

    def __init__(self, config: SerialConfig):
        """
        Initialize serial protocol handler.

        Args:
            config: Serial port configuration.
        """
        self._config = config
        self._port: Optional[serial.Serial] = None
        self._serial_lock = threading.Lock()
        self._connected = False
        self._firmware_version: Optional[str] = None

        # Movement state machine (aligned with INDI)
        self._movement_state = MovementState.IDLE
        self._position = 0
        self._target_position = 0

        # Cached temperature (updated when idle, max age 120s)
        self._temperature_cache: Optional[float] = None
        self._temperature_cache_time: float = 0
        self._temperature_cache_max_age: float = 120.0  # seconds

    def connect(self) -> None:
        """Open serial port and validate connection with FV handshake."""
        if self._connected:
            logger.warning("Already connected")
            return

        port_name = self._config.port
        timeout = self._config.timeout_seconds

        logger.info(f"Opening serial port {port_name}")

        try:
            self._port = serial.Serial(
                port=port_name,
                baudrate=self.BAUD_RATE,
                bytesize=self.DATA_BITS,
                parity=self.PARITY,
                stopbits=self.STOP_BITS,
                timeout=timeout,
                write_timeout=timeout,
            )
        except serial.SerialException as e:
            error_msg = str(e).lower()
            if "filenotfounderror" in error_msg or "no such file" in error_msg:
                raise PortNotFoundError(f"Failed to open {port_name}: Port not found")
            elif "access" in error_msg or "permission" in error_msg or "in use" in error_msg:
                raise PortInUseError(f"{port_name} is already in use by another application")
            else:
                raise PortNotFoundError(f"Failed to open {port_name}: {e}")

        # Flush buffers
        self._port.reset_input_buffer()
        self._port.reset_output_buffer()

        # Perform FV handshake to validate hardware
        try:
            response = self._send_command_internal("FV", 0)
            parsed = parse_response(response)

            if not parsed["checksum_valid"]:
                self._port.close()
                raise HandshakeError("Hardware did not respond to FV command, wrong device?")

            # Handle both integer (002100) and float (3.2) firmware versions
            fw_value = parsed['value']
            if isinstance(fw_value, float):
                self._firmware_version = str(fw_value)
            else:
                self._firmware_version = f"{fw_value:06d}"
            self._connected = True

            # Query initial position
            pos_response = self._send_command_internal("FG", 0)
            pos_parsed = parse_response(pos_response)
            if pos_parsed["checksum_valid"] and pos_parsed["cmd"] == "FD":
                self._position = int(pos_parsed["value"])
                self._target_position = self._position

            logger.info(f"Connected to Robofocus (firmware: {self._firmware_version}, position: {self._position})")

        except (SerialTimeoutError, ProtocolError, ChecksumMismatchError) as e:
            if self._port:
                self._port.close()
            raise HandshakeError(f"Hardware did not respond to FV command: {e}")

    def disconnect(self) -> None:
        """Close serial port connection."""
        if self._port and self._port.is_open:
            self._port.close()
            logger.info("Serial port closed")

        self._connected = False
        self._port = None
        self._movement_state = MovementState.IDLE

    def is_connected(self) -> bool:
        """Check if connected to hardware."""
        return self._connected and self._port is not None and self._port.is_open

    def send_command(self, cmd: str, value: int = 0) -> bytes:
        """
        Send command with retry logic.

        CRITICAL: Commands are blocked during movement to avoid
        stopping the hardware (any serial activity = stop command).

        Raises:
            MovementInProgressError: If movement is in progress.
        """
        if not self.is_connected():
            raise NotConnectedError("Focuser not connected")

        # Block commands during PROGRAMMATIC movement (CRITICAL for hardware safety)
        # During EXTERNAL movement, allow FG queries to detect when movement ends
        if self._movement_state == MovementState.MOVING_PROGRAMMATIC:
            raise MovementInProgressError(
                f"Cannot send {cmd} command during programmatic movement"
            )
        if self._movement_state == MovementState.MOVING_EXTERNAL and cmd not in ("FG", "FQ"):
            raise MovementInProgressError(
                f"Cannot send {cmd} command during external movement (only FG/FQ allowed)"
            )

        last_exception = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                result = self._send_command_internal(cmd, value)
                # If None, external movement detected - return None (not an error)
                if result is None:
                    return None
                return result
            except (SerialTimeoutError, ChecksumMismatchError) as e:
                last_exception = e
                if attempt < self.MAX_RETRIES:
                    logger.warning(f"Command {cmd} retry: attempt {attempt}/{self.MAX_RETRIES}")
                    time.sleep(self.RETRY_DELAY_MS / 1000.0)
                    # Flush buffers before retry
                    if self._port:
                        self._port.reset_input_buffer()
                        self._port.reset_output_buffer()

        raise MaxRetriesExceededError(f"{cmd} command failed after {self.MAX_RETRIES} attempts: {last_exception}")

    def _send_command_internal(self, cmd: str, value: int) -> bytes:
        """Send command and read response (internal, no retry)."""
        protocol_logger = get_protocol_logger()

        with self._serial_lock:
            if not self._port or not self._port.is_open:
                raise NotConnectedError("Serial port not open")

            # Only flush output buffer, NOT input buffer
            # (input buffer is flushed AFTER receiving complete response)
            self._port.reset_output_buffer()

            # Encode and send command
            packet = encode_command(cmd, value)

            if logger.isEnabledFor(logging.DEBUG):
                hex_str = " ".join(f"{b:02X}" for b in packet)
                logger.debug(f"TX: {hex_str}")

            # Log TX to protocol logger
            protocol_logger.log_tx(packet, cmd, value)

            self._port.write(packet)
            self._port.flush()

            # Read response
            response = self._read_response(cmd, protocol_logger)

            # If None, external movement is in progress - return None
            # (state already set to MOVING_EXTERNAL by _read_response)
            if response is None:
                return None

            # Log RX to protocol logger (already logged in _read_response for 'F' packets)
            # protocol_logger.log_rx(response)  # Don't double-log

            if logger.isEnabledFor(logging.DEBUG):
                hex_str = " ".join(f"{b:02X}" for b in response)
                logger.debug(f"RX: {hex_str}")

            # Validate checksum
            if not validate_checksum(response):
                raise ChecksumMismatchError(f"Checksum mismatch for {cmd} response")

            return response

    def _read_response(self, cmd: str, protocol_logger) -> bytes:
        """
        Read 9-byte response packet with immediate external movement detection.

        When external movement (handset) is detected:
        1. Set movement_state to MOVING_EXTERNAL IMMEDIATELY
        2. Return None RIGHT AWAY so UI can see is_moving=true
        3. Subsequent polls will continue reading until 'F' arrives

        Args:
            cmd: Command being executed (for error messages)
            protocol_logger: Protocol logger for logging

        Returns:
            9-byte response packet starting with 'F', or None if external movement detected

        Raises:
            SerialTimeoutError: When no response received (idle timeout)
            ProtocolError: When invalid data received
        """
        original_timeout = self._port.timeout
        self._port.timeout = self._config.timeout_seconds

        try:
            while True:
                byte_data = self._port.read(1)

                if len(byte_data) == 0:
                    # Timeout - no data
                    if self._movement_state == MovementState.MOVING_EXTERNAL:
                        # We're in external movement mode but no data - maybe user released
                        # Keep state and return None, next poll will check again
                        return None
                    else:
                        protocol_logger.log_error(f"Timeout: no response to {cmd}", b"")
                        raise SerialTimeoutError(f"No response to {cmd} command")

                char = chr(byte_data[0])

                if char == 'I':  # Inward movement
                    protocol_logger.log_rx(byte_data)
                    logger.info("External movement detected (inward)")

                    # Set state IMMEDIATELY so UI sees is_moving=true
                    self._movement_state = MovementState.MOVING_EXTERNAL

                    # Start background thread to wait for 'F' packet
                    # This releases the lock so API calls can continue
                    self._port.timeout = original_timeout
                    threading.Thread(target=self._monitor_external_movement, daemon=True).start()

                    return None  # Return immediately

                elif char == 'O':  # Outward movement
                    protocol_logger.log_rx(byte_data)
                    logger.info("External movement detected (outward)")

                    # Set state IMMEDIATELY so UI sees is_moving=true
                    self._movement_state = MovementState.MOVING_EXTERNAL

                    # Start background thread to wait for 'F' packet
                    self._port.timeout = original_timeout
                    threading.Thread(target=self._monitor_external_movement, daemon=True).start()

                    return None  # Return immediately

                elif char == 'F':  # Start of response packet
                    remaining = self._port.read(8)

                    if len(remaining) < 8:
                        protocol_logger.log_error(
                            f"Incomplete response: {1+len(remaining)}/9 bytes",
                            byte_data + remaining
                        )
                        raise ProtocolError(f"Incomplete response: received {1+len(remaining)}/9 bytes")

                    response = byte_data + remaining
                    protocol_logger.log_rx(response)

                    parsed = parse_response(response)
                    if parsed["cmd"] == "FD" and parsed["checksum_valid"]:
                        new_pos = int(parsed["value"])
                        if self._movement_state == MovementState.MOVING_EXTERNAL:
                            logger.info(f"External movement finished at position {new_pos}")
                        self._position = new_pos

                    # Movement finished
                    self._movement_state = MovementState.IDLE
                    self._port.reset_input_buffer()

                    return bytes(response)

                else:
                    logger.warning(f"Unexpected byte: 0x{byte_data[0]:02X}")
                    protocol_logger.log_rx(byte_data)
                    continue

        finally:
            self._port.timeout = original_timeout

    def wait_for_movement_end(self, timeout: float = 300.0) -> int:
        """
        Wait for movement to finish, reading async chars.

        Blocking method that reads one byte at a time (like INDI ReadResponse):
        - 'I' = inward movement, update position
        - 'O' = outward movement, update position
        - 'F' = start of response packet, read remaining 8 bytes

        This method should be called in a background thread during movement.

        Args:
            timeout: Maximum time to wait for movement to finish (default 5 min)

        Returns:
            Final position from FD packet

        Raises:
            SerialTimeoutError: If movement doesn't finish within timeout
            ProtocolError: If invalid data received
        """
        if not self.is_connected():
            raise NotConnectedError("Focuser not connected")

        protocol_logger = get_protocol_logger()
        start_time = time.time()
        last_char_time = time.time()
        motion_logged = False

        logger.debug(f"Waiting for movement to end (timeout: {timeout}s)")

        with self._serial_lock:
            # Set short timeout for individual reads
            original_timeout = self._port.timeout
            self._port.timeout = 0.5  # 500ms per-byte timeout

            try:
                while True:
                    elapsed = time.time() - start_time
                    if elapsed > timeout:
                        self._movement_state = MovementState.IDLE
                        protocol_logger.log_error(f"Movement timeout after {elapsed:.1f}s", b"")
                        raise SerialTimeoutError(f"Movement did not complete within {timeout} seconds")

                    # Check for stall (no chars for 3 seconds)
                    if time.time() - last_char_time > 3.0:
                        logger.warning("Movement stall detected (no async chars for 3s)")
                        # Try to recover by reading position
                        self._movement_state = MovementState.IDLE
                        self._port.reset_input_buffer()
                        return self._position

                    byte = self._port.read(1)

                    if len(byte) == 0:
                        # Timeout on single byte read - continue waiting
                        continue

                    last_char_time = time.time()
                    char = chr(byte[0])

                    if char == 'I':
                        # Inward movement - log raw byte
                        protocol_logger.log_rx(byte)
                        self._position = max(0, self._position - 1)
                        if not motion_logged:
                            logger.info("Moving inward...")
                            motion_logged = True

                    elif char == 'O':
                        # Outward movement - log raw byte
                        protocol_logger.log_rx(byte)
                        self._position += 1
                        if not motion_logged:
                            logger.info("Moving outward...")
                            motion_logged = True

                    elif char == 'F':
                        # Start of response packet - read remaining 8 bytes
                        remaining = self._port.read(8)

                        if len(remaining) < 8:
                            logger.warning(f"Incomplete response after 'F': {1+len(remaining)}/9 bytes")
                            # Try to continue
                            continue

                        response = byte + remaining
                        protocol_logger.log_rx(response)

                        if logger.isEnabledFor(logging.DEBUG):
                            hex_str = " ".join(f"{b:02X}" for b in response)
                            logger.debug(f"RX: {hex_str}")

                        parsed = parse_response(response)

                        if parsed["cmd"] == "FD" and parsed["checksum_valid"]:
                            self._position = int(parsed["value"])
                            logger.info(f"Movement finished at position {self._position}")
                        else:
                            logger.warning(f"Unexpected response during movement: {parsed['cmd']}")

                        # Movement finished - flush and return
                        self._port.reset_input_buffer()
                        self._movement_state = MovementState.IDLE
                        return self._position

                    else:
                        # Unexpected character - log and continue
                        logger.debug(f"Unexpected byte during movement: 0x{byte[0]:02X}")

            finally:
                # Restore original timeout
                self._port.timeout = original_timeout

    def get_position(self) -> int:
        """
        Get current focuser position.

        During ANY movement (programmatic or external), returns cached position.
        Background thread monitors external movement and updates position when done.

        When IDLE, sends FG query.
        """
        if not self.is_connected():
            raise NotConnectedError("Focuser not connected")

        # During ANY movement, return cached position immediately
        # Background thread will update position when movement ends
        if self._movement_state != MovementState.IDLE:
            return self._position

        # IDLE: Query hardware
        response = self.send_command("FG", 0)

        # If response is None, external movement was just detected
        # Background thread is now monitoring, return cached position
        if response is None:
            return self._position

        parsed = parse_response(response)

        if parsed["cmd"] == "FD":
            self._position = int(parsed["value"])
            return self._position
        else:
            logger.warning(f"Unexpected response to FG query: {parsed['cmd']}")
            return self._position

    def _start_external_movement_monitor(self) -> None:
        """
        Start background thread to monitor external movement and wait for 'F' packet.
        Called when I/O char is detected during FG query.
        """
        if hasattr(self, '_external_monitor_thread') and self._external_monitor_thread and self._external_monitor_thread.is_alive():
            return  # Already running

        self._external_monitor_thread = threading.Thread(
            target=self._monitor_external_movement,
            daemon=True
        )
        self._external_monitor_thread.start()

    def _monitor_external_movement(self) -> None:
        """
        Background thread that reads serial buffer waiting for 'F' packet.
        Runs until 'F' is received or timeout.
        """
        protocol_logger = get_protocol_logger()
        start_time = time.time()
        timeout = 60.0  # Max 60 seconds for external movement

        logger.debug("External movement monitor thread started")

        with self._serial_lock:
            if not self._port or not self._port.is_open:
                self._movement_state = MovementState.IDLE
                return

            original_timeout = self._port.timeout
            self._port.timeout = 0.5  # 500ms per read

            try:
                while time.time() - start_time < timeout:
                    if self._movement_state != MovementState.MOVING_EXTERNAL:
                        # State changed externally, stop monitoring
                        break

                    byte_data = self._port.read(1)

                    if len(byte_data) == 0:
                        # No data - keep waiting
                        continue

                    char = chr(byte_data[0])

                    if char in ('I', 'O'):
                        protocol_logger.log_rx(byte_data)
                        continue

                    elif char == 'F':
                        remaining = self._port.read(8)

                        if len(remaining) == 8:
                            response = byte_data + remaining
                            protocol_logger.log_rx(response)

                            parsed = parse_response(response)
                            if parsed["cmd"] == "FD" and parsed["checksum_valid"]:
                                self._position = int(parsed["value"])
                                logger.info(f"External movement finished at position {self._position}")

                            self._movement_state = MovementState.IDLE
                            self._port.reset_input_buffer()
                            return
                        else:
                            logger.warning("Incomplete 'F' packet in monitor")

                    else:
                        protocol_logger.log_rx(byte_data)

                # Timeout
                logger.warning("External movement monitor timeout, resetting to IDLE")
                self._movement_state = MovementState.IDLE
                self._port.reset_input_buffer()

            finally:
                self._port.timeout = original_timeout
                logger.debug("External movement monitor thread finished")

    def move_absolute(self, target: int) -> None:
        """Start movement to absolute position (non-blocking)."""
        if not self.is_connected():
            raise NotConnectedError("Focuser not connected")

        if self._movement_state != MovementState.IDLE:
            raise MovementInProgressError(f"Cannot start move during {self._movement_state.value} movement")

        self._target_position = target
        self._movement_state = MovementState.MOVING_PROGRAMMATIC

        logger.info(f"Moving to position {target}")

        protocol_logger = get_protocol_logger()

        with self._serial_lock:
            if not self._port or not self._port.is_open:
                self._movement_state = MovementState.IDLE
                raise NotConnectedError("Serial port not open")

            # Flush buffers before sending move command
            self._port.reset_input_buffer()
            self._port.reset_output_buffer()

            # Encode and send command
            packet = encode_command("FG", target)

            if logger.isEnabledFor(logging.DEBUG):
                hex_str = " ".join(f"{b:02X}" for b in packet)
                logger.debug(f"TX: {hex_str}")

            # Log TX to protocol logger
            protocol_logger.log_tx(packet, "FG", target)

            self._port.write(packet)
            self._port.flush()

        logger.debug(f"Move command sent to position {target}")

    def halt(self) -> None:
        """
        Stop movement immediately.

        Can be called during movement (this is the only command allowed).
        """
        if not self.is_connected():
            raise NotConnectedError("Focuser not connected")

        logger.info("Halting movement")

        protocol_logger = get_protocol_logger()

        # Halt is special - allowed during movement
        with self._serial_lock:
            if not self._port or not self._port.is_open:
                raise NotConnectedError("Serial port not open")

            # Flush and send halt command
            self._port.reset_input_buffer()
            self._port.reset_output_buffer()

            packet = encode_command("FQ", 0)
            protocol_logger.log_tx(packet, "FQ", 0)

            self._port.write(packet)
            self._port.flush()

            # Wait briefly for hardware to stop
            time.sleep(0.2)

            # Read response (might include leftover I/O chars)
            self._port.reset_input_buffer()

        self._movement_state = MovementState.IDLE
        logger.info("Halt command sent")

    def get_temperature(self) -> float:
        """
        Read temperature sensor in Celsius.

        During movement, returns cached value (NO command sent!).
        """
        if not self.is_connected():
            raise NotConnectedError("Focuser not connected")

        current_time = time.time()
        cache_age = current_time - self._temperature_cache_time

        # During movement, ALWAYS return cached value
        if self._movement_state != MovementState.IDLE:
            if self._temperature_cache is not None:
                logger.debug(f"Temperature during movement (cached, age {cache_age:.0f}s): {self._temperature_cache:.2f}°C")
                return self._temperature_cache
            # No cached value available - return a default
            logger.warning("No cached temperature available during movement, returning 20.0°C")
            return 20.0

        # When idle, check cache validity
        if self._temperature_cache is not None and cache_age < self._temperature_cache_max_age:
            logger.debug(f"Temperature (cached, age {cache_age:.0f}s): {self._temperature_cache:.2f}°C")
            return self._temperature_cache

        # Query hardware for fresh temperature
        response = self.send_command("FT", 0)
        parsed = parse_response(response)

        if parsed["cmd"] != "FT":
            logger.warning(f"Unexpected response to FT: {parsed['cmd']}")

        raw_adc = int(parsed["value"])

        # Check for sensor error
        if raw_adc < 200 or raw_adc > 1000:
            from robofocus_alpaca.utils.exceptions import SensorError
            raise SensorError("Temperature sensor not responding")

        # Convert: Celsius = (raw - 380) / 10
        # Empirically calibrated for firmware 3.2
        celsius = (raw_adc - 380) / 10.0

        # Cache the temperature
        self._temperature_cache = celsius
        self._temperature_cache_time = current_time

        logger.info(f"Temperature: {celsius:.2f}°C (raw ADC: {raw_adc})")
        return celsius

    def is_moving(self) -> bool:
        """Check if focuser is currently moving."""
        return self._movement_state != MovementState.IDLE

    def get_backlash(self) -> tuple[int, int]:
        """
        Read current backlash compensation settings.

        During movement, raises MovementInProgressError.

        Returns:
            Tuple of (direction, amount):
            - direction: 2 = compensation on IN motion, 3 = compensation on OUT motion
            - amount: backlash steps (1-255)
        """
        if not self.is_connected():
            raise NotConnectedError("Focuser not connected")

        if self._movement_state != MovementState.IDLE:
            raise MovementInProgressError("Cannot query backlash during movement")

        # Send FB with 0 to read current settings
        response = self.send_command("FB", 0)
        parsed = parse_response(response)

        if parsed["cmd"] != "FB":
            logger.warning(f"Unexpected response to FB: {parsed['cmd']}")
            return (2, 0)  # Default: IN direction, 0 steps

        # Response format: FB N XXXXX (N=direction, XXXXX=amount)
        raw_value = int(parsed["value"])

        # First digit is direction (2 or 3), rest is amount
        direction = raw_value // 100000
        amount = raw_value % 100000

        logger.debug(f"Backlash settings: direction={direction}, amount={amount}")
        return (direction, amount)

    def set_backlash(self, direction: int, amount: int) -> None:
        """
        Set backlash compensation.

        Args:
            direction: 2 = compensation on IN motion, 3 = compensation on OUT motion
            amount: backlash steps (0-255, 0 disables)
        """
        if not self.is_connected():
            raise NotConnectedError("Focuser not connected")

        if self._movement_state != MovementState.IDLE:
            raise MovementInProgressError("Cannot set backlash during movement")

        if direction not in (2, 3):
            raise ValueError(f"Invalid backlash direction: {direction}. Must be 2 (IN) or 3 (OUT)")

        if amount < 0 or amount > 255:
            raise ValueError(f"Backlash amount must be 0-255, got {amount}")

        # Format: N followed by 5-digit amount
        value = direction * 100000 + amount

        logger.info(f"Setting backlash: direction={direction} ({'IN' if direction == 2 else 'OUT'}), amount={amount}")

        response = self.send_command("FB", value)
        parsed = parse_response(response)

        if parsed["cmd"] != "FB":
            logger.warning(f"Unexpected response to FB set: {parsed['cmd']}")

    def get_max_travel(self) -> int:
        """
        Read maximum travel limit from hardware.

        Returns:
            Max position stored in Robofocus hardware.
        """
        if not self.is_connected():
            raise NotConnectedError("Focuser not connected")

        if self._movement_state != MovementState.IDLE:
            raise MovementInProgressError("Cannot query max travel during movement")

        response = self.send_command("FL", 0)
        parsed = parse_response(response)

        if parsed["cmd"] != "FL":
            logger.warning(f"Unexpected response to FL: {parsed['cmd']}")
            return 65535  # Default max

        raw_value = int(parsed["value"])
        max_travel = raw_value % 100000

        logger.debug(f"Hardware max travel: {max_travel}")
        return max_travel

    def set_max_travel(self, value: int) -> None:
        """
        Write maximum travel limit to hardware.

        Args:
            value: Max position to store in Robofocus hardware (1-65535).
        """
        if not self.is_connected():
            raise NotConnectedError("Focuser not connected")

        if self._movement_state != MovementState.IDLE:
            raise MovementInProgressError("Cannot set max travel during movement")

        if value < 1 or value > 65535:
            raise ValueError(f"Max travel must be 1-65535, got {value}")

        logger.info(f"Setting hardware max travel to {value}")

        response = self.send_command("FL", value)
        parsed = parse_response(response)

        if parsed["cmd"] != "FL":
            logger.warning(f"Unexpected response to FL set: {parsed['cmd']}")

    def sync_position(self, value: int) -> None:
        """
        Sync/set the hardware position counter to a specific value.

        This does NOT move the focuser - it sets the internal counter.
        Used for calibration (e.g., "Set as Zero").

        Note: FS000000 and FS000001 return current position instead of setting it.
        Values 0 or 1 are automatically converted to 2.

        Args:
            value: Position value to set (0-999999).
        """
        if not self.is_connected():
            raise NotConnectedError("Focuser not connected")

        if self._movement_state != MovementState.IDLE:
            raise MovementInProgressError("Cannot sync position during movement")

        if value < 0 or value > 999999:
            raise ValueError(f"Position must be 0-999999, got {value}")

        # FS000000 and FS000001 return current position instead of setting it
        # Use 2 as minimum value for hardware calibration
        hw_value = value if value >= 2 else 2

        logger.info(f"Syncing hardware position to {hw_value}" + (f" (requested {value})" if hw_value != value else ""))

        response = self.send_command("FS", hw_value)
        parsed = parse_response(response)

        if parsed["cmd"] != "FS":
            logger.warning(f"Unexpected response to FS: {parsed['cmd']}")

        # Update cached position with actual hardware value
        self._position_cache = hw_value

    def read_async_chars(self) -> List[str]:
        """
        Read asynchronous status characters without blocking.

        DEPRECATED: With the new architecture, async chars are read internally
        by wait_for_movement_end(). This method exists only for interface
        compatibility and returns an empty list.

        Returns:
            Empty list (async chars handled internally).
        """
        return []

    @property
    def firmware_version(self) -> Optional[str]:
        """Get firmware version (set after connect)."""
        return self._firmware_version

    @property
    def port_name(self) -> str:
        """Get configured port name."""
        return self._config.port

    # Legacy property for compatibility
    @property
    def _is_moving_flag(self) -> bool:
        """Legacy property for backward compatibility with controller."""
        return self._movement_state != MovementState.IDLE

    @_is_moving_flag.setter
    def _is_moving_flag(self, value: bool) -> None:
        """Legacy setter - sets state to IDLE if False."""
        if not value:
            self._movement_state = MovementState.IDLE
