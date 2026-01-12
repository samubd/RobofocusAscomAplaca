"""
COM port enumeration and Robofocus auto-discovery.

Provides utilities to list available serial ports and automatically
detect Robofocus devices by probing with FV command.
"""

import logging
import time
from dataclasses import dataclass
from typing import List, Optional

import serial
import serial.tools.list_ports
from serial import SerialException

from robofocus_alpaca.protocol.encoder import encode_command, parse_response
from robofocus_alpaca.protocol.checksum import validate_checksum


logger = logging.getLogger(__name__)


@dataclass
class PortInfo:
    """Information about an available serial port."""

    name: str
    description: str
    hardware_id: str
    is_bluetooth: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "hardware_id": self.hardware_id,
            "is_bluetooth": self.is_bluetooth,
        }


@dataclass
class DiscoveredDevice:
    """Information about a discovered Robofocus device."""

    port: str
    firmware_version: str
    description: str

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "port": self.port,
            "firmware_version": self.firmware_version,
            "description": self.description,
        }


def list_available_ports(include_bluetooth: bool = True) -> List[PortInfo]:
    """
    List all available serial (COM) ports on the system.

    Args:
        include_bluetooth: If False, filter out Bluetooth virtual ports.

    Returns:
        List of PortInfo objects with port metadata.
    """
    ports = []

    for port in serial.tools.list_ports.comports():
        # Check if it's a Bluetooth port
        is_bluetooth = False
        desc_lower = (port.description or "").lower()
        if "bluetooth" in desc_lower or "bth" in desc_lower:
            is_bluetooth = True

        if not include_bluetooth and is_bluetooth:
            continue

        ports.append(
            PortInfo(
                name=port.device,
                description=port.description or "Unknown",
                hardware_id=port.hwid or "",
                is_bluetooth=is_bluetooth,
            )
        )

    # Sort by port name for consistent ordering
    ports.sort(key=lambda p: p.name)

    logger.debug(f"Found {len(ports)} serial ports")
    return ports


def scan_for_robofocus(
    timeout_seconds: float = 1.0,
    skip_ports: Optional[List[str]] = None,
    include_bluetooth: bool = False,
) -> List[DiscoveredDevice]:
    """
    Scan all available COM ports to find Robofocus devices.

    Probes each port by sending FV command and validating the response.
    Uses short timeout for fast scanning.

    Args:
        timeout_seconds: Timeout per port (default 1.0s for fast scan).
        skip_ports: List of port names to skip (e.g., already in use).
        include_bluetooth: If True, also scan Bluetooth ports.

    Returns:
        List of discovered Robofocus devices with port and firmware info.
    """
    skip_ports = skip_ports or []
    discovered = []

    ports = list_available_ports(include_bluetooth=include_bluetooth)
    logger.info(f"Scanning {len(ports)} ports for Robofocus devices...")

    start_time = time.time()

    for port_info in ports:
        port_name = port_info.name

        # Skip if in skip list
        if port_name in skip_ports:
            logger.debug(f"Skipping {port_name}: in skip list")
            continue

        # Skip Bluetooth by default
        if port_info.is_bluetooth and not include_bluetooth:
            logger.debug(f"Skipping {port_name}: Bluetooth port")
            continue

        # Try to probe this port
        device = _probe_port(port_name, port_info.description, timeout_seconds)
        if device:
            discovered.append(device)

    elapsed_ms = int((time.time() - start_time) * 1000)
    logger.info(f"Scan complete: found {len(discovered)} Robofocus device(s) in {elapsed_ms}ms")

    if not discovered:
        logger.warning("No Robofocus device found on any COM port")

    return discovered


def _probe_port(port_name: str, description: str, timeout: float) -> Optional[DiscoveredDevice]:
    """
    Probe a single port to check if it's a Robofocus device.

    Args:
        port_name: COM port name (e.g., "COM5").
        description: Port description for logging.
        timeout: Read timeout in seconds.

    Returns:
        DiscoveredDevice if Robofocus found, None otherwise.
    """
    logger.debug(f"Probing {port_name} ({description})...")

    port = None
    try:
        # Open port with short timeout
        port = serial.Serial(
            port=port_name,
            baudrate=9600,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout,
            write_timeout=timeout,
        )

        # Flush buffers
        port.reset_input_buffer()
        port.reset_output_buffer()

        # Send FV command
        fv_packet = encode_command("FV", 0)
        port.write(fv_packet)
        port.flush()

        # Read response
        response = port.read(9)

        if len(response) != 9:
            logger.debug(f"{port_name}: No valid response (got {len(response)} bytes)")
            return None

        # Validate checksum
        if not validate_checksum(response):
            logger.debug(f"{port_name}: Invalid checksum")
            return None

        # Parse response
        parsed = parse_response(response)

        if parsed["cmd"] != "FV":
            logger.debug(f"{port_name}: Unexpected command in response: {parsed['cmd']}")
            return None

        # Handle both integer (002100) and float (3.2) firmware versions
        fw_value = parsed['value']
        if isinstance(fw_value, float):
            firmware = str(fw_value)
        else:
            firmware = f"{fw_value:06d}"
        logger.info(f"Found Robofocus on {port_name} (firmware: {firmware})")

        return DiscoveredDevice(
            port=port_name,
            firmware_version=firmware,
            description=description,
        )

    except SerialException as e:
        error_msg = str(e).lower()
        if "access" in error_msg or "permission" in error_msg or "in use" in error_msg:
            logger.debug(f"Skipping {port_name}: port in use")
        else:
            logger.debug(f"Skipping {port_name}: {e}")
        return None

    except Exception as e:
        logger.debug(f"Error probing {port_name}: {e}")
        return None

    finally:
        if port and port.is_open:
            port.close()


def find_first_robofocus(
    timeout_seconds: float = 1.0,
    skip_ports: Optional[List[str]] = None,
) -> Optional[DiscoveredDevice]:
    """
    Find the first available Robofocus device.

    Convenience function that returns the first device found, or None.

    Args:
        timeout_seconds: Timeout per port.
        skip_ports: Ports to skip.

    Returns:
        First discovered device, or None if none found.
    """
    devices = scan_for_robofocus(
        timeout_seconds=timeout_seconds,
        skip_ports=skip_ports,
    )

    if devices:
        if len(devices) > 1:
            logger.warning(f"Multiple Robofocus devices found, using first one: {devices[0].port}")
        return devices[0]

    return None
