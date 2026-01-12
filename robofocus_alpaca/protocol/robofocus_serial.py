"""
Real serial protocol handler for Robofocus hardware.

Implements SerialProtocolInterface using pyserial for RS-232 communication.
"""

import logging
import threading
import time
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
)


logger = logging.getLogger(__name__)


class RobofocusSerial(SerialProtocolInterface):
    """
    Real hardware serial protocol implementation.

    Communicates with Robofocus via RS-232 serial port using 9-byte
    command/response packets with checksum validation.
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

        # Movement state
        self._position = 0
        self._target_position = 0
        self._is_moving_flag = False

        # Cached temperature (updated when idle, max age 120s)
        self._temperature_cache: Optional[float] = None
        self._temperature_cache_time: float = 0
        self._temperature_cache_max_age: float = 120.0  # seconds

        # Buffer for async characters
        self._async_buffer: List[str] = []

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

    def is_connected(self) -> bool:
        """Check if connected to hardware."""
        return self._connected and self._port is not None and self._port.is_open

    def send_command(self, cmd: str, value: int = 0) -> bytes:
        """Send command with retry logic."""
        if not self.is_connected():
            raise NotConnectedError("Focuser not connected")

        last_exception = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                return self._send_command_internal(cmd, value)
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

            # Flush buffers
            self._port.reset_input_buffer()
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

            # Read response with async character handling
            # Robofocus sends 'I'/'O' during manual movement, we need to skip them
            response = self._read_response_with_sync(cmd, protocol_logger)

            # Log RX to protocol logger
            protocol_logger.log_rx(response)

            if logger.isEnabledFor(logging.DEBUG):
                hex_str = " ".join(f"{b:02X}" for b in response)
                logger.debug(f"RX: {hex_str}")

            # Validate checksum
            if not validate_checksum(response):
                parsed = parse_response(response)
                raise ChecksumMismatchError(
                    f"Checksum mismatch for {cmd} response"
                )

            return response

    def _read_response_with_sync(self, cmd: str, protocol_logger) -> bytes:
        """
        Read 9-byte response, skipping async movement characters.

        During manual movement, Robofocus sends 'I' (inward) or 'O' (outward)
        characters. We need to skip these and synchronize on 'F' which starts
        all valid response packets.

        Args:
            cmd: Command being executed (for error messages)
            protocol_logger: Protocol logger for error logging

        Returns:
            9-byte response packet starting with 'F'
        """
        response = bytearray()
        async_chars_skipped = 0
        max_async_chars = 100  # Safety limit

        # Phase 1: Find the 'F' start byte, skipping async chars
        while True:
            byte = self._port.read(1)

            if len(byte) == 0:
                if async_chars_skipped > 0:
                    logger.debug(f"Skipped {async_chars_skipped} async chars before timeout")
                protocol_logger.log_error(f"Timeout: no response to {cmd}", bytes(response))
                raise SerialTimeoutError(f"No response to {cmd} command within {self._config.timeout_seconds} seconds")

            char = chr(byte[0])

            if char == 'F':
                # Found packet start
                response.append(byte[0])
                break
            elif char in ('I', 'O'):
                # Skip async movement character
                async_chars_skipped += 1
                # Update position estimate for async movement
                if char == 'I':
                    self._position = max(0, self._position - 1)
                elif char == 'O':
                    self._position += 1

                if async_chars_skipped > max_async_chars:
                    protocol_logger.log_error(f"Too many async chars ({async_chars_skipped})", b"")
                    raise ProtocolError(f"Received {async_chars_skipped} async chars without valid response")
            else:
                # Unexpected character - might be partial packet, try to recover
                logger.warning(f"Unexpected byte while waiting for 'F': 0x{byte[0]:02X} ('{char}')")
                async_chars_skipped += 1

                if async_chars_skipped > max_async_chars:
                    protocol_logger.log_error(f"Too many unexpected chars", b"")
                    raise ProtocolError(f"Cannot synchronize: too many unexpected characters")

        if async_chars_skipped > 0:
            logger.debug(f"Skipped {async_chars_skipped} async chars before response")
            # Log to protocol logger for visibility in web UI
            protocol_logger.log_rx(f"[Skipped {async_chars_skipped} async movement chars (I/O)]".encode())

        # Phase 2: Read remaining 8 bytes of the packet
        remaining = self._port.read(8)

        if len(remaining) < 8:
            protocol_logger.log_error(f"Incomplete response: {len(remaining)+1}/9 bytes", bytes(response) + remaining)
            raise ProtocolError(f"Incomplete response: received {len(remaining)+1}/9 bytes")

        response.extend(remaining)

        return bytes(response)

    def read_async_chars(self) -> List[str]:
        """Read asynchronous status characters (I/O/F) without blocking."""
        if not self.is_connected():
            return []

        chars = []

        with self._serial_lock:
            if not self._port:
                return []

            # Read available bytes without blocking
            available = self._port.in_waiting
            if available > 0:
                data = self._port.read(available)
                for byte in data:
                    char = chr(byte)
                    if char in ('I', 'O', 'F'):
                        chars.append(char)
                        # Update position estimate
                        if char == 'I':
                            self._position = max(0, self._position - 1)
                        elif char == 'O':
                            self._position += 1
                        elif char == 'F':
                            # Movement finished - next 8 bytes are position packet
                            self._is_moving_flag = False
                    elif logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"Unexpected character: 0x{byte:02X}")

        return chars

    def get_position(self) -> int:
        """Get current focuser position."""
        if not self.is_connected():
            raise NotConnectedError("Focuser not connected")

        # If moving, return cached position (updated by async chars)
        if self._is_moving_flag:
            return self._position

        # Query hardware
        response = self.send_command("FG", 0)
        parsed = parse_response(response)

        if parsed["cmd"] == "FD":
            self._position = int(parsed["value"])
            return self._position
        else:
            logger.warning(f"Unexpected response to FG query: {parsed['cmd']}")
            return self._position

    def move_absolute(self, target: int) -> None:
        """Start movement to absolute position (non-blocking)."""
        if not self.is_connected():
            raise NotConnectedError("Focuser not connected")

        self._target_position = target
        self._is_moving_flag = True

        logger.info(f"Moving to position {target}")

        protocol_logger = get_protocol_logger()

        # Send move command without waiting for response
        # Robofocus immediately starts sending I/O/F chars during movement
        with self._serial_lock:
            if not self._port or not self._port.is_open:
                raise NotConnectedError("Serial port not open")

            # Flush buffers before sending
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
        """Stop movement immediately."""
        if not self.is_connected():
            raise NotConnectedError("Focuser not connected")

        logger.info("Halting movement")

        try:
            response = self.send_command("FQ", 0)
            self._is_moving_flag = False

            # Query final position
            pos_response = self.send_command("FG", 0)
            parsed = parse_response(pos_response)
            if parsed["cmd"] == "FD":
                self._position = int(parsed["value"])
                logger.info(f"Halted at position {self._position}")
        except Exception as e:
            logger.error(f"Error during halt: {e}")
            self._is_moving_flag = False

    def get_temperature(self) -> float:
        """Read temperature sensor in Celsius."""
        if not self.is_connected():
            raise NotConnectedError("Focuser not connected")

        current_time = time.time()
        cache_age = current_time - self._temperature_cache_time

        # Return cached temperature if:
        # 1. During movement (to avoid interfering with async chars)
        # 2. Cache is still valid (less than max age)
        if self._temperature_cache is not None:
            if self._is_moving_flag or cache_age < self._temperature_cache_max_age:
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
        return self._is_moving_flag

    def get_backlash(self) -> tuple[int, int]:
        """
        Read current backlash compensation settings.

        Returns:
            Tuple of (direction, amount):
            - direction: 2 = compensation on IN motion, 3 = compensation on OUT motion
            - amount: backlash steps (1-255)
        """
        if not self.is_connected():
            raise NotConnectedError("Focuser not connected")

        # Send FB with 0 to read current settings
        response = self.send_command("FB", 0)
        parsed = parse_response(response)

        if parsed["cmd"] != "FB":
            logger.warning(f"Unexpected response to FB: {parsed['cmd']}")
            return (2, 0)  # Default: IN direction, 0 steps

        # Response format: FB N XXXXX (N=direction, XXXXX=amount)
        # Parse the raw value which contains direction and amount
        raw_value = int(parsed["value"])

        # First digit is direction (2 or 3), rest is amount
        # e.g., 200020 = direction 2, amount 20
        direction = raw_value // 100000  # First digit
        amount = raw_value % 100000  # Remaining digits

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

        if direction not in (2, 3):
            raise ValueError(f"Invalid backlash direction: {direction}. Must be 2 (IN) or 3 (OUT)")

        if amount < 0 or amount > 255:
            raise ValueError(f"Backlash amount must be 0-255, got {amount}")

        # Format: N followed by 5-digit amount (e.g., 300020 = OUT, 20 steps)
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

        response = self.send_command("FL", 0)
        parsed = parse_response(response)

        if parsed["cmd"] != "FL":
            logger.warning(f"Unexpected response to FL: {parsed['cmd']}")
            return 65535  # Default max

        # Response format: FL 0 XXXXX (first digit is flag, rest is value)
        raw_value = int(parsed["value"])
        max_travel = raw_value % 100000  # Remove first digit flag

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

        if value < 1 or value > 65535:
            raise ValueError(f"Max travel must be 1-65535, got {value}")

        logger.info(f"Setting hardware max travel to {value}")

        response = self.send_command("FL", value)
        parsed = parse_response(response)

        if parsed["cmd"] != "FL":
            logger.warning(f"Unexpected response to FL set: {parsed['cmd']}")

    @property
    def firmware_version(self) -> Optional[str]:
        """Get firmware version (set after connect)."""
        return self._firmware_version

    @property
    def port_name(self) -> str:
        """Get configured port name."""
        return self._config.port
