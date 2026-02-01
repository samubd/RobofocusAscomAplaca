"""
Web GUI API endpoints for ESP32.

Provides endpoints for the control panel web interface.
"""

from controller import controller
from config import config
from wifi_manager import wifi

# log_buffer disabled to save memory

# WiFi status cache - update every 5 calls to reduce overhead
_wifi_cache = None
_wifi_cache_counter = 0


def register_gui_routes(server):
    """
    Register GUI API routes.

    Args:
        server: WebServer instance
    """

    @server.route("/gui/status", methods=["GET"])
    async def get_status(request, response):
        """Get complete focuser status for GUI."""
        try:
            global _wifi_cache, _wifi_cache_counter

            status = controller.get_status()

            # Add WiFi info (cached to reduce overhead)
            _wifi_cache_counter += 1
            if _wifi_cache is None or _wifi_cache_counter >= 5:
                _wifi_cache = wifi.get_status()
                _wifi_cache_counter = 0

            status['wifi'] = _wifi_cache
            status['port'] = 'UART2'  # ESP32 uses UART, not COM port

            return response.json(status)
        except Exception as e:
            return response.error(str(e), 500)

    @server.route("/gui/move", methods=["POST"])
    async def post_move(request, response):
        """Move focuser (relative or absolute)."""
        try:
            data = request.json_data or {}

            if 'position' in data:
                # Absolute move
                target = int(data['position'])
                controller.move(target)
                return response.json({"success": True, "target": target})

            elif 'steps' in data and 'direction' in data:
                # Relative move
                steps = int(data['steps'])
                direction = data['direction']
                controller.move_relative(steps, direction)
                return response.json({"success": True, "steps": steps, "direction": direction})

            else:
                return response.error("Missing 'position' or 'steps'+'direction'", 400)

        except Exception as e:
            return response.error(str(e), 400)

    @server.route("/gui/halt", methods=["POST"])
    async def post_halt(request, response):
        """Emergency stop."""
        try:
            controller.halt()
            return response.json({"success": True, "message": "Movement halted"})
        except Exception as e:
            return response.error(str(e), 500)

    @server.route("/gui/connect", methods=["POST"])
    async def post_connect(request, response):
        """Connect to focuser hardware."""
        try:
            success = controller.connect()
            if success:
                return response.json({"success": True, "message": "Connected"})
            else:
                return response.error("Connection failed", 500)
        except Exception as e:
            return response.error(str(e), 500)

    @server.route("/gui/disconnect", methods=["POST"])
    async def post_disconnect(request, response):
        """Disconnect from focuser hardware."""
        try:
            controller.disconnect()
            return response.json({"success": True, "message": "Disconnected"})
        except Exception as e:
            return response.error(str(e), 500)

    @server.route("/gui/set-max", methods=["POST"])
    async def post_set_max(request, response):
        """Set max position."""
        try:
            data = request.json_data or {}
            value = int(data.get('position', config.max_step))
            config.max_step = value
            return response.json({"success": True, "message": f"Max position set to {value}"})
        except Exception as e:
            return response.error(str(e), 400)

    @server.route("/gui/set-min", methods=["POST"])
    async def post_set_min(request, response):
        """Set min position."""
        try:
            data = request.json_data or {}
            value = int(data.get('position', config.min_step))
            config.min_step = value
            return response.json({"success": True, "message": f"Min position set to {value}"})
        except Exception as e:
            return response.error(str(e), 400)

    @server.route("/gui/set-max-increment", methods=["POST"])
    async def post_set_max_increment(request, response):
        """Set max increment."""
        try:
            data = request.json_data or {}
            value = int(data.get('position', config.max_increment))
            config.max_increment = value
            return response.json({"success": True, "message": f"Max increment set to {value}"})
        except Exception as e:
            return response.error(str(e), 400)

    @server.route("/gui/mode", methods=["GET"])
    async def get_mode(request, response):
        """Get current mode (simulator/hardware)."""
        return response.json({
            "mode": controller.mode,
            "use_simulator": controller._use_simulator,
            "connected": controller.connected
        })

    @server.route("/gui/mode", methods=["PUT"])
    async def put_mode(request, response):
        """Set mode (simulator/hardware)."""
        try:
            data = request.json_data or {}
            use_simulator = data.get('use_simulator', True)

            # Must disconnect first
            if controller.connected:
                return response.error("Disconnect before changing mode", 400)

            controller.set_mode(use_simulator)
            return response.json({
                "success": True,
                "mode": controller.mode,
                "message": f"Mode changed to {controller.mode}"
            })
        except Exception as e:
            return response.error(str(e), 400)

    # Log endpoints disabled to save memory
    # Use serial monitor for logs instead

    print("[gui] Routes registered")


def register_wifi_routes(server):
    """
    Register WiFi configuration routes (for AP mode).

    Args:
        server: WebServer instance
    """

    @server.route("/wifi/status", methods=["GET"])
    async def get_wifi_status(request, response):
        """Get WiFi status."""
        return response.json(wifi.get_status())

    @server.route("/wifi/scan", methods=["GET"])
    async def get_wifi_scan(request, response):
        """Scan for available networks."""
        try:
            networks = wifi.scan_networks()
            return response.json({"networks": networks})
        except Exception as e:
            return response.error(str(e), 500)

    @server.route("/wifi/connect", methods=["POST"])
    async def post_wifi_connect(request, response):
        """Connect to WiFi network."""
        try:
            data = request.json_data or {}
            ssid = data.get('ssid')
            password = data.get('password', '')

            if not ssid:
                return response.error("SSID required", 400)

            # Start connection (async)
            import uasyncio as asyncio
            success = await wifi.connect(ssid, password, save=True)

            if success:
                return response.json({
                    "success": True,
                    "message": f"Connected to {ssid}",
                    "ip": wifi.ip_address
                })
            else:
                return response.error(f"Failed to connect to {ssid}", 400)

        except Exception as e:
            return response.error(str(e), 500)

    @server.route("/wifi/forget", methods=["POST"])
    async def post_wifi_forget(request, response):
        """Forget saved WiFi credentials."""
        try:
            config.clear_wifi()
            return response.json({"success": True, "message": "WiFi credentials cleared"})
        except Exception as e:
            return response.error(str(e), 500)

    print("[wifi] Routes registered")
