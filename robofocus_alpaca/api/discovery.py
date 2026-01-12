"""
ASCOM Alpaca UDP discovery protocol.

Listens on UDP port 32227 and responds to "alpacadiscovery1" packets.
"""

import socket
import threading
import logging
import json
from typing import Optional


logger = logging.getLogger(__name__)

DISCOVERY_PORT = 32227
DISCOVERY_MESSAGE = b"alpacadiscovery1"


class DiscoveryServer:
    """UDP discovery server for ASCOM Alpaca."""

    def __init__(self, alpaca_port: int):
        """
        Initialize discovery server.

        Args:
            alpaca_port: HTTP port where Alpaca API is running.
        """
        self.alpaca_port = alpaca_port
        self.socket: Optional[socket.socket] = None
        self.thread: Optional[threading.Thread] = None
        self.running = False

    def start(self) -> None:
        """Start discovery server in background thread."""
        if self.running:
            logger.warning("Discovery server already running")
            return

        try:
            # Create UDP socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind(("0.0.0.0", DISCOVERY_PORT))
            self.socket.settimeout(1.0)  # 1 second timeout for clean shutdown

            self.running = True

            # Start background thread
            self.thread = threading.Thread(target=self._listen, daemon=True)
            self.thread.start()

            logger.info(f"Discovery server started on UDP port {DISCOVERY_PORT}")

        except OSError as e:
            logger.error(f"Failed to start discovery server: {e}")
            raise

    def stop(self) -> None:
        """Stop discovery server."""
        if not self.running:
            return

        self.running = False

        if self.thread:
            self.thread.join(timeout=3.0)

        if self.socket:
            self.socket.close()

        logger.info("Discovery server stopped")

    def _listen(self) -> None:
        """Listen for discovery packets."""
        logger.debug("Discovery server listening...")

        while self.running:
            try:
                data, addr = self.socket.recvfrom(1024)

                if data == DISCOVERY_MESSAGE:
                    self._respond(addr)

            except socket.timeout:
                # Timeout is expected (for clean shutdown)
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Error in discovery server: {e}")

    def _respond(self, addr: tuple) -> None:
        """
        Send discovery response to client.

        Args:
            addr: Client address (ip, port).
        """
        try:
            response = json.dumps({"AlpacaPort": self.alpaca_port})
            self.socket.sendto(response.encode("utf-8"), addr)
            logger.info(f"Discovery response sent to {addr[0]}:{addr[1]} (AlpacaPort={self.alpaca_port})")
        except Exception as e:
            logger.error(f"Failed to send discovery response: {e}")
