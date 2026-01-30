"""
Focuser controller - state machine and high-level API.

Provides a clean interface between the web API and the serial protocol.
"""

from config import config
from serial_protocol import protocol


class FocuserController:
    """
    High-level focuser controller.

    Wraps the serial protocol with validation and state management.
    """

    def __init__(self):
        self._protocol = protocol

    # ========================================================================
    # Connection
    # ========================================================================

    def connect(self) -> bool:
        """Connect to Robofocus hardware."""
        return self._protocol.connect()

    def disconnect(self):
        """Disconnect from hardware."""
        self._protocol.disconnect()

    @property
    def connected(self) -> bool:
        """Check if connected to hardware."""
        return self._protocol.is_connected

    @property
    def firmware_version(self) -> str:
        """Get firmware version (after connect)."""
        return self._protocol.firmware_version or "unknown"

    # ========================================================================
    # Position
    # ========================================================================

    def get_position(self) -> int:
        """Get current focuser position."""
        if not self.connected:
            return 0
        return self._protocol.get_position()

    @property
    def is_moving(self) -> bool:
        """Check if focuser is moving."""
        if not self.connected:
            return False
        return self._protocol.is_moving()

    # ========================================================================
    # Movement
    # ========================================================================

    def move(self, target: int) -> bool:
        """
        Move to absolute position.

        Args:
            target: Target position

        Returns:
            True if movement started.

        Raises:
            ValueError: If target is out of bounds.
            RuntimeError: If not connected or already moving.
        """
        if not self.connected:
            raise RuntimeError("Not connected")

        if self.is_moving:
            raise RuntimeError("Movement already in progress")

        # Validate bounds
        min_pos = config.min_step
        max_pos = config.max_step

        if target < min_pos or target > max_pos:
            raise ValueError(f"Target {target} out of bounds ({min_pos}-{max_pos})")

        # Validate max increment
        current = self.get_position()
        delta = abs(target - current)

        if delta > config.max_increment:
            raise ValueError(f"Move delta {delta} exceeds max_increment {config.max_increment}")

        return self._protocol.move_absolute(target)

    def move_relative(self, steps: int, direction: str) -> bool:
        """
        Move relative to current position.

        Args:
            steps: Number of steps
            direction: "in" or "out"

        Returns:
            True if movement started.
        """
        current = self.get_position()

        if direction == "in":
            target = current - steps
        elif direction == "out":
            target = current + steps
        else:
            raise ValueError(f"Invalid direction: {direction}")

        # Clamp to bounds
        target = max(config.min_step, min(config.max_step, target))

        return self.move(target)

    def halt(self) -> bool:
        """
        Stop movement immediately.

        Returns:
            True if halt command sent.
        """
        if not self.connected:
            return False
        return self._protocol.halt()

    # ========================================================================
    # Temperature
    # ========================================================================

    def get_temperature(self) -> float:
        """
        Get temperature in Celsius.

        Returns:
            Temperature value, or None if not available.
        """
        if not self.connected:
            return None
        try:
            return self._protocol.get_temperature()
        except Exception as e:
            print(f"[controller] Temperature error: {e}")
            return None

    # ========================================================================
    # Status
    # ========================================================================

    def get_status(self) -> dict:
        """
        Get complete focuser status for GUI/API.

        Returns:
            Dict with all status fields.
        """
        connected = self.connected
        position = self.get_position() if connected else 0
        is_moving = self.is_moving if connected else False
        temperature = self.get_temperature() if connected else None

        return {
            'connected': connected,
            'position': position,
            'is_moving': is_moving,
            'temperature': temperature,
            'firmware_version': self.firmware_version if connected else None,
            'min_step': config.min_step,
            'max_step': config.max_step,
            'max_increment': config.max_increment,
            'step_size_microns': config.step_size_microns,
            'mode': 'hardware'  # Always hardware on ESP32 (no simulator)
        }


# Global controller instance
controller = FocuserController()
