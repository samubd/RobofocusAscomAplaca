"""
Checksum calculation and validation for Robofocus protocol.
"""


def calculate_checksum(message: str) -> int:
    """
    Calculate Robofocus checksum (sum of ASCII values modulo 256).

    Args:
        message: 8-character string (e.g., "FG002500").

    Returns:
        Checksum byte (0-255).

    Raises:
        ValueError: If message is not exactly 8 characters.

    Example:
        >>> calculate_checksum("FG002500")
        127
    """
    if len(message) != 8:
        raise ValueError(f"Message must be exactly 8 characters, got {len(message)}")

    checksum = sum(ord(c) for c in message) % 256
    return checksum


def validate_checksum(packet: bytes) -> bool:
    """
    Validate checksum of received packet.

    Args:
        packet: 9-byte packet (8 bytes message + 1 byte checksum).

    Returns:
        True if checksum is valid, False otherwise.

    Raises:
        ValueError: If packet is not exactly 9 bytes.

    Example:
        >>> packet = b"FV002100" + bytes([54])
        >>> validate_checksum(packet)
        True
    """
    if len(packet) != 9:
        raise ValueError(f"Packet must be exactly 9 bytes, got {len(packet)}")

    message = packet[:8].decode("ascii", errors="replace")
    checksum_received = packet[8]
    checksum_calculated = calculate_checksum(message)

    return checksum_received == checksum_calculated
