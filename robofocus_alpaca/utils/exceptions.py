"""
Custom exception classes for the Robofocus Alpaca driver.
"""


class RobofocusException(Exception):
    """Base exception for all Robofocus driver errors."""
    pass


class NotConnectedError(RobofocusException):
    """Raised when operation requires connection but focuser is disconnected."""
    pass


class DriverError(RobofocusException):
    """General driver error (maps to Alpaca ErrorNumber 1280)."""
    pass


class InvalidValueError(RobofocusException):
    """Invalid parameter value (maps to Alpaca ErrorNumber 1026)."""
    pass


class ProtocolError(RobofocusException):
    """Serial protocol error (malformed packet, wrong length, etc.)."""
    pass


class SerialTimeoutError(RobofocusException):
    """Serial port timeout (no response from hardware)."""
    pass


class ChecksumMismatchError(ProtocolError):
    """Checksum validation failed."""
    pass


class PortNotFoundError(DriverError):
    """Serial port does not exist."""
    pass


class PortInUseError(DriverError):
    """Serial port is already open by another application."""
    pass


class HandshakeError(DriverError):
    """Failed to establish communication with hardware (FV command failed)."""
    pass


class MaxRetriesExceededError(DriverError):
    """Command failed after maximum retry attempts."""
    pass


class SensorError(DriverError):
    """Hardware sensor error (e.g., temperature sensor disconnected)."""
    pass


class LockTimeoutError(DriverError):
    """Failed to acquire serial lock within timeout."""
    pass
