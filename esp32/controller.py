"""
Focuser controller - state machine and high-level API.

Provides a clean interface between the web API and the serial protocol or simulator.
Supports runtime switching between hardware and simulator modes.
"""

from config import config


class FocuserController:
    """
    High-level focuser controller.

    Wraps the serial protocol or simulator with validation and state management.
    """

    def __init__(self):
        self._serial_protocol = None
        self._simulator = None
        self._use_simulator = config.use_simulator

        # Lazy load the active backend
        self._load_backend()

    def _load_backend(self):
        """Load the appropriate backend based on mode."""
        if self._use_simulator:
            if self._simulator is None:
                from simulator import simulator
                self._simulator = simulator
                print("[controller] Using SIMULATOR mode")
        else:
            if self._serial_protocol is None:
                from serial_protocol import protocol
                self._serial_protocol = protocol
                print("[controller] Using SERIAL/HARDWARE mode")

    @property
    def _protocol(self):
        """Get the active protocol (simulator or serial)."""
        if self._use_simulator:
            return self._simulator
        return self._serial_protocol

    # ========================================================================
    # Mode Switching
    # ========================================================================

    @property
    def mode(self) -> str:
        """Get current mode: 'simulator' or 'hardware'."""
        return 'simulator' if self._use_simulator else 'hardware'

    def set_mode(self, use_simulator: bool) -> bool:
        """
        Switch between simulator and hardware mode.

        Args:
            use_simulator: True for simulator, False for hardware.

        Returns:
            True if mode changed successfully.

        Raises:
            RuntimeError: If connected (must disconnect first).
        """
        if self.connected:
            raise RuntimeError("Disconnect before changing mode")

        if use_simulator == self._use_simulator:
            return True  # Already in requested mode

        # Save preference
        config.use_simulator = use_simulator
        self._use_simulator = use_simulator

        # Load new backend
        self._load_backend()

        print(f"[controller] Mode changed to: {self.mode}")
        return True

    # ========================================================================
    # Connection
    # ========================================================================

    def connect(self) -> bool:
        """Connect to focuser (hardware or simulator)."""
        self._load_backend()
        return self._protocol.connect()

    def disconnect(self):
        """Disconnect from focuser."""
        if self._protocol:
            self._protocol.disconnect()

    @property
    def connected(self) -> bool:
        """Check if connected."""
        if self._protocol is None:
            return False
        return self._protocol.is_connected

    @property
    def firmware_version(self) -> str:
        """Get firmware version (after connect)."""
        if self._protocol is None:
            return "unknown"
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
            'mode': self.mode,
            'use_simulator': self._use_simulator,
        }


# Global controller instance
controller = FocuserController()
