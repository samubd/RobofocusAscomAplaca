"""
WiFi Manager for ESP32.

Handles WiFi provisioning via Access Point mode and connection management.
Implements automatic fallback to AP mode when WiFi connection fails.
"""

import network
import time
import uasyncio as asyncio
from machine import Pin

from config import config


class WiFiState:
    """WiFi connection states."""
    AP_MODE = "ap_mode"           # Access Point active for configuration
    CONNECTING = "connecting"      # Attempting to connect to WiFi
    CONNECTED = "connected"        # Connected to WiFi (STA mode)
    DISCONNECTED = "disconnected"  # Lost connection, will retry


class WiFiManager:
    """
    Manages WiFi connectivity with AP fallback.

    Behavior:
    - If no WiFi configured: Start in AP mode for configuration
    - If WiFi configured: Try to connect, fallback to AP after failures
    - When in STA mode: Monitor connection, re-enable AP on failure
    """

    # Configuration
    AP_IP = "192.168.4.1"
    AP_SUBNET = "255.255.255.0"
    AP_GATEWAY = "192.168.4.1"
    CONNECT_TIMEOUT = 15  # seconds
    RETRY_INTERVAL = 30   # seconds between retries
    MAX_RETRIES = 3       # retries before fallback to AP

    def __init__(self):
        self._state = WiFiState.DISCONNECTED
        self._sta = network.WLAN(network.STA_IF)
        self._ap = network.WLAN(network.AP_IF)
        self._retry_count = 0
        self._monitor_task = None
        self._led = None

        # Try to use built-in LED for status
        try:
            self._led = Pin(2, Pin.OUT)
        except Exception:
            pass

    @property
    def state(self) -> str:
        """Current WiFi state."""
        return self._state

    @property
    def is_connected(self) -> bool:
        """Check if connected to WiFi (STA mode)."""
        return self._state == WiFiState.CONNECTED and self._sta.isconnected()

    @property
    def is_ap_active(self) -> bool:
        """Check if Access Point is active."""
        return self._ap.active()

    @property
    def ip_address(self) -> str:
        """Get current IP address."""
        if self._sta.isconnected():
            return self._sta.ifconfig()[0]
        elif self._ap.active():
            return self.AP_IP
        return "0.0.0.0"

    @property
    def ssid(self) -> str:
        """Get connected SSID or AP SSID."""
        if self._sta.isconnected():
            return self._sta.config('essid')
        elif self._ap.active():
            return config.ap_ssid
        return ""

    def _set_led(self, on: bool):
        """Set LED state."""
        if self._led:
            self._led.value(1 if on else 0)

    async def _blink_led(self, interval_ms: int, count: int = -1):
        """Blink LED with given interval. count=-1 for infinite."""
        i = 0
        while count < 0 or i < count:
            self._set_led(True)
            await asyncio.sleep_ms(interval_ms // 2)
            self._set_led(False)
            await asyncio.sleep_ms(interval_ms // 2)
            i += 1

    def start_ap(self) -> bool:
        """
        Start Access Point mode for WiFi configuration.

        Returns:
            True if AP started successfully.
        """
        print(f"[wifi] Starting AP mode: {config.ap_ssid}")

        # Disable STA interface
        self._sta.active(False)

        # Configure and start AP
        self._ap.active(True)
        self._ap.config(
            essid=config.ap_ssid,
            authmode=network.AUTH_OPEN  # Open network for easy setup
        )

        # Set static IP
        self._ap.ifconfig((self.AP_IP, self.AP_SUBNET, self.AP_GATEWAY, self.AP_GATEWAY))

        self._state = WiFiState.AP_MODE
        print(f"[wifi] AP active at {self.AP_IP}")

        # Slow blink for AP mode
        self._set_led(True)

        return True

    def stop_ap(self):
        """Stop Access Point."""
        if self._ap.active():
            self._ap.active(False)
            print("[wifi] AP stopped")

    def scan_networks(self) -> list:
        """
        Scan for available WiFi networks.

        Returns:
            List of dicts with 'ssid', 'rssi', 'security' keys.
        """
        # Temporarily enable STA for scanning
        was_active = self._sta.active()
        self._sta.active(True)
        print(f"[wifi] STA activated, was_active={was_active}")
        time.sleep(2)  # ESP32 needs time to initialize STA before scan
        print("[wifi] Starting scan...")

        try:
            networks = self._sta.scan()
            print(f"[wifi] Raw scan returned {len(networks)} networks")
            result = []

            for net in networks:
                try:
                    ssid = net[0].decode('utf-8')
                except:
                    continue  # Skip networks with non-decodable SSIDs
                if ssid:  # Skip hidden networks
                    result.append({
                        'ssid': ssid,
                        'rssi': net[3],
                        'security': 'open' if net[4] == 0 else 'secured'
                    })

            # Sort by signal strength
            result.sort(key=lambda x: x['rssi'], reverse=True)

            # Remove duplicates
            seen = set()
            unique = []
            for net in result:
                if net['ssid'] not in seen:
                    seen.add(net['ssid'])
                    unique.append(net)

            print(f"[wifi] Returning {len(unique)} unique networks")
            return unique

        except Exception as e:
            print(f"[wifi] Scan error: {e}")
            return []

        finally:
            if not was_active and self._state == WiFiState.AP_MODE:
                self._sta.active(False)

    async def connect(self, ssid: str = None, password: str = None, save: bool = True) -> bool:
        """
        Connect to WiFi network.

        Args:
            ssid: Network name (uses stored if None)
            password: Network password (uses stored if None)
            save: Save credentials to NVS if connection succeeds

        Returns:
            True if connected successfully.
        """
        # Use stored credentials if not provided
        if ssid is None:
            ssid, password = config.get_wifi()

        if not ssid:
            print("[wifi] No SSID provided or stored")
            return False

        print(f"[wifi] Connecting to {ssid}...")
        self._state = WiFiState.CONNECTING

        # Disable AP while connecting
        self.stop_ap()

        # Enable and connect STA
        self._sta.active(True)
        self._sta.connect(ssid, password or "")

        # Wait for connection with timeout
        start = time.time()
        while not self._sta.isconnected():
            if time.time() - start > self.CONNECT_TIMEOUT:
                print(f"[wifi] Connection timeout to {ssid}")
                self._sta.disconnect()
                return False

            # Fast blink while connecting
            self._set_led(not self._led.value() if self._led else False)
            await asyncio.sleep_ms(200)

        # Connected!
        ip = self._sta.ifconfig()[0]
        print(f"[wifi] Connected to {ssid}, IP: {ip}")

        self._state = WiFiState.CONNECTED
        self._retry_count = 0

        # Save credentials if requested
        if save:
            config.save_wifi(ssid, password or "")

        # Solid LED for connected
        self._set_led(True)

        return True

    async def disconnect(self):
        """Disconnect from WiFi."""
        self._sta.disconnect()
        self._sta.active(False)
        self._state = WiFiState.DISCONNECTED
        self._set_led(False)
        print("[wifi] Disconnected")

    async def ensure_connected(self) -> bool:
        """
        Ensure WiFi is connected, with retry and AP fallback.

        This is the main entry point for WiFi management.

        Returns:
            True if connected to WiFi, False if in AP mode.
        """
        # Check if WiFi is configured
        if not config.has_wifi():
            print("[wifi] No WiFi configured, starting AP mode")
            self.start_ap()
            return False

        # Try to connect
        for attempt in range(self.MAX_RETRIES):
            print(f"[wifi] Connection attempt {attempt + 1}/{self.MAX_RETRIES}")

            if await self.connect():
                return True

            if attempt < self.MAX_RETRIES - 1:
                print(f"[wifi] Retrying in {self.RETRY_INTERVAL}s...")
                await asyncio.sleep(self.RETRY_INTERVAL)

        # All retries failed, fall back to AP mode
        print("[wifi] Max retries reached, starting AP fallback")
        self.start_ap()
        return False

    async def monitor_connection(self):
        """
        Background task to monitor WiFi connection.

        Automatically re-enables AP mode if connection is lost.
        """
        print("[wifi] Starting connection monitor")

        while True:
            await asyncio.sleep(5)  # Check every 5 seconds

            if self._state == WiFiState.CONNECTED:
                if not self._sta.isconnected():
                    print("[wifi] Connection lost!")
                    self._state = WiFiState.DISCONNECTED
                    self._retry_count += 1

                    if self._retry_count >= self.MAX_RETRIES:
                        print("[wifi] Max retries reached, enabling AP fallback")
                        self.start_ap()
                        self._retry_count = 0
                    else:
                        # Try to reconnect
                        print("[wifi] Attempting reconnection...")
                        if await self.connect():
                            self._retry_count = 0

            elif self._state == WiFiState.AP_MODE:
                # In AP mode, periodically check if we should retry WiFi
                # (e.g., if user configured WiFi via web interface)
                if config.has_wifi():
                    # User may have configured WiFi, try to connect
                    if await self.connect():
                        self.stop_ap()

    def start_monitor(self):
        """Start the connection monitor as a background task."""
        if self._monitor_task is None:
            self._monitor_task = asyncio.create_task(self.monitor_connection())

    def get_status(self) -> dict:
        """Get current WiFi status for API/UI."""
        return {
            'state': self._state,
            'connected': self.is_connected,
            'ap_active': self.is_ap_active,
            'ip': self.ip_address,
            'ssid': self.ssid,
            'rssi': self._sta.status('rssi') if self._sta.isconnected() else None
        }


# Global WiFi manager instance
wifi = WiFiManager()
