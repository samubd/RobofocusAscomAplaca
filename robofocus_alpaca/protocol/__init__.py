"""
Protocol package for Robofocus serial communication.
"""

from robofocus_alpaca.protocol.interface import SerialProtocolInterface
from robofocus_alpaca.protocol.robofocus_serial import RobofocusSerial
from robofocus_alpaca.protocol.port_scanner import (
    PortInfo,
    DiscoveredDevice,
    list_available_ports,
    scan_for_robofocus,
    find_first_robofocus,
)
from robofocus_alpaca.protocol.checksum import calculate_checksum, validate_checksum
from robofocus_alpaca.protocol.encoder import encode_command, parse_response

__all__ = [
    "SerialProtocolInterface",
    "RobofocusSerial",
    "PortInfo",
    "DiscoveredDevice",
    "list_available_ports",
    "scan_for_robofocus",
    "find_first_robofocus",
    "calculate_checksum",
    "validate_checksum",
    "encode_command",
    "parse_response",
]
