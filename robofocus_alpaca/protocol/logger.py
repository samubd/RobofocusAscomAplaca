"""
Protocol message logger for debugging serial communication.

Captures TX/RX messages with timestamps for debugging purposes.
"""

import threading
from collections import deque
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict

from robofocus_alpaca.protocol.encoder import parse_response


@dataclass
class ProtocolMessage:
    """A single protocol message (TX or RX)."""
    timestamp: str
    direction: str  # "TX" or "RX"
    raw_hex: str
    raw_bytes: List[int]
    decoded: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class ProtocolLogger:
    """
    Thread-safe logger for protocol messages.

    Maintains a circular buffer of messages with configurable max size.
    """

    DEFAULT_MAX_MESSAGES = 500

    def __init__(self, max_messages: int = DEFAULT_MAX_MESSAGES):
        """
        Initialize protocol logger.

        Args:
            max_messages: Maximum number of messages to keep in buffer.
        """
        self._messages: deque = deque(maxlen=max_messages)
        self._lock = threading.Lock()
        self._enabled = True
        self._tx_count = 0
        self._rx_count = 0
        self._error_count = 0

    @property
    def enabled(self) -> bool:
        """Check if logging is enabled."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Enable or disable logging."""
        self._enabled = value

    def log_tx(self, data: bytes, cmd: str = None, value: int = None) -> None:
        """
        Log a transmitted message.

        Args:
            data: Raw bytes sent.
            cmd: Optional command code (e.g., "FG").
            value: Optional command value.
        """
        if not self._enabled:
            return

        with self._lock:
            self._tx_count += 1

            msg = ProtocolMessage(
                timestamp=datetime.now().isoformat(timespec='milliseconds'),
                direction="TX",
                raw_hex=data.hex().upper(),
                raw_bytes=list(data),
                decoded=self._decode_command(data, cmd, value)
            )

            self._messages.append(msg)

    def log_rx(self, data: bytes) -> None:
        """
        Log a received message.

        Args:
            data: Raw bytes received.
        """
        if not self._enabled:
            return

        with self._lock:
            self._rx_count += 1

            decoded = None
            error = None

            if len(data) >= 9:
                try:
                    parsed = parse_response(data)
                    decoded = {
                        "cmd": parsed.get("cmd", "??"),
                        "value": parsed.get("value", 0),
                        "checksum_valid": parsed.get("checksum_valid", False),
                        "checksum_expected": parsed.get("checksum_expected"),
                        "checksum_received": parsed.get("checksum_received"),
                    }
                    if not decoded["checksum_valid"]:
                        self._error_count += 1
                        error = f"Checksum mismatch: expected {decoded['checksum_expected']}, got {decoded['checksum_received']}"
                except Exception as e:
                    error = str(e)
                    self._error_count += 1
            elif len(data) > 0:
                # Partial or async data
                decoded = {
                    "type": "async",
                    "chars": "".join(chr(b) if 32 <= b < 127 else f"[{b:02X}]" for b in data)
                }
            else:
                error = "Empty response (timeout?)"
                self._error_count += 1

            msg = ProtocolMessage(
                timestamp=datetime.now().isoformat(timespec='milliseconds'),
                direction="RX",
                raw_hex=data.hex().upper() if data else "",
                raw_bytes=list(data) if data else [],
                decoded=decoded,
                error=error
            )

            self._messages.append(msg)

    def log_error(self, error_msg: str, data: bytes = None) -> None:
        """
        Log an error message.

        Args:
            error_msg: Error description.
            data: Optional raw bytes associated with error.
        """
        if not self._enabled:
            return

        with self._lock:
            self._error_count += 1

            msg = ProtocolMessage(
                timestamp=datetime.now().isoformat(timespec='milliseconds'),
                direction="ERR",
                raw_hex=data.hex().upper() if data else "",
                raw_bytes=list(data) if data else [],
                error=error_msg
            )

            self._messages.append(msg)

    def _decode_command(self, data: bytes, cmd: str = None, value: int = None) -> Dict[str, Any]:
        """Decode a command packet."""
        if len(data) < 9:
            return {"error": "Packet too short"}

        # If cmd/value provided, use them
        if cmd and value is not None:
            return {
                "cmd": cmd,
                "value": value,
                "description": self._get_command_description(cmd, value)
            }

        # Try to parse from raw data
        try:
            # Format: F + cmd[0] + value[0-5] + checksum
            cmd_char = chr(data[1]) if len(data) > 1 else "?"
            full_cmd = f"F{cmd_char}"

            # Extract 6-digit value from bytes 2-7
            value_str = "".join(chr(b) for b in data[2:8])
            try:
                value = int(value_str)
            except ValueError:
                value = 0

            return {
                "cmd": full_cmd,
                "value": value,
                "description": self._get_command_description(full_cmd, value)
            }
        except Exception as e:
            return {"error": str(e)}

    def _get_command_description(self, cmd: str, value: int) -> str:
        """Get human-readable description of command."""
        descriptions = {
            "FV": "Get Version",
            "FG": f"Move to {value}" if value > 0 else "Query Position",
            "FD": f"Position: {value}",
            "FT": "Get Temperature",
            "FQ": "Halt Movement",
            "FB": self._describe_backlash(value),
            "FL": f"Max Travel: {value}" if value > 0 else "Query Max Travel",
            "FC": "Motor Config",
            "FP": "Power Switches",
            "FS": f"Sync Position to {value}",
            "FI": f"Move Inward {value} steps",
            "FO": f"Move Outward {value} steps",
        }
        return descriptions.get(cmd, f"Unknown command")

    def _describe_backlash(self, value: int) -> str:
        """Describe backlash command value."""
        if value == 0:
            return "Query Backlash"
        direction = value // 100000
        amount = value % 100000
        dir_str = "IN" if direction == 2 else "OUT" if direction == 3 else "OFF"
        return f"Set Backlash: {amount} steps on {dir_str} motion"

    def get_messages(self, limit: int = 100, offset: int = 0) -> List[dict]:
        """
        Get recent messages.

        Args:
            limit: Maximum number of messages to return.
            offset: Number of messages to skip from the start.

        Returns:
            List of message dictionaries, oldest first (chronological order).
        """
        with self._lock:
            messages = list(self._messages)
            # Keep chronological order (oldest first, newest last)
            # Take the last 'limit' messages
            if len(messages) > limit:
                messages = messages[-limit:]
            return [m.to_dict() for m in messages]

    def get_stats(self) -> dict:
        """Get logging statistics."""
        with self._lock:
            return {
                "total_messages": len(self._messages),
                "tx_count": self._tx_count,
                "rx_count": self._rx_count,
                "error_count": self._error_count,
                "max_messages": self._messages.maxlen,
                "enabled": self._enabled,
            }

    def clear(self) -> None:
        """Clear all logged messages."""
        with self._lock:
            self._messages.clear()
            self._tx_count = 0
            self._rx_count = 0
            self._error_count = 0


# Global instance
_logger: Optional[ProtocolLogger] = None


def get_protocol_logger() -> ProtocolLogger:
    """Get or create the global protocol logger."""
    global _logger
    if _logger is None:
        _logger = ProtocolLogger()
    return _logger
