"""
ASCOM Alpaca UDP Discovery service for ESP32.

Responds to Alpaca discovery broadcasts on port 32227.
"""

import socket
import json
import uasyncio as asyncio

from config import config
from wifi_manager import wifi


DISCOVERY_PORT = 32227
DISCOVERY_MESSAGE = b"alpacadiscovery1"


class DiscoveryService:
    """
    UDP Discovery responder for ASCOM Alpaca.

    Listens on port 32227 and responds to "alpacadiscovery1" broadcasts
    with device information JSON.
    """

    def __init__(self, http_port: int = 80):
        self._http_port = http_port
        self._socket = None
        self._running = False

    @property
    def is_running(self) -> bool:
        """Check if discovery service is running."""
        return self._running

    def _get_response(self) -> bytes:
        """Build discovery response JSON."""
        response = {
            "AlpacaPort": self._http_port
        }
        return json.dumps(response).encode('utf-8')

    async def start(self):
        """Start the discovery service."""
        if self._running:
            return

        try:
            # Create UDP socket
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.bind(('0.0.0.0', DISCOVERY_PORT))
            self._socket.setblocking(False)

            self._running = True
            print(f"[discovery] Listening on UDP port {DISCOVERY_PORT}")

            # Start listener task
            asyncio.create_task(self._listen())

        except Exception as e:
            print(f"[discovery] Failed to start: {e}")
            self._running = False

    async def _listen(self):
        """Background task to handle discovery requests."""
        while self._running:
            try:
                # Non-blocking receive
                try:
                    data, addr = self._socket.recvfrom(256)
                except OSError:
                    # No data available
                    await asyncio.sleep_ms(100)
                    continue

                # Check for discovery message
                if data.strip().lower() == DISCOVERY_MESSAGE.lower():
                    print(f"[discovery] Request from {addr[0]}")

                    # Only respond if connected to WiFi (not in AP mode)
                    if wifi.is_connected:
                        response = self._get_response()
                        self._socket.sendto(response, addr)
                        print(f"[discovery] Responded with port {self._http_port}")
                    else:
                        print("[discovery] Ignoring (AP mode active)")

            except Exception as e:
                print(f"[discovery] Error: {e}")
                await asyncio.sleep_ms(1000)

    def stop(self):
        """Stop the discovery service."""
        self._running = False
        if self._socket:
            self._socket.close()
            self._socket = None
        print("[discovery] Stopped")


# Global discovery service instance
discovery = DiscoveryService()
