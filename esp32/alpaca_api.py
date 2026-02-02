"""
ASCOM Alpaca API endpoints for ESP32.

Implements the ASCOM Alpaca REST API for focuser control.
Optimized for low-resource ESP32 with response caching.
"""

import json
import time
from controller import controller
from config import config

# Transaction ID counter
_transaction_id = 0

# Pre-cached JSON strings for static responses (avoid repeated dict creation)
_CACHE = {}

# TTL cache for dynamic values (reduces controller calls by ~80%)
# Format: {'value': x, 'json': "...", 'expires': ticks_ms}
_TTL_CACHE = {
    'position': {'value': None, 'json': None, 'expires': 0},
    'ismoving': {'value': None, 'json': None, 'expires': 0},
    'temperature': {'value': None, 'json': None, 'expires': 0},
    'connected': {'value': None, 'json': None, 'expires': 0},
}

# TTL values in milliseconds
_TTL_POSITION_MS = 150    # Position: 150ms cache (during move, updates every 150ms)
_TTL_ISMOVING_MS = 100    # IsMoving: 100ms cache
_TTL_TEMPERATURE_MS = 1000  # Temperature: 1 second cache (changes very slowly)
_TTL_CONNECTED_MS = 500   # Connected: 500ms cache


def get_next_transaction_id() -> int:
    """Get next server transaction ID."""
    global _transaction_id
    _transaction_id += 1
    return _transaction_id


def make_response_fast(value) -> str:
    """Create minimal ASCOM response as JSON string (no transaction IDs)."""
    return json.dumps({"Value": value, "ErrorNumber": 0, "ErrorMessage": ""})


def get_cached_or_fetch(key: str, fetch_func, ttl_ms: int) -> str:
    """
    Get cached JSON response or fetch fresh value.
    Returns pre-built JSON string for fastest response.
    """
    now = time.ticks_ms()
    cache = _TTL_CACHE[key]

    # Check if cache is valid
    if cache['json'] is not None and time.ticks_diff(cache['expires'], now) > 0:
        return cache['json']

    # Fetch fresh value
    value = fetch_func()
    cache['value'] = value
    cache['json'] = make_response_fast(value)
    cache['expires'] = time.ticks_add(now, ttl_ms)
    return cache['json']


def invalidate_cache(key: str = None):
    """Invalidate TTL cache (called after move/halt commands)."""
    if key:
        _TTL_CACHE[key]['expires'] = 0
    else:
        for k in _TTL_CACHE:
            _TTL_CACHE[k]['expires'] = 0


def make_response(value, client_id: int = 0, server_id: int = 0, error: Exception = None) -> dict:
    """
    Create ASCOM Alpaca response format.

    Args:
        value: Response value
        client_id: Client transaction ID
        server_id: Server transaction ID
        error: Exception if error occurred

    Returns:
        Dict in Alpaca response format.
    """
    if error:
        return {
            "Value": value,
            "ClientTransactionID": client_id,
            "ServerTransactionID": server_id,
            "ErrorNumber": 1,
            "ErrorMessage": str(error)
        }
    return {
        "Value": value,
        "ClientTransactionID": client_id,
        "ServerTransactionID": server_id,
        "ErrorNumber": 0,
        "ErrorMessage": ""
    }


