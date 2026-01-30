"""
ASCOM Alpaca API endpoints for ESP32.

Implements the ASCOM Alpaca REST API for focuser control.
"""

from controller import controller
from config import config

# Transaction ID counter
_transaction_id = 0


def get_next_transaction_id() -> int:
    """Get next server transaction ID."""
    global _transaction_id
    _transaction_id += 1
    return _transaction_id


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
        """Get connection status."""
        client_id = int(request.query.get("ClientTransactionID", 0))
        try:
            value = controller.connected
            return response.json(make_response(value, client_id, get_next_transaction_id()))
        except Exception as e:
            return response.json(make_response(None, client_id, get_next_transaction_id(), e))

    @server.route("/api/v1/focuser/0/position", methods=["GET"])
    async def get_position(request, response):
        """Get current position."""
        client_id = int(request.query.get("ClientTransactionID", 0))
        try:
            value = controller.get_position()
            return response.json(make_response(value, client_id, get_next_transaction_id()))
        except Exception as e:
            return response.json(make_response(None, client_id, get_next_transaction_id(), e))

    @server.route("/api/v1/focuser/0/ismoving", methods=["GET"])
    async def get_ismoving(request, response):
        """Check if focuser is moving."""
        client_id = int(request.query.get("ClientTransactionID", 0))
        try:
            value = controller.is_moving
            return response.json(make_response(value, client_id, get_next_transaction_id()))
        except Exception as e:
            return response.json(make_response(None, client_id, get_next_transaction_id(), e))

    @server.route("/api/v1/focuser/0/temperature", methods=["GET"])
    async def get_temperature(request, response):
        """Get temperature in Celsius."""
        client_id = int(request.query.get("ClientTransactionID", 0))
        try:
            value = controller.get_temperature()
            return response.json(make_response(value, client_id, get_next_transaction_id()))
        except Exception as e:
            return response.json(make_response(None, client_id, get_next_transaction_id(), e))

    @server.route("/api/v1/focuser/0/absolute", methods=["GET"])
    async def get_absolute(request, response):
        """Return True (supports absolute positioning)."""
        client_id = int(request.query.get("ClientTransactionID", 0))
        return response.json(make_response(True, client_id, get_next_transaction_id()))

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

    @server.route("/api/v1/focuser/0/tempcomp", methods=["GET"])
    async def get_tempcomp(request, response):
        """Get temperature compensation status (always False)."""
        client_id = int(request.query.get("ClientTransactionID", 0))
        return response.json(make_response(False, client_id, get_next_transaction_id()))

    @server.route("/api/v1/focuser/0/tempcompavailable", methods=["GET"])
    async def get_tempcompavailable(request, response):
        """Check if temperature compensation is available (always False)."""
        client_id = int(request.query.get("ClientTransactionID", 0))
        return response.json(make_response(False, client_id, get_next_transaction_id()))

    @server.route("/api/v1/focuser/0/interfaceversion", methods=["GET"])
    async def get_interfaceversion(request, response):
        """Get ASCOM interface version."""
        client_id = int(request.query.get("ClientTransactionID", 0))
        return response.json(make_response(3, client_id, get_next_transaction_id()))

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
                print("[alpaca] Focuser connected via API")
            else:
                controller.disconnect()
                print("[alpaca] Focuser disconnected via API")

            return response.json(make_response(None, client_id, get_next_transaction_id()))
        except Exception as e:
            print(f"[alpaca] Connect error: {e}")
            return response.json(make_response(None, client_id, get_next_transaction_id(), e))

    @server.route("/api/v1/focuser/0/move", methods=["PUT"])
    async def put_move(request, response):
        """Move to absolute position (non-blocking)."""
        client_id = int(request.form_data.get("ClientTransactionID", 0))
        try:
            position = int(request.form_data.get("Position", 0))
            controller.move(position)
            print(f"[alpaca] Move command: target={position}")
            return response.json(make_response(None, client_id, get_next_transaction_id()))
        except Exception as e:
            print(f"[alpaca] Move error: {e}")
            return response.json(make_response(None, client_id, get_next_transaction_id(), e))

    @server.route("/api/v1/focuser/0/halt", methods=["PUT"])
    async def put_halt(request, response):
        """Stop movement immediately."""
        client_id = int(request.form_data.get("ClientTransactionID", 0))
        try:
            controller.halt()
            print("[alpaca] Halt command executed")
            return response.json(make_response(None, client_id, get_next_transaction_id()))
        except Exception as e:
            print(f"[alpaca] Halt error: {e}")
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
