"""
Command encoding for Robofocus protocol.
"""

from .checksum import calculate_checksum


def encode_command(cmd: str, value: int) -> bytes:
    """
    Encode command as 9-byte packet.

    Args:
        cmd: Two-letter command (e.g., "FG", "FV", "FT").
        value: 6-digit integer (zero-padded).

    Returns:
        9 bytes: cmd + value + checksum.

    Raises:
        ValueError: If cmd is not 2 characters or value exceeds 999999.

    Example:
        >>> encode_command("FG", 2500)
        b'FG002500\\x7f'
    """
    if len(cmd) != 2:
        raise ValueError(f"Command must be exactly 2 characters, got: {cmd}")

    if value < 0 or value > 999999:
        raise ValueError(f"Value must be 0-999999, got: {value}")

    # Create 8-character message
    message = f"{cmd}{value:06d}"

    # Calculate checksum
    checksum = calculate_checksum(message)

    # Return as bytes
    return message.encode("ascii") + bytes([checksum])


def parse_response(packet: bytes) -> dict:
    """
    Parse 9-byte response packet.

    Args:
        packet: Raw bytes from serial port (9 bytes).

    Returns:
        Dictionary with:
            - cmd: Command code (2 chars)
            - value: Numeric value (int)
            - checksum_valid: True if checksum matches

    Raises:
        ValueError: If packet is not 9 bytes.

    Example:
        >>> packet = b"FD002500" + bytes([125])
        >>> parse_response(packet)
        {'cmd': 'FD', 'value': 2500, 'checksum_valid': True}
    """
    if len(packet) != 9:
        raise ValueError(f"Expected 9 bytes, got {len(packet)}")

    # Decode message part
    try:
        message = packet[:8].decode("ascii")
    except UnicodeDecodeError as e:
        raise ValueError(f"Invalid ASCII in packet: {e}")

    # Extract command
    cmd = message[:2]

    # Extract value
    value_str = message[2:8]
    try:
        # Try integer first (standard format: "002100")
        value = int(value_str)
    except ValueError:
        # Try float format (some firmware versions: "003.20")
        try:
            value = float(value_str)
        except ValueError:
            raise ValueError(f"Invalid numeric value in packet: {value_str}")

    # Validate checksum
    checksum_received = packet[8]
    checksum_calculated = calculate_checksum(message)
    checksum_valid = (checksum_received == checksum_calculated)

    return {
        "cmd": cmd,
        "value": value,
        "checksum_valid": checksum_valid
    }