def register_alpaca_routes(server):
    """
    Register all ASCOM Alpaca API routes.

    Args:
        server: WebServer instance
    """

    # ========================================================================
    # GET Endpoints
    # ========================================================================

    @server.route("/api/v1/focuser/0/connected", methods=["GET"])
    async def get_connected(request, response):
        """Get connection status (TTL cached)."""
        response.headers["Content-Type"] = "application/json"
        response.body = get_cached_or_fetch('connected', lambda: controller.connected, _TTL_CONNECTED_MS)
        return response

    @server.route("/api/v1/focuser/0/position", methods=["GET"])
    async def get_position(request, response):
        """Get current position (TTL cached)."""
        response.headers["Content-Type"] = "application/json"
        response.body = get_cached_or_fetch('position', controller.get_position, _TTL_POSITION_MS)
        return response

    @server.route("/api/v1/focuser/0/ismoving", methods=["GET"])
    async def get_ismoving(request, response):
        """Check if focuser is moving (TTL cached)."""
        response.headers["Content-Type"] = "application/json"
        response.body = get_cached_or_fetch('ismoving', lambda: controller.is_moving, _TTL_ISMOVING_MS)
        return response

    @server.route("/api/v1/focuser/0/temperature", methods=["GET"])
    async def get_temperature(request, response):
        """Get temperature in Celsius (TTL cached)."""
        response.headers["Content-Type"] = "application/json"
        response.body = get_cached_or_fetch('temperature', controller.get_temperature, _TTL_TEMPERATURE_MS)
        return response

    @server.route("/api/v1/focuser/0/absolute", methods=["GET"])
    async def get_absolute(request, response):
        """Return True (supports absolute positioning)."""
        response.headers["Content-Type"] = "application/json"
        response.body = _CACHE["absolute"]
        return response

    @server.route("/api/v1/focuser/0/maxstep", methods=["GET"])
    async def get_maxstep(request, response):
        """Get maximum position."""
        client_id = int(request.query.get("ClientTransactionID", 0))
        return response.json(make_response(config.max_step, client_id, get_next_transaction_id()))

    @server.route("/api/v1/focuser/0/maxincrement", methods=["GET"])
    async def get_maxincrement(request, response):
        """Get maximum single move increment."""
        client_id = int(request.query.get("ClientTransactionID", 0))
        return response.json(make_response(config.max_increment, client_id, get_next_transaction_id()))

    @server.route("/api/v1/focuser/0/stepsize", methods=["GET"])
    async def get_stepsize(request, response):
        """Get step size in microns."""
        client_id = int(request.query.get("ClientTransactionID", 0))
        return response.json(make_response(config.step_size_microns, client_id, get_next_transaction_id()))

    # Pre-cache static responses on first registration
    if "tempcomp" not in _CACHE:
        _CACHE["tempcomp"] = make_response_fast(False)
        _CACHE["tempcompavailable"] = make_response_fast(False)
        _CACHE["absolute"] = make_response_fast(True)
        _CACHE["interfaceversion"] = make_response_fast(3)

    @server.route("/api/v1/focuser/0/tempcomp", methods=["GET"])
    async def get_tempcomp(request, response):
        """Get temperature compensation status (always False)."""
        response.headers["Content-Type"] = "application/json"
        response.body = _CACHE["tempcomp"]
        return response

    @server.route("/api/v1/focuser/0/tempcompavailable", methods=["GET"])
    async def get_tempcompavailable(request, response):
        """Check if temperature compensation is available (always False)."""
        response.headers["Content-Type"] = "application/json"
        response.body = _CACHE["tempcompavailable"]
        return response

    @server.route("/api/v1/focuser/0/interfaceversion", methods=["GET"])
    async def get_interfaceversion(request, response):
        """Get ASCOM interface version."""
        response.headers["Content-Type"] = "application/json"
        response.body = _CACHE["interfaceversion"]
        return response

    @server.route("/api/v1/focuser/0/driverversion", methods=["GET"])
    async def get_driverversion(request, response):
        """Get driver version."""
        client_id = int(request.query.get("ClientTransactionID", 0))
        return response.json(make_response("1.0.0-esp32", client_id, get_next_transaction_id()))

    @server.route("/api/v1/focuser/0/driverinfo", methods=["GET"])
    async def get_driverinfo(request, response):
        """Get driver information."""
        client_id = int(request.query.get("ClientTransactionID", 0))
        info = "ASCOM Alpaca Driver for Robofocus (ESP32)"
        return response.json(make_response(info, client_id, get_next_transaction_id()))

    @server.route("/api/v1/focuser/0/description", methods=["GET"])
    async def get_description(request, response):
        """Get device description."""
        client_id = int(request.query.get("ClientTransactionID", 0))
        return response.json(make_response("Robofocus Electronic Focuser", client_id, get_next_transaction_id()))

    @server.route("/api/v1/focuser/0/name", methods=["GET"])
    async def get_name(request, response):
        """Get device name."""
        client_id = int(request.query.get("ClientTransactionID", 0))
        return response.json(make_response("Robofocus", client_id, get_next_transaction_id()))

    @server.route("/api/v1/focuser/0/supportedactions", methods=["GET"])
    async def get_supportedactions(request, response):
        """Get list of supported actions (empty)."""
        client_id = int(request.query.get("ClientTransactionID", 0))
        return response.json(make_response([], client_id, get_next_transaction_id()))

    # ========================================================================
    # PUT Endpoints
    # ========================================================================

    @server.route("/api/v1/focuser/0/connected", methods=["PUT"])
    async def put_connected(request, response):
        """Connect or disconnect focuser."""
        client_id = int(request.form_data.get("ClientTransactionID", 0))
        try:
            connected_str = request.form_data.get("Connected", "false")
            connected = connected_str.lower() in ("true", "1", "yes")

            if connected:
                controller.connect()
                print("[alpaca] Connected")
            else:
                controller.disconnect()
                print("[alpaca] Disconnected")

            invalidate_cache('connected')  # Force fresh value
            return response.json(make_response(None, client_id, get_next_transaction_id()))
        except Exception as e:
            return response.json(make_response(None, client_id, get_next_transaction_id(), e))

    @server.route("/api/v1/focuser/0/move", methods=["PUT"])
    async def put_move(request, response):
        """Move to absolute position (non-blocking)."""
        client_id = int(request.form_data.get("ClientTransactionID", 0))
        try:
            position = int(request.form_data.get("Position", 0))
            controller.move(position)
            invalidate_cache()  # Force fresh values after move
            print(f"[alpaca] Move: {position}")
            return response.json(make_response(None, client_id, get_next_transaction_id()))
        except Exception as e:
            return response.json(make_response(None, client_id, get_next_transaction_id(), e))

    @server.route("/api/v1/focuser/0/halt", methods=["PUT"])
    async def put_halt(request, response):
        """Stop movement immediately."""
        client_id = int(request.form_data.get("ClientTransactionID", 0))
        try:
            controller.halt()
            invalidate_cache()  # Force fresh values after halt
            print("[alpaca] Halt")
            return response.json(make_response(None, client_id, get_next_transaction_id()))
        except Exception as e:
            return response.json(make_response(None, client_id, get_next_transaction_id(), e))

    # ========================================================================
    # Management API (for discovery)
    # ========================================================================

    @server.route("/management/apiversions", methods=["GET"])
    async def get_apiversions(request, response):
        """Get supported API versions."""
        return response.json({"Value": [1]})

    @server.route("/management/v1/description", methods=["GET"])
    async def get_mgmt_description(request, response):
        """Get server description for discovery."""
        return response.json({
            "Value": {
                "ServerName": "Robofocus ESP32",
                "Manufacturer": "DIY",
                "ManufacturerVersion": "1.0.0",
                "Location": "ESP32"
            }
        })

    @server.route("/management/v1/configureddevices", methods=["GET"])
    async def get_configureddevices(request, response):
        """Get list of configured devices."""
        return response.json({
            "Value": [{
                "DeviceName": "Robofocus",
                "DeviceType": "Focuser",
                "DeviceNumber": 0,
                "UniqueID": config.device_id
            }]
        })

    print("[alpaca] Routes registered")
