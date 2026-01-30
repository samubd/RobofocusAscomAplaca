"""
NVS (Non-Volatile Storage) configuration manager for ESP32.

Stores WiFi credentials and focuser settings in flash memory.
"""

import json
try:
    from esp32 import NVS
    _HAS_NVS = True
except ImportError:
    _HAS_NVS = False

# NVS namespace
_NAMESPACE = "robofocus"

# Default configuration
DEFAULT_CONFIG = {
    "wifi_ssid": "",
    "wifi_password": "",
    "device_name": "Robofocus",
    "max_step": 60000,
    "min_step": 0,
    "max_increment": 60000,
    "step_size_microns": 1.0,
}


class Config:
    """Configuration manager using NVS storage."""

    def __init__(self):
        self._cache = dict(DEFAULT_CONFIG)
        self._nvs = None

        if _HAS_NVS:
            try:
                self._nvs = NVS(_NAMESPACE)
            except Exception as e:
                print(f"[config] NVS init failed: {e}")

    def _get_device_id(self) -> str:
        """Get unique device ID from MAC address."""
        try:
            import network
            import ubinascii
            wlan = network.WLAN(network.STA_IF)
            mac = wlan.config('mac')
            # Use last 4 hex chars of MAC
            return ubinascii.hexlify(mac[-2:]).decode().upper()
        except Exception:
            return "0000"

    @property
    def device_id(self) -> str:
        """Unique device identifier (last 4 hex of MAC)."""
        return self._get_device_id()

    @property
    def ap_ssid(self) -> str:
        """Access Point SSID for WiFi provisioning."""
        return f"Robofocus-{self.device_id}"

    # --- WiFi Configuration ---

    def get_wifi(self) -> tuple:
        """
        Get stored WiFi credentials.

        Returns:
            Tuple of (ssid, password) or (None, None) if not configured.
        """
        if not self._nvs:
            return (None, None)

        try:
            # Read SSID
            ssid_buf = bytearray(64)
            ssid_len = self._nvs.get_blob("wifi_ssid", ssid_buf)
            ssid = ssid_buf[:ssid_len].decode() if ssid_len > 0 else None

            # Read password
            pass_buf = bytearray(64)
            pass_len = self._nvs.get_blob("wifi_pass", pass_buf)
            password = pass_buf[:pass_len].decode() if pass_len > 0 else None

            if ssid:
                return (ssid, password or "")
            return (None, None)

        except Exception as e:
            print(f"[config] get_wifi error: {e}")
            return (None, None)

    def save_wifi(self, ssid: str, password: str) -> bool:
        """
        Save WiFi credentials to NVS.

        Args:
            ssid: WiFi network name
            password: WiFi password

        Returns:
            True if saved successfully.
        """
        if not self._nvs:
            print("[config] NVS not available")
            return False

        try:
            self._nvs.set_blob("wifi_ssid", ssid.encode())
            self._nvs.set_blob("wifi_pass", password.encode())
            self._nvs.commit()
            print(f"[config] WiFi saved: {ssid}")
            return True
        except Exception as e:
            print(f"[config] save_wifi error: {e}")
            return False

    def clear_wifi(self) -> bool:
        """
        Clear stored WiFi credentials (factory reset WiFi).

        Returns:
            True if cleared successfully.
        """
        if not self._nvs:
            return False

        try:
            self._nvs.erase_key("wifi_ssid")
            self._nvs.erase_key("wifi_pass")
            self._nvs.commit()
            print("[config] WiFi credentials cleared")
            return True
        except Exception as e:
            print(f"[config] clear_wifi error: {e}")
            return False

    def has_wifi(self) -> bool:
        """Check if WiFi credentials are stored."""
        ssid, _ = self.get_wifi()
        return ssid is not None and len(ssid) > 0

    # --- Focuser Configuration ---

    def get(self, key: str, default=None):
        """Get configuration value."""
        return self._cache.get(key, default)

    def set(self, key: str, value) -> bool:
        """Set configuration value (in-memory, not persisted)."""
        self._cache[key] = value
        return True

    @property
    def max_step(self) -> int:
        return self._cache.get("max_step", 60000)

    @max_step.setter
    def max_step(self, value: int):
        self._cache["max_step"] = value

    @property
    def min_step(self) -> int:
        return self._cache.get("min_step", 0)

    @min_step.setter
    def min_step(self, value: int):
        self._cache["min_step"] = value

    @property
    def max_increment(self) -> int:
        return self._cache.get("max_increment", 60000)

    @max_increment.setter
    def max_increment(self, value: int):
        self._cache["max_increment"] = value

    @property
    def step_size_microns(self) -> float:
        return self._cache.get("step_size_microns", 1.0)


# Global config instance
config = Config()
