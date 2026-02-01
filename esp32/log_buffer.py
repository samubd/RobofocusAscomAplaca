"""
Circular log buffer for ESP32.

Stores recent log messages in memory for viewing via web interface.
"""

import time

# Maximum number of log entries to keep
MAX_ENTRIES = 100


class LogBuffer:
    """Circular buffer for log messages."""

    def __init__(self, max_entries=MAX_ENTRIES):
        self._entries = []
        self._max = max_entries
        self._original_print = None

    def add(self, message: str, level: str = "INFO"):
        """Add a log entry."""
        entry = {
            "time": time.time(),
            "level": level,
            "message": message
        }
        self._entries.append(entry)

        # Keep only last N entries
        if len(self._entries) > self._max:
            self._entries = self._entries[-self._max:]

    def get_entries(self, limit: int = 50) -> list:
        """Get recent log entries."""
        return self._entries[-limit:]

    def clear(self):
        """Clear all entries."""
        self._entries = []

    def hook_print(self):
        """
        Hook the print function to capture logs.

        Call this once at startup to redirect print output to the buffer.
        """
        import builtins
        self._original_print = builtins.print

        def hooked_print(*args, **kwargs):
            # Call original print
            self._original_print(*args, **kwargs)

            # Capture to buffer
            message = " ".join(str(arg) for arg in args)
            level = "INFO"

            # Detect level from message prefix
            if message.startswith("["):
                if "error" in message.lower():
                    level = "ERROR"
                elif "warn" in message.lower():
                    level = "WARN"
                elif "debug" in message.lower():
                    level = "DEBUG"

            self.add(message, level)

        builtins.print = hooked_print
        print("[log] Print hook installed")


# Global log buffer instance
log_buffer = LogBuffer()
