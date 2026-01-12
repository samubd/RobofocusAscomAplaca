"""
Map Python exceptions to ASCOM Alpaca error codes.
"""

from typing import Tuple
from robofocus_alpaca.utils.exceptions import (
    NotConnectedError,
    DriverError,
    InvalidValueError,
    ProtocolError,
    SerialTimeoutError,
    ChecksumMismatchError,
    PortNotFoundError,
    PortInUseError,
    HandshakeError,
    MaxRetriesExceededError,
    SensorError,
    LockTimeoutError,
)


# ASCOM Alpaca Error Codes
ERROR_NOT_IMPLEMENTED = 0x400  # 1024
ERROR_INVALID_VALUE = 0x402  # 1026
ERROR_NOT_CONNECTED = 0x407  # 1031
ERROR_DRIVER_ERROR = 0x500  # 1280


def map_exception_to_alpaca(exception: Exception) -> Tuple[int, str]:
    """
    Map exception to Alpaca error code and message.

    Args:
        exception: Python exception.

    Returns:
        Tuple of (ErrorNumber, ErrorMessage).
    """
    # Map specific exceptions
    if isinstance(exception, NotConnectedError):
        return (ERROR_NOT_CONNECTED, str(exception))

    if isinstance(exception, InvalidValueError):
        return (ERROR_INVALID_VALUE, str(exception))

    if isinstance(exception, (
        SerialTimeoutError,
        ChecksumMismatchError,
        PortNotFoundError,
        PortInUseError,
        HandshakeError,
        MaxRetriesExceededError,
        SensorError,
        LockTimeoutError,
        ProtocolError,
        DriverError,
    )):
        return (ERROR_DRIVER_ERROR, str(exception))

    # Unknown exception
    return (ERROR_DRIVER_ERROR, f"Internal error: {type(exception).__name__}: {exception}")
