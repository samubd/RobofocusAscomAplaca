"""
Mock serial protocol for hardware simulator.

Simulates Robofocus hardware without requiring physical device.
"""

import threading
import time
import random
import logging
from typing import List, Optional
from datetime import datetime

from robofocus_alpaca.protocol.interface import SerialProtocolInterface
from robofocus_alpaca.protocol.encoder import encode_command, parse_response
from robofocus_alpaca.protocol.checksum import calculate_checksum
from robofocus_alpaca.protocol.logger import get_protocol_logger
from robofocus_alpaca.config.models import SimulatorConfig
from robofocus_alpaca.utils.exceptions import (
    NotConnectedError,
    InvalidValueError,
    SensorError,
    ChecksumMismatchError,
)


logger = logging.getLogger(__name__)


class MockSerialProtocol(SerialProtocolInterface):
    """
    Mock implementation of serial protocol for testing without hardware.
    """

    def __init__(self, config: SimulatorConfig):
        """
        Initialize simulator.

        Args:
            config: Simulator configuration.
        """
        self.config = config
        self._connected = False
        self._lock = threading.Lock()

        # Virtual hardware state
        self._position = config.initial_position
        self._target_position = config.initial_position
        self._is_moving = False
        self._firmware_version = config.firmware_version

        # Backlash configuration
        self._backlash_mode = 1  # 1=off, 2=inward, 3=outward
        self._backlash_amount = 0

        # Limits
        self._max_limit = 60000
        self._min_limit = 0

        # Motor configuration
        self._motor_duty = 5
        self._motor_delay = 2
        self._motor_ticks = 3

        # Power switches (1=off, 2=on)
        self._switches = [1, 1, 1, 1]  # All off initially

        # Movement simulation
        self._movement_thread: Optional[threading.Thread] = None
        self._stop_movement = threading.Event()
        self._async_chars: List[str] = []
        self._async_chars_lock = threading.Lock()

        # Temperature simulation
        self._start_time = datetime.now()

        logger.info("MockSerialProtocol initialized")

    def connect(self) -> None:
        """Open simulated connection."""
        with self._lock:
            if self._connected:
                logger.warning("Already connected")
                return

            # Simulate connection delay
            if self.config.response_latency_ms > 0:
                time.sleep(self.config.response_latency_ms / 1000.0)

            self._connected = True
            logger.info("Simulator connected (firmware version: %s)", self._firmware_version)

    def disconnect(self) -> None:
        """Close simulated connection."""
        with self._lock:
            if not self._connected:
                return

            # Stop any ongoing movement
            if self._is_moving:
                self._stop_movement.set()
                if self._movement_thread:
                    self._movement_thread.join(timeout=2.0)

            self._connected = False
            logger.info("Simulator disconnected")

    def is_connected(self) -> bool:
        """Check connection status."""
        return self._connected

    def send_command(self, cmd: str, value: int = 0) -> bytes:
        """
        Send command to simulator.

        Args:
            cmd: Command code (FV, FG, FT, etc.).
            value: Command value.

        Returns:
            9-byte response packet.

        Raises:
            NotConnectedError: If not connected.
        """
        if not self._connected:
            raise NotConnectedError("Simulator not connected")

        protocol_logger = get_protocol_logger()

        # Log TX
        tx_packet = encode_command(cmd, value)
        protocol_logger.log_tx(tx_packet, cmd, value)

        # Simulate latency
        if self.config.response_latency_ms > 0:
            time.sleep(self.config.response_latency_ms / 1000.0)

        # Inject timeout error
        if self.config.inject_timeout:
            logger.warning("[SIMULATOR] Injected timeout for testing")
            protocol_logger.log_error("Simulated timeout")
            time.sleep(10)  # Simulate timeout

        # Route to appropriate handler
        with self._lock:
            if cmd == "FV":
                response = self._handle_fv()
            elif cmd == "FG":
                response = self._handle_fg(value)
            elif cmd == "FT":
                response = self._handle_ft()
            elif cmd == "FQ":
                response = self._handle_fq()
            elif cmd == "FB":
                response = self._handle_fb(value)
            elif cmd == "FL":
                response = self._handle_fl(value)
            elif cmd == "FC":
                response = self._handle_fc(value)
            elif cmd == "FP":
                response = self._handle_fp(value)
            elif cmd == "FS":
                response = self._handle_fs(value)
            elif cmd == "FI":
                response = self._handle_fi(value)
            elif cmd == "FO":
                response = self._handle_fo(value)
            else:
                # Unknown command, echo back
                logger.warning("Unknown command: %s", cmd)
                response = encode_command(cmd, value)

        # Inject checksum error
        if random.random() < self.config.inject_checksum_error_rate:
            logger.warning("[SIMULATOR] Injected checksum error for testing")
            response = response[:8] + bytes([random.randint(0, 255)])

        # Log RX
        if response:
            protocol_logger.log_rx(response)

        logger.debug("[SIMULATOR] TX: %s -> RX: %s",
                     tx_packet.hex(), response.hex() if response else "empty")

        return response

    def _handle_fv(self) -> bytes:
        """Handle FV (Get Version) command."""
        return encode_command("FV", int(self._firmware_version))

    def _handle_fg(self, value: int) -> bytes:
        """
        Handle FG command (Move or Query Position).

        If value == 0: Query current position (return FD packet)
        Else: Start movement to value (return FD with target)
        """
        if value == 0:
            # Query mode
            return encode_command("FD", self._position)
        else:
            # Movement mode
            self._target_position = min(value, self._max_limit)
            if self._target_position != value:
                logger.warning("Position clamped: %d -> %d", value, self._target_position)

            if self._target_position == self._position:
                # Already at target
                logger.info("Already at target position: %d", self._position)
                return encode_command("FD", self._position)

            # Start movement in background
            self._start_movement(self._target_position)

            return encode_command("FD", self._target_position)

    def _handle_ft(self) -> bytes:
        """Handle FT (Get Temperature) command."""
        temp_celsius = self._get_simulated_temperature()
        # Convert to raw ADC: (celsius + 273.15) * 2
        raw_adc = int((temp_celsius + 273.15) * 2.0)
        return encode_command("FT", raw_adc)

    def _handle_fq(self) -> bytes:
        """Handle FQ (Halt) command."""
        if self._is_moving:
            logger.info("[SIMULATOR] Halting movement at position %d", self._position)
            self._stop_movement.set()
            if self._movement_thread:
                self._movement_thread.join(timeout=2.0)
            # Queue 'F' character
            with self._async_chars_lock:
                self._async_chars.append('F')
        return encode_command("FQ", 0)

    def _handle_fb(self, value: int) -> bytes:
        """Handle FB (Backlash) command."""
        if value == 0:
            # Query mode
            response_value = (self._backlash_mode * 100000) + self._backlash_amount
            return encode_command("FB", response_value)
        else:
            # Set mode
            self._backlash_mode = value // 100000
            self._backlash_amount = value % 1000
            logger.info("Backlash set: mode=%d, amount=%d",
                        self._backlash_mode, self._backlash_amount)
            return encode_command("FB", value)

    def _handle_fl(self, value: int) -> bytes:
        """Handle FL (Max Limit) command."""
        if value == 0:
            # Query mode
            return encode_command("FL", self._max_limit)
        else:
            # Set limit
            self._max_limit = value
            logger.info("Max limit set to: %d", self._max_limit)
            return encode_command("FL", value)

    def _handle_fc(self, value: int) -> bytes:
        """Handle FC (Motor Config) command."""
        if value == 0:
            # Query mode
            config_value = (self._motor_duty * 100000 +
                            self._motor_delay * 10000 +
                            self._motor_ticks * 1000)
            return encode_command("FC", config_value)
        else:
            # Set config
            self._motor_duty = (value // 100000) % 10
            self._motor_delay = (value // 10000) % 10
            self._motor_ticks = (value // 1000) % 10
            logger.info("Motor config set: duty=%d, delay=%d, ticks=%d",
                        self._motor_duty, self._motor_delay, self._motor_ticks)
            return encode_command("FC", value)

    def _handle_fp(self, value: int) -> bytes:
        """Handle FP (Power Switches) command."""
        if value == 0:
            # Query mode
            response_value = (self._switches[0] * 1000 +
                              self._switches[1] * 100 +
                              self._switches[2] * 10 +
                              self._switches[3])
            return encode_command("FP", response_value)
        else:
            # Toggle switch
            switch_num = value // 100000
            if 1 <= switch_num <= 4:
                idx = switch_num - 1
                self._switches[idx] = 2 if self._switches[idx] == 1 else 1
                logger.info("Toggled switch %d to %d", switch_num, self._switches[idx])
            response_value = (self._switches[0] * 1000 +
                              self._switches[1] * 100 +
                              self._switches[2] * 10 +
                              self._switches[3])
            return encode_command("FP", response_value)

    def _handle_fs(self, value: int) -> bytes:
        """Handle FS (Sync Position) command."""
        self._position = value
        self._target_position = value
        logger.info("Position synced to: %d", value)
        # FS typically doesn't respond
        return b""

    def _handle_fi(self, value: int) -> bytes:
        """Handle FI (Relative Inward) command."""
        target = max(self._position - value, self._min_limit)
        self._target_position = target
        self._start_movement(target)
        return encode_command("FI", value)

    def _handle_fo(self, value: int) -> bytes:
        """Handle FO (Relative Outward) command."""
        target = min(self._position + value, self._max_limit)
        self._target_position = target
        self._start_movement(target)
        return encode_command("FO", value)

    def _start_movement(self, target: int) -> None:
        """
        Start simulated movement in background thread.

        Args:
            target: Target position.
        """
        # Stop existing movement
        if self._is_moving:
            self._stop_movement.set()
            if self._movement_thread:
                self._movement_thread.join(timeout=2.0)

        self._stop_movement.clear()
        self._is_moving = True
        self._target_position = target

        self._movement_thread = threading.Thread(
            target=self._simulate_movement,
            args=(target,),
            daemon=True
        )
        self._movement_thread.start()

        logger.info("Movement started: %d -> %d", self._position, target)

    def _simulate_movement(self, target: int) -> None:
        """
        Simulate movement by updating position incrementally.

        Args:
            target: Target position.
        """
        direction = 1 if target > self._position else -1
        char = 'O' if direction > 0 else 'I'

        steps_per_update = max(1, self.config.movement_speed_steps_per_sec // 10)
        sleep_time = steps_per_update / self.config.movement_speed_steps_per_sec

        while not self._stop_movement.is_set():
            with self._lock:
                if self._position == target:
                    break

                # Move towards target
                remaining = abs(target - self._position)
                step = min(steps_per_update, remaining) * direction
                self._position += step

                # Queue async chars
                with self._async_chars_lock:
                    for _ in range(abs(step)):
                        self._async_chars.append(char)

            time.sleep(sleep_time)

        # Movement finished
        with self._lock:
            self._is_moving = False

            # Queue 'F' character + final position packet
            with self._async_chars_lock:
                self._async_chars.append('F')

        logger.info("Movement completed at position: %d", self._position)

    def _get_simulated_temperature(self) -> float:
        """
        Calculate simulated temperature with noise and drift.

        Returns:
            Temperature in Celsius.
        """
        base_temp = self.config.temperature_celsius

        # Add noise
        if self.config.temperature_noise_celsius > 0:
            noise = random.uniform(
                -self.config.temperature_noise_celsius,
                self.config.temperature_noise_celsius
            )
            base_temp += noise

        # Add drift
        if self.config.temperature_drift_per_hour != 0:
            elapsed_hours = (datetime.now() - self._start_time).total_seconds() / 3600.0
            drift = elapsed_hours * self.config.temperature_drift_per_hour
            base_temp += drift

        return base_temp

    def read_async_chars(self) -> List[str]:
        """Read asynchronous status characters."""
        with self._async_chars_lock:
            chars = self._async_chars.copy()
            self._async_chars.clear()
        return chars

    def get_position(self) -> int:
        """Get current position."""
        if not self._connected:
            raise NotConnectedError("Simulator not connected")
        return self._position

    def move_absolute(self, target: int) -> None:
        """Start movement to absolute position."""
        if not self._connected:
            raise NotConnectedError("Simulator not connected")

        if target < self._min_limit or target > self._max_limit:
            raise InvalidValueError(
                f"Position {target} out of range [{self._min_limit}, {self._max_limit}]"
            )

        self.send_command("FG", target)

    def halt(self) -> None:
        """Stop movement."""
        if not self._connected:
            raise NotConnectedError("Simulator not connected")
        self.send_command("FQ", 0)

    def get_temperature(self) -> float:
        """Get simulated temperature."""
        if not self._connected:
            raise NotConnectedError("Simulator not connected")

        response = self.send_command("FT", 0)
        parsed = parse_response(response)
        raw_adc = parsed["value"]

        # Convert: (raw / 2.0) - 273.15
        temp_celsius = (raw_adc / 2.0) - 273.15
        return temp_celsius

    def is_moving(self) -> bool:
        """Check if moving."""
        return self._is_moving

    def wait_for_movement_end(self, timeout: float = 300.0) -> int:
        """
        Wait for movement to finish.

        In simulator, just waits for _is_moving to become False.

        Args:
            timeout: Maximum time to wait in seconds.

        Returns:
            Final position.
        """
        if not self._connected:
            raise NotConnectedError("Simulator not connected")

        start_time = time.time()

        while self._is_moving:
            if time.time() - start_time > timeout:
                self._is_moving = False
                raise TimeoutError(f"Movement did not complete within {timeout} seconds")
            time.sleep(0.1)

        return self._position

    def get_backlash(self) -> tuple[int, int]:
        """
        Read current backlash compensation settings.

        Returns:
            Tuple of (direction, amount).
        """
        if not self._connected:
            raise NotConnectedError("Simulator not connected")
        return (self._backlash_mode, self._backlash_amount)

    def set_backlash(self, direction: int, amount: int) -> None:
        """
        Set backlash compensation.

        Args:
            direction: 2 = IN motion, 3 = OUT motion
            amount: backlash steps (0-255)
        """
        if not self._connected:
            raise NotConnectedError("Simulator not connected")

        if direction not in (2, 3):
            raise ValueError(f"Invalid backlash direction: {direction}. Must be 2 (IN) or 3 (OUT)")

        if amount < 0 or amount > 255:
            raise ValueError(f"Backlash amount must be 0-255, got {amount}")

        value = direction * 100000 + amount
        self.send_command("FB", value)

    def get_max_travel(self) -> int:
        """Read maximum travel limit from simulated hardware."""
        if not self._connected:
            raise NotConnectedError("Simulator not connected")
        return self._max_limit

    def set_max_travel(self, value: int) -> None:
        """Write maximum travel limit to simulated hardware."""
        if not self._connected:
            raise NotConnectedError("Simulator not connected")
        if value < 1 or value > 65535:
            raise ValueError(f"Max travel must be 1-65535, got {value}")
        self._max_limit = value
        logger.info(f"Simulator max travel set to {value}")

    def sync_position(self, value: int) -> None:
        """Sync/set the simulated position counter to a specific value.

        Note: Mimics real hardware behavior where FS000000 and FS000001
        return current position instead of setting it. Values 0 or 1 are converted to 2.
        """
        if not self._connected:
            raise NotConnectedError("Simulator not connected")
        if value < 0 or value > 999999:
            raise ValueError(f"Position must be 0-999999, got {value}")

        # Mimic hardware behavior: 0 or 1 becomes 2
        hw_value = value if value >= 2 else 2

        old_pos = self._position
        self._position = hw_value
        self._target_position = hw_value
        logger.info(f"Simulator position synced: {old_pos} -> {hw_value}" + (f" (requested {value})" if hw_value != value else ""))

    def reset(self) -> None:
        """Reset simulator to initial state (for testing)."""
        with self._lock:
            if self._is_moving:
                self._stop_movement.set()
                if self._movement_thread:
                    self._movement_thread.join(timeout=2.0)

            self._position = self.config.initial_position
            self._target_position = self.config.initial_position
            self._is_moving = False
            self._backlash_mode = 1
            self._backlash_amount = 0
            self._switches = [1, 1, 1, 1]

            with self._async_chars_lock:
                self._async_chars.clear()

        logger.info("Simulator reset to initial state")
