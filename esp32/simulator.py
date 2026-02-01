"""
Focuser simulator for ESP32.

Simulates Robofocus hardware without requiring physical device.
Simplified version optimized for MicroPython and ESP32 memory constraints.
"""

import time
import random


class FocuserSimulator:
    """
    Simulated focuser for testing without hardware.

    Uses cooperative multitasking (tick-based) instead of threads.
    """

    # Movement speed (steps per second)
    MOVEMENT_SPEED = 500

    # Temperature simulation
    BASE_TEMPERATURE = 18.0  # Celsius
    TEMP_NOISE = 0.5  # +/- noise range

    def __init__(self):
        self._connected = False
        self._position = 30000  # Start at mid-range
        self._target_position = 30000
        self._is_moving = False
        self._firmware_version = "2.0"

        # Movement timing
        self._last_move_time = 0
        self._move_direction = 0  # -1=in, 0=stopped, 1=out

        # Temperature
        self._start_time = time.time()

        print("[simulator] Initialized")

    def connect(self) -> bool:
        """Connect to simulator."""
        if self._connected:
            print("[simulator] Already connected")
            return True

        self._connected = True
        print(f"[simulator] Connected (firmware: {self._firmware_version})")
        return True

    def disconnect(self):
        """Disconnect from simulator."""
        if self._is_moving:
            self.halt()
        self._connected = False
        print("[simulator] Disconnected")

    @property
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connected

    @property
    def firmware_version(self) -> str:
        """Get firmware version."""
        return self._firmware_version if self._connected else None

    def get_position(self) -> int:
        """Get current position."""
        if not self._connected:
            return 0
        self._tick()  # Update movement
        return self._position

    def is_moving(self) -> bool:
        """Check if moving."""
        if not self._connected:
            return False
        self._tick()  # Update movement
        return self._is_moving

    def move_absolute(self, target: int) -> bool:
        """
        Start movement to absolute position.

        Args:
            target: Target position (0-65535)

        Returns:
            True if movement started.
        """
        if not self._connected:
            return False

        # Clamp target
        target = max(0, min(65535, target))

        if target == self._position:
            print(f"[simulator] Already at position {target}")
            return True

        self._target_position = target
        self._is_moving = True
        self._move_direction = 1 if target > self._position else -1
        self._last_move_time = time.time()

        print(f"[simulator] Moving: {self._position} -> {target}")
        return True

    def halt(self) -> bool:
        """Stop movement immediately."""
        if not self._connected:
            return False

        if self._is_moving:
            print(f"[simulator] Halted at position {self._position}")
            self._is_moving = False
            self._move_direction = 0
            self._target_position = self._position

        return True

    def get_temperature(self) -> float:
        """
        Get simulated temperature.

        Returns:
            Temperature in Celsius with slight noise.
        """
        if not self._connected:
            return None

        # Add random noise
        noise = random.uniform(-self.TEMP_NOISE, self.TEMP_NOISE)

        # Small drift over time (0.1 deg per hour)
        elapsed_hours = (time.time() - self._start_time) / 3600.0
        drift = elapsed_hours * 0.1

        return self.BASE_TEMPERATURE + noise + drift

    def _tick(self):
        """
        Update movement state (call periodically).

        This implements cooperative multitasking - movement
        progresses when this method is called.
        """
        if not self._is_moving:
            return

        now = time.time()
        elapsed = now - self._last_move_time

        if elapsed < 0.05:  # 50ms minimum tick
            return

        # Calculate steps to move
        steps = int(elapsed * self.MOVEMENT_SPEED)
        if steps < 1:
            return

        self._last_move_time = now

        # Move towards target
        if self._move_direction > 0:
            # Moving out
            self._position = min(self._position + steps, self._target_position)
        else:
            # Moving in
            self._position = max(self._position - steps, self._target_position)

        # Check if reached target
        if self._position == self._target_position:
            self._is_moving = False
            self._move_direction = 0
            print(f"[simulator] Reached position {self._position}")

    def sync_position(self, value: int):
        """Set position counter to specific value."""
        if not self._connected:
            return

        old_pos = self._position
        self._position = max(0, min(65535, value))
        self._target_position = self._position
        print(f"[simulator] Position synced: {old_pos} -> {self._position}")


# Global simulator instance
simulator = FocuserSimulator()
