"""
Abstract interface for serial protocol communication.

This interface allows transparent substitution between real hardware and simulator.
"""

from abc import ABC, abstractmethod
from typing import List


class SerialProtocolInterface(ABC):
    """Abstract base class for serial protocol handlers."""

    @abstractmethod
    def connect(self) -> None:
        """
        Open connection to hardware.

        Raises:
            PortNotFoundError: If serial port does not exist.
            PortInUseError: If port is already open.
            HandshakeError: If hardware doesn't respond to FV command.
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection to hardware."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """
        Check if connected to hardware.

        Returns:
            True if connected, False otherwise.
        """
        pass

    @abstractmethod
    def send_command(self, cmd: str, value: int = 0) -> bytes:
        """
        Send command to hardware and wait for response.

        Args:
            cmd: Two-letter command code (e.g., "FV", "FG", "FT").
            value: 6-digit integer value (0-999999).

        Returns:
            9-byte response packet from hardware.

        Raises:
            NotConnectedError: If not connected.
            SerialTimeoutError: If no response within timeout.
            ChecksumMismatchError: If response checksum is invalid.
            ProtocolError: If response format is incorrect.
        """
        pass

    @abstractmethod
    def read_async_chars(self) -> List[str]:
        """
        Read asynchronous status characters without blocking.

        During movement, hardware sends 'I' (inward), 'O' (outward), 'F' (finished).

        Returns:
            List of characters received since last call (e.g., ['O', 'O', 'F']).
        """
        pass

    @abstractmethod
    def get_position(self) -> int:
        """
        Get current focuser position.

        Returns:
            Position in steps (0 to max_step).

        Raises:
            NotConnectedError: If not connected.
            SerialTimeoutError: If no response.
        """
        pass

    @abstractmethod
    def move_absolute(self, target: int) -> None:
        """
        Start movement to absolute position (non-blocking).

        Args:
            target: Target position in steps.

        Raises:
            NotConnectedError: If not connected.
            InvalidValueError: If target is out of range.
            SerialTimeoutError: If no response.
        """
        pass

    @abstractmethod
    def halt(self) -> None:
        """
        Stop movement immediately.

        Raises:
            NotConnectedError: If not connected.
        """
        pass

    @abstractmethod
    def get_temperature(self) -> float:
        """
        Read temperature sensor.

        Returns:
            Temperature in degrees Celsius.

        Raises:
            NotConnectedError: If not connected.
            SensorError: If sensor is not available or not responding.
            SerialTimeoutError: If no response.
        """
        pass

    @abstractmethod
    def is_moving(self) -> bool:
        """
        Check if focuser is currently moving.

        Returns:
            True if moving, False if idle.
        """
        pass

    @abstractmethod
    def get_backlash(self) -> tuple[int, int]:
        """
        Read current backlash compensation settings.

        Returns:
            Tuple of (direction, amount):
            - direction: 2 = compensation on IN motion, 3 = compensation on OUT motion
            - amount: backlash steps (0-255)

        Raises:
            NotConnectedError: If not connected.
        """
        pass

    @abstractmethod
    def set_backlash(self, direction: int, amount: int) -> None:
        """
        Set backlash compensation.

        Args:
            direction: 2 = compensation on IN motion, 3 = compensation on OUT motion
            amount: backlash steps (0-255, 0 disables)

        Raises:
            NotConnectedError: If not connected.
            ValueError: If direction or amount is invalid.
        """
        pass

    @abstractmethod
    def get_max_travel(self) -> int:
        """
        Read maximum travel limit from hardware.

        Returns:
            Max position stored in hardware.

        Raises:
            NotConnectedError: If not connected.
        """
        pass

    @abstractmethod
    def set_max_travel(self, value: int) -> None:
        """
        Write maximum travel limit to hardware.

        Args:
            value: Max position to store in hardware (1-65535).

        Raises:
            NotConnectedError: If not connected.
            ValueError: If value out of range.
        """
        pass
