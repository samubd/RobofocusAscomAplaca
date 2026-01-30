"""
Robofocus ASCOM Alpaca Server for ESP32.

Main entry point - boots the system and starts all services.

Boot sequence:
1. Initialize hardware (LED for status)
2. Load WiFi config from NVS
3. If no config: start AP mode + config server only
4. If config exists: connect to WiFi, fallback to AP on failure
5. When in STA mode: start Alpaca server + discovery
6. Main loop: monitor WiFi, handle requests
"""

import gc
import time
import uasyncio as asyncio
from machine import Pin

# Import our modules
from config import config
from wifi_manager import wifi, WiFiState
from web_server import server
from controller import controller
from discovery import discovery
from alpaca_api import register_alpaca_routes
from gui_api import register_gui_routes, register_wifi_routes


# Configuration
HTTP_PORT = 80
AUTO_CONNECT_FOCUSER = True


async def setup_ap_mode():
    """
    Setup for AP mode (WiFi configuration only).

    In this mode:
    - WiFi provisioning page is available
    - Alpaca API is NOT available
    - Discovery is NOT running
    """
    print("\n" + "="*50)
    print("ROBOFOCUS ESP32 - AP MODE (Configuration)")
    print("="*50)
    print(f"Connect to WiFi: {config.ap_ssid}")
    print(f"Open browser: http://{wifi.AP_IP}")
    print("="*50 + "\n")

    # Register only WiFi config routes
    register_wifi_routes(server)

    # Start web server
    await server.start(port=HTTP_PORT)


async def setup_sta_mode():
    """
    Setup for STA mode (full operation).

    In this mode:
    - Alpaca API is available
    - Web GUI is available
    - Discovery is running
    - Focuser auto-connects (optional)
    """
    print("\n" + "="*50)
    print("ROBOFOCUS ESP32 - CONNECTED")
    print("="*50)
    print(f"IP Address: {wifi.ip_address}")
    print(f"Web GUI: http://{wifi.ip_address}")
    print(f"Alpaca API: http://{wifi.ip_address}/api/v1/focuser/0")
    print("="*50 + "\n")

    # Register all routes
    register_alpaca_routes(server)
    register_gui_routes(server)
    register_wifi_routes(server)  # Keep WiFi routes for reconfiguration

    # Start web server
    await server.start(port=HTTP_PORT)

    # Start discovery service
    await discovery.start()

    # Auto-connect to focuser hardware
    if AUTO_CONNECT_FOCUSER:
        print("[main] Auto-connecting to Robofocus...")
        try:
            if controller.connect():
                print("[main] Focuser connected!")
            else:
                print("[main] Focuser connection failed (will retry via API)")
        except Exception as e:
            print(f"[main] Focuser error: {e}")


async def main():
    """Main application entry point."""
    print("\n")
    print("╔══════════════════════════════════════════════════╗")
    print("║     ROBOFOCUS ASCOM ALPACA SERVER (ESP32)        ║")
    print("║     Version 1.0.0                                ║")
    print("╚══════════════════════════════════════════════════╝")
    print()

    # Show device info
    print(f"[main] Device ID: {config.device_id}")
    print(f"[main] AP SSID: {config.ap_ssid}")

    # Collect garbage before starting
    gc.collect()
    print(f"[main] Free memory: {gc.mem_free():,} bytes")

    # Check if WiFi is configured
    if config.has_wifi():
        ssid, _ = config.get_wifi()
        print(f"[main] Stored WiFi: {ssid}")

        # Try to connect
        if await wifi.ensure_connected():
            # Connected to WiFi - full operation mode
            await setup_sta_mode()
        else:
            # Connection failed - AP fallback mode
            await setup_ap_mode()
    else:
        # No WiFi configured - AP mode for initial setup
        print("[main] No WiFi configured")
        wifi.start_ap()
        await setup_ap_mode()

    # Start WiFi connection monitor
    wifi.start_monitor()

    # Main loop - keep running
    print("[main] Server running. Press Ctrl+C to stop.")

    while True:
        # Periodic maintenance
        gc.collect()

        # Check WiFi state changes
        if wifi.state == WiFiState.CONNECTED and not discovery.is_running:
            # WiFi reconnected - restart discovery
            print("[main] WiFi reconnected, restarting discovery")
            await discovery.start()

        elif wifi.state == WiFiState.AP_MODE and discovery.is_running:
            # Fell back to AP - stop discovery
            print("[main] AP mode active, stopping discovery")
            discovery.stop()

        await asyncio.sleep(5)


# Entry point
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[main] Shutting down...")
        controller.disconnect()
        discovery.stop()
        print("[main] Goodbye!")
