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
    "use_simulator": True,  # Default to simulator (no hardware needed)
}


class Config:
    """Configuration manager using NVS storage."""

    def __init__(self):
        self._cache = dict(DEFAULT_CONFIG)
        self._nvs = None

        if _HAS_NVS:
            try:
                self._nvs = NVS(_NAMESPACE)
                # Load focuser config from NVS
                self._load_focuser_config()
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

    # --- Focuser Configuration Persistence ---

    def _load_focuser_config(self):
        """Load focuser configuration from NVS."""
        if not self._nvs:
            return

        try:
            # Try to load each focuser setting from NVS
            for key in ['max_step', 'min_step', 'max_increment', 'step_size_microns', 'device_name']:
                try:
                    if key == 'step_size_microns':
                        # Float values stored as string
                        buf = bytearray(32)
                        length = self._nvs.get_blob(key, buf)
                        if length > 0:
                            value = float(buf[:length].decode())
                            self._cache[key] = value
                    elif key == 'device_name':
                        # String value
                        buf = bytearray(64)
                        length = self._nvs.get_blob(key, buf)
                        if length > 0:
                            self._cache[key] = buf[:length].decode()
                    else:
                        # Integer values
                        value = self._nvs.get_i32(key)
                        if value is not None:
                            self._cache[key] = value
                except OSError:
                    # Key doesn't exist, use default
                    pass

            # Load use_simulator setting
            try:
                value = self._nvs.get_i32("use_simulator")
                if value is not None:
                    self._cache["use_simulator"] = (value == 1)
            except OSError:
                pass  # Key doesn't exist, use default

            print(f"[config] Loaded focuser config: max_step={self._cache['max_step']}, "
                  f"min_step={self._cache['min_step']}, max_increment={self._cache['max_increment']}, "
                  f"use_simulator={self._cache.get('use_simulator', True)}")

        except Exception as e:
            print(f"[config] load_focuser_config error: {e}")

    def _save_focuser_config(self):
        """Save focuser configuration to NVS."""
        if not self._nvs:
            print("[config] NVS not available")
            return False

        try:
            # Save integer values
            for key in ['max_step', 'min_step', 'max_increment']:
                value = self._cache.get(key)
                if value is not None:
                    self._nvs.set_i32(key, int(value))

            # Save float as string
            step_size = self._cache.get('step_size_microns')
            if step_size is not None:
                self._nvs.set_blob('step_size_microns', str(step_size).encode())

            # Save device name
            device_name = self._cache.get('device_name')
            if device_name is not None:
                self._nvs.set_blob('device_name', device_name.encode())

            self._nvs.commit()
            print(f"[config] Focuser config saved to NVS")
            return True

        except Exception as e:
            print(f"[config] save_focuser_config error: {e}")
            return False

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
        """
        Set configuration value and persist to NVS.

        Args:
            key: Configuration key
            value: Configuration value

        Returns:
            True if saved successfully.
        """
        self._cache[key] = value
        # Persist to NVS if it's a focuser setting
        if key in ['max_step', 'min_step', 'max_increment', 'step_size_microns', 'device_name']:
            return self._save_focuser_config()
        return True

    @property
    def max_step(self) -> int:
        return self._cache.get("max_step", 60000)

    @max_step.setter
    def max_step(self, value: int):
        self._cache["max_step"] = value
        self._save_focuser_config()

    @property
    def min_step(self) -> int:
        return self._cache.get("min_step", 0)

    @min_step.setter
    def min_step(self, value: int):
        self._cache["min_step"] = value
        self._save_focuser_config()

    @property
    def max_increment(self) -> int:
        return self._cache.get("max_increment", 60000)

    @max_increment.setter
    def max_increment(self, value: int):
        self._cache["max_increment"] = value
        self._save_focuser_config()

    @property
    def step_size_microns(self) -> float:
        return self._cache.get("step_size_microns", 1.0)

    @property
    def use_simulator(self) -> bool:
        """Get use_simulator setting."""
        return self._cache.get("use_simulator", True)

    @use_simulator.setter
    def use_simulator(self, value: bool):
        """Set use_simulator and persist to NVS."""
        self._cache["use_simulator"] = value
        if self._nvs:
            try:
                self._nvs.set_i32("use_simulator", 1 if value else 0)
                self._nvs.commit()
                print(f"[config] use_simulator saved: {value}")
            except Exception as e:
                print(f"[config] save use_simulator error: {e}")


# Global config instance
config = Config()
