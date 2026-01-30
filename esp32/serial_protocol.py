"""
Robofocus serial protocol handler for ESP32.

CRITICAL: This implementation follows the INDI driver (robofocus.cpp) pattern.
The byte-by-byte read loop is ESSENTIAL for correct operation.

Protocol:
- 9600 baud, 8N1, no flow control
- Commands: 2-char code + 6-digit value + 1-byte checksum = 9 bytes
- Responses: Same format, or async 'I'/'O' chars during movement
"""

from machine import UART
import time


class MovementState:
    """Movement state constants."""
    IDLE = "idle"
    MOVING = "moving"


class RobofocusProtocol:
    """
    Serial protocol handler for Robofocus focuser.

    CRITICAL PATTERN (from INDI robofocus.cpp ReadResponse):
    - Read one byte at a time
    - 'I' = inward movement, continue reading
    - 'O' = outward movement, continue reading
    - 'F' = start of response packet, read remaining 8 bytes
    - NEVER throw exceptions on I/O chars, just continue the loop
    """

    # Serial settings (fixed by Robofocus protocol)
    BAUD_RATE = 9600
    UART_ID = 2      # Use UART2 (UART0 is USB debug)
    TX_PIN = 17      # GPIO17 for TX
    RX_PIN = 16      # GPIO16 for RX

    # Timeouts
    RESPONSE_TIMEOUT_MS = 3000   # Max wait for response
    MOVEMENT_TIMEOUT_MS = 300000  # Max movement time (5 minutes)
    BYTE_TIMEOUT_MS = 500        # Timeout per byte during movement

    def __init__(self, uart_id: int = None, tx_pin: int = None, rx_pin: int = None):
        """
        Initialize protocol handler.

        Args:
            uart_id: UART peripheral ID (default: 2)
            tx_pin: TX GPIO pin (default: 17)
            rx_pin: RX GPIO pin (default: 16)
        """
        self._uart_id = uart_id if uart_id is not None else self.UART_ID
        self._tx_pin = tx_pin if tx_pin is not None else self.TX_PIN
        self._rx_pin = rx_pin if rx_pin is not None else self.RX_PIN

        self._uart = None
        self._connected = False
        self._firmware_version = None

        # State
        self._movement_state = MovementState.IDLE
        self._position = 0
        self._target_position = 0

        # Temperature cache
        self._temperature_cache = None
        self._temperature_cache_time = 0
        self._temperature_cache_max_age = 120  # seconds

    # ========================================================================
    # Checksum (from protocol/checksum.py)
    # ========================================================================

    def _calculate_checksum(self, message: str) -> int:
        """
        Calculate Robofocus checksum (sum of ASCII values modulo 256).

        Args:
            message: 8-character string (e.g., "FG002500")

        Returns:
            Checksum byte (0-255)
        """
        return sum(ord(c) for c in message) % 256

    def _validate_checksum(self, packet: bytes) -> bool:
        """Validate checksum of 9-byte packet."""
        if len(packet) != 9:
            return False
        message = packet[:8].decode('ascii', 'ignore')
        return packet[8] == self._calculate_checksum(message)

    # ========================================================================
    # Command encoding (from protocol/encoder.py)
    # ========================================================================

    def _encode_command(self, cmd: str, value: int) -> bytes:
        """
        Encode command as 9-byte packet.

        Args:
            cmd: Two-letter command (e.g., "FG", "FV", "FT")
            value: 6-digit integer (0-999999)

        Returns:
            9 bytes: cmd + value + checksum
        """
        if len(cmd) != 2:
            raise ValueError(f"Command must be 2 chars: {cmd}")
        if value < 0 or value > 999999:
            raise ValueError(f"Value must be 0-999999: {value}")

        message = f"{cmd}{value:06d}"
        checksum = self._calculate_checksum(message)
        return message.encode('ascii') + bytes([checksum])

    def _parse_response(self, packet: bytes) -> dict:
        """
        Parse 9-byte response packet.

        Returns:
            Dict with 'cmd', 'value', 'checksum_valid' keys.
        """
        if len(packet) != 9:
            raise ValueError(f"Expected 9 bytes, got {len(packet)}")

        message = packet[:8].decode('ascii', 'ignore')
        cmd = message[:2]

        # Parse value (integer or float for firmware version)
        value_str = message[2:8]
        try:
            value = int(value_str)
        except ValueError:
            try:
                value = float(value_str)
            except ValueError:
                value = 0

        checksum_valid = self._validate_checksum(packet)

        return {
            'cmd': cmd,
            'value': value,
            'checksum_valid': checksum_valid
        }

    # ========================================================================
    # Connection
    # ========================================================================

    def connect(self) -> bool:
        """
        Open serial port and validate connection with FV handshake.

        Returns:
            True if connected successfully.
        """
        if self._connected:
            return True

        print(f"[serial] Opening UART{self._uart_id} (TX={self._tx_pin}, RX={self._rx_pin})")

        try:
            self._uart = UART(
                self._uart_id,
                baudrate=self.BAUD_RATE,
                tx=self._tx_pin,
                rx=self._rx_pin,
                bits=8,
                parity=None,
                stop=1,
                timeout=100,  # 100ms timeout
                timeout_char=50
            )
        except Exception as e:
            print(f"[serial] UART init failed: {e}")
            return False

        # Flush buffers
        self._flush_buffers()

        # FV handshake
        print("[serial] Sending FV handshake...")
        try:
            response = self._send_command_internal("FV", 0)
            if response is None:
                print("[serial] No response to FV")
                self._uart = None
                return False

            parsed = self._parse_response(response)
            if not parsed['checksum_valid']:
                print("[serial] FV checksum invalid")
                self._uart = None
                return False

            # Store firmware version
            fw = parsed['value']
            self._firmware_version = str(fw) if isinstance(fw, float) else f"{fw:06d}"
            print(f"[serial] Firmware: {self._firmware_version}")

            # Read initial position
            pos_response = self._send_command_internal("FG", 0)
            if pos_response:
                pos_parsed = self._parse_response(pos_response)
                if pos_parsed['checksum_valid'] and pos_parsed['cmd'] == 'FD':
                    self._position = int(pos_parsed['value'])
                    self._target_position = self._position
                    print(f"[serial] Position: {self._position}")

            self._connected = True
            return True

        except Exception as e:
            print(f"[serial] Handshake failed: {e}")
            self._uart = None
            return False

    def disconnect(self):
        """Close serial connection."""
        if self._uart:
            self._uart.deinit()
            self._uart = None
        self._connected = False
        self._movement_state = MovementState.IDLE
        print("[serial] Disconnected")

    @property
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connected and self._uart is not None

    @property
    def firmware_version(self) -> str:
        """Get firmware version (after connect)."""
        return self._firmware_version

    # ========================================================================
    # Low-level I/O
    # ========================================================================

    def _flush_buffers(self):
        """Clear UART buffers."""
        if self._uart:
            while self._uart.any():
                self._uart.read(self._uart.any())

    def _send_command_internal(self, cmd: str, value: int) -> bytes:
        """
        Send command and read response (no retry).

        CRITICAL: This implements the byte-by-byte read loop from INDI driver.

        Returns:
            9-byte response packet, or None on timeout/error.
        """
        if not self._uart:
            return None

        # Encode and send
        packet = self._encode_command(cmd, value)
        self._uart.write(packet)

        # Read response using the CRITICAL pattern
        return self._read_response()

    def _read_response(self) -> bytes:
        """
        Read response with async char handling.

        CRITICAL PATTERN (from INDI robofocus.cpp):
        - Loop reading one byte at a time
        - 'I' (0x49) = inward movement, continue loop
        - 'O' (0x4F) = outward movement, continue loop
        - 'F' (0x46) = start of response, read 8 more bytes
        - NEVER exit on I/O, only on 'F' or timeout

        Returns:
            9-byte response packet starting with 'F', or None on timeout.
        """
        start_time = time.ticks_ms()
        timeout = self.MOVEMENT_TIMEOUT_MS if self._movement_state == MovementState.MOVING else self.RESPONSE_TIMEOUT_MS

        while True:
            # Check timeout
            elapsed = time.ticks_diff(time.ticks_ms(), start_time)
            if elapsed > timeout:
                print(f"[serial] Response timeout after {elapsed}ms")
                return None

            # Read one byte
            byte = self._uart.read(1)

            if byte is None or len(byte) == 0:
                # No data yet, continue waiting
                time.sleep_ms(10)
                continue

            char = byte[0]

            # Handle async movement chars
            if char == 0x49:  # 'I' - Inward movement
                self._movement_state = MovementState.MOVING
                # DO NOT exit - continue the loop!
                continue

            elif char == 0x4F:  # 'O' - Outward movement
                self._movement_state = MovementState.MOVING
                # DO NOT exit - continue the loop!
                continue

            elif char == 0x46:  # 'F' - Start of response packet
                # Read remaining 8 bytes
                remaining = self._uart.read(8)

                if remaining is None or len(remaining) < 8:
                    # Wait a bit and try again
                    time.sleep_ms(50)
                    first_part = remaining or b''
                    second_part = self._uart.read(8 - len(first_part))
                    remaining = first_part + (second_part or b'')

                if remaining is None or len(remaining) < 8:
                    print("[serial] Incomplete response after 'F'")
                    return None

                response = bytes([0x46]) + remaining

                # Movement finished
                self._movement_state = MovementState.IDLE

                # Flush any remaining data
                self._flush_buffers()

                return response

            else:
                # Unexpected byte, log and continue
                print(f"[serial] Unexpected byte: 0x{char:02X}")
                continue

        return None

    # ========================================================================
    # Public API
    # ========================================================================

    def get_position(self) -> int:
        """
        Get current focuser position.

        During movement, returns cached position.
        """
        if not self.is_connected:
            raise RuntimeError("Not connected")

        # During movement, return cached
        if self._movement_state == MovementState.MOVING:
            return self._position

        # Query hardware
        response = self._send_command_internal("FG", 0)

        # If None, movement may have started externally
        if response is None:
            return self._position

        parsed = self._parse_response(response)
        if parsed['cmd'] == 'FD' and parsed['checksum_valid']:
            self._position = int(parsed['value'])

        return self._position

    def move_absolute(self, target: int) -> bool:
        """
        Start movement to absolute position (non-blocking).

        Args:
            target: Target position (0-999999)

        Returns:
            True if command sent successfully.
        """
        if not self.is_connected:
            raise RuntimeError("Not connected")

        if self._movement_state == MovementState.MOVING:
            raise RuntimeError("Movement already in progress")

        print(f"[serial] Moving to {target}")

        self._target_position = target
        self._movement_state = MovementState.MOVING

        # Flush and send
        self._flush_buffers()
        packet = self._encode_command("FG", target)
        self._uart.write(packet)

        return True

    def halt(self) -> bool:
        """
        Stop movement immediately.

        Returns:
            True if halt command sent.
        """
        if not self.is_connected:
            raise RuntimeError("Not connected")

        print("[serial] Halting movement")

        # Flush and send halt (FQ or carriage return)
        self._flush_buffers()
        self._uart.write(b'\r')  # CR stops movement

        time.sleep_ms(200)  # Wait for hardware to stop

        self._movement_state = MovementState.IDLE
        self._flush_buffers()

        return True

    def get_temperature(self) -> float:
        """
        Read temperature in Celsius.

        During movement, returns cached value.
        """
        if not self.is_connected:
            raise RuntimeError("Not connected")

        current_time = time.time()
        cache_age = current_time - self._temperature_cache_time

        # During movement, return cached
        if self._movement_state == MovementState.MOVING:
            if self._temperature_cache is not None:
                return self._temperature_cache
            return 20.0  # Default if no cache

        # Check cache validity
        if self._temperature_cache is not None and cache_age < self._temperature_cache_max_age:
            return self._temperature_cache

        # Query hardware
        response = self._send_command_internal("FT", 0)

        if response is None:
            if self._temperature_cache is not None:
                return self._temperature_cache
            return 20.0

        parsed = self._parse_response(response)
        if parsed['cmd'] != 'FT':
            print(f"[serial] Unexpected response to FT: {parsed['cmd']}")
            return self._temperature_cache or 20.0

        raw_adc = int(parsed['value'])

        # Convert: Celsius = (raw - 380) / 10
        celsius = (raw_adc - 380) / 10.0

        # Cache
        self._temperature_cache = celsius
        self._temperature_cache_time = current_time

        return celsius

    def is_moving(self) -> bool:
        """Check if focuser is currently moving."""
        return self._movement_state == MovementState.MOVING

    def wait_for_movement(self, timeout_ms: int = None) -> int:
        """
        Wait for movement to complete (blocking).

        Args:
            timeout_ms: Maximum wait time (default: MOVEMENT_TIMEOUT_MS)

        Returns:
            Final position.
        """
        if timeout_ms is None:
            timeout_ms = self.MOVEMENT_TIMEOUT_MS

        if not self._movement_state == MovementState.MOVING:
            return self._position

        print("[serial] Waiting for movement to complete...")

        start_time = time.ticks_ms()

        while self._movement_state == MovementState.MOVING:
            elapsed = time.ticks_diff(time.ticks_ms(), start_time)
            if elapsed > timeout_ms:
                print("[serial] Movement wait timeout")
                self._movement_state = MovementState.IDLE
                break

            # Read and process any bytes (I/O/F)
            response = self._read_response()
            if response:
                parsed = self._parse_response(response)
                if parsed['cmd'] == 'FD' and parsed['checksum_valid']:
                    self._position = int(parsed['value'])
                    print(f"[serial] Movement complete at {self._position}")
                break

            time.sleep_ms(100)

        return self._position


# Global protocol instance
protocol = RobofocusProtocol()
