"""
ASCOM Alpaca API endpoints for focuser.
"""

import logging
from fastapi import APIRouter, Form, Query, Depends, Request
from robofocus_alpaca.api.models import AlpacaResponse, make_response
from robofocus_alpaca.api.app import get_next_transaction_id
from robofocus_alpaca.focuser.controller import FocuserController


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/focuser/0", tags=["focuser"])

def get_focuser(request: Request) -> FocuserController:
    """Dependency to get focuser controller from app.state."""
    focuser = getattr(request.app.state, 'focuser', None)
    if focuser is None:
        raise RuntimeError("Focuser controller not initialized")
    return focuser


@router.get("/health")
async def health_check():
    """Simple health check endpoint (no dependencies)."""
    return {"status": "ok", "message": "Server is running"}


# Helper to extract ClientTransactionID
def get_client_id(ClientTransactionID: int = Query(0)) -> int:
    """Extract client transaction ID from query params."""
    return ClientTransactionID


def get_client_id_form(ClientTransactionID: int = Form(0)) -> int:
    """Extract client transaction ID from form data."""
    return ClientTransactionID


# GET endpoints

@router.get("/connected", response_model=AlpacaResponse)
async def get_connected(
    client_id: int = Depends(get_client_id),
    focuser: FocuserController = Depends(get_focuser)
):
    """Get connection status."""
    try:
        value = focuser.connected
        response = make_response(value, client_id, get_next_transaction_id())
        logger.debug(f"GET /connected -> {value}")
        return response
    except Exception as e:
        logger.error(f"Error in /connected: {e}")
        return make_response(None, client_id, get_next_transaction_id(), e)


@router.get("/position", response_model=AlpacaResponse)
async def get_position(
    client_id: int = Depends(get_client_id),
    focuser: FocuserController = Depends(get_focuser)
):
    """Get current position."""
    try:
        value = focuser.get_position()
        response = make_response(value, client_id, get_next_transaction_id())
        logger.debug(f"GET /position -> {value}")
        return response
    except Exception as e:
        logger.error(f"Error in /position: {e}")
        return make_response(None, client_id, get_next_transaction_id(), e)


@router.get("/ismoving", response_model=AlpacaResponse)
async def get_ismoving(
    client_id: int = Depends(get_client_id),
    focuser: FocuserController = Depends(get_focuser)
):
    """Check if focuser is moving."""
    try:
        value = focuser.is_moving
        response = make_response(value, client_id, get_next_transaction_id())
        logger.debug(f"GET /ismoving -> {value}")
        return response
    except Exception as e:
        logger.error(f"Error in /ismoving: {e}")
        return make_response(None, client_id, get_next_transaction_id(), e)


@router.get("/temperature", response_model=AlpacaResponse)
async def get_temperature(
    client_id: int = Depends(get_client_id),
    focuser: FocuserController = Depends(get_focuser)
):
    """Get temperature in Celsius."""
    try:
        value = focuser.get_temperature()
        response = make_response(value, client_id, get_next_transaction_id())
        logger.debug(f"GET /temperature -> {value:.2f}°C")
        return response
    except Exception as e:
        logger.error(f"Error in /temperature: {e}")
        return make_response(None, client_id, get_next_transaction_id(), e)


@router.get("/absolute", response_model=AlpacaResponse)
async def get_absolute(
    client_id: int = Depends(get_client_id),
    focuser: FocuserController = Depends(get_focuser)
):
    """Return True (supports absolute positioning)."""
    response = make_response(True, client_id, get_next_transaction_id())
    return response


@router.get("/maxstep", response_model=AlpacaResponse)
async def get_maxstep(
    request: Request,
    client_id: int = Depends(get_client_id),
    focuser: FocuserController = Depends(get_focuser)
):
    """Get maximum logical position (adjusted for zero offset)."""
    from robofocus_alpaca.config.user_settings import get_user_settings
    user_settings = get_user_settings()
    zero_offset = user_settings.zero_offset if user_settings else 0
    value = focuser.config.max_step - zero_offset
    response = make_response(value, client_id, get_next_transaction_id())
    return response


@router.get("/maxincrement", response_model=AlpacaResponse)
async def get_maxincrement(
    client_id: int = Depends(get_client_id),
    focuser: FocuserController = Depends(get_focuser)
):
    """Get maximum single move increment."""
    value = focuser.config.max_increment
    response = make_response(value, client_id, get_next_transaction_id())
    return response


@router.get("/stepsize", response_model=AlpacaResponse)
async def get_stepsize(
    client_id: int = Depends(get_client_id),
    focuser: FocuserController = Depends(get_focuser)
):
    """Get step size in microns."""
    value = focuser.config.step_size_microns
    response = make_response(value, client_id, get_next_transaction_id())
    return response


@router.get("/tempcomp", response_model=AlpacaResponse)
async def get_tempcomp(
    client_id: int = Depends(get_client_id),
    focuser: FocuserController = Depends(get_focuser)
):
    """Get temperature compensation status (always False)."""
    response = make_response(False, client_id, get_next_transaction_id())
    return response


@router.get("/tempcompavailable", response_model=AlpacaResponse)
async def get_tempcompavailable(
    client_id: int = Depends(get_client_id),
    focuser: FocuserController = Depends(get_focuser)
):
    """Check if temperature compensation is available (always False)."""
    response = make_response(False, client_id, get_next_transaction_id())
    return response


@router.get("/interfaceversion", response_model=AlpacaResponse)
async def get_interfaceversion(
    client_id: int = Depends(get_client_id)
):
    """Get ASCOM interface version."""
    response = make_response(3, client_id, get_next_transaction_id())  # IFocuserV3 (with backlash)
    return response


@router.get("/driverversion", response_model=AlpacaResponse)
async def get_driverversion(
    client_id: int = Depends(get_client_id)
):
    """Get driver version."""
    response = make_response("1.0.0", client_id, get_next_transaction_id())
    return response


@router.get("/driverinfo", response_model=AlpacaResponse)
async def get_driverinfo(
    client_id: int = Depends(get_client_id)
):
    """Get driver information."""
    info = "ASCOM Alpaca Driver for Robofocus Focuser"
    response = make_response(info, client_id, get_next_transaction_id())
    return response


@router.get("/description", response_model=AlpacaResponse)
async def get_description(
    client_id: int = Depends(get_client_id)
):
    """Get device description."""
    response = make_response("Robofocus Electronic Focuser", client_id, get_next_transaction_id())
    return response


@router.get("/name", response_model=AlpacaResponse)
async def get_name(
    client_id: int = Depends(get_client_id)
):
    """Get device name."""
    response = make_response("Robofocus", client_id, get_next_transaction_id())
    return response


@router.get("/supportedactions", response_model=AlpacaResponse)
async def get_supportedactions(
    client_id: int = Depends(get_client_id)
):
    """Get list of supported actions (empty)."""
    response = make_response([], client_id, get_next_transaction_id())
    return response


# PUT endpoints

@router.put("/connected", response_model=AlpacaResponse)
async def put_connected(
    Connected: bool = Form(...),
    client_id: int = Depends(get_client_id_form),
    focuser: FocuserController = Depends(get_focuser)
):
    """Connect or disconnect focuser."""
    try:
        if Connected:
            focuser.connect()
            logger.info("Focuser connected via API")
        else:
            focuser.disconnect()
            logger.info("Focuser disconnected via API")

        response = make_response(None, client_id, get_next_transaction_id())
        return response
    except Exception as e:
        logger.error(f"Error in /connected PUT: {e}")
        return make_response(None, client_id, get_next_transaction_id(), e)


@router.put("/move", response_model=AlpacaResponse)
async def put_move(
    Position: int = Form(...),
    client_id: int = Depends(get_client_id_form),
    focuser: FocuserController = Depends(get_focuser)
):
    """Move to absolute position (non-blocking)."""
    try:
        focuser.move(Position)
        logger.info(f"Move command: target={Position}")
        response = make_response(None, client_id, get_next_transaction_id())
        return response
    except Exception as e:
        logger.error(f"Error in /move: {e}")
        return make_response(None, client_id, get_next_transaction_id(), e)


@router.put("/halt", response_model=AlpacaResponse)
async def put_halt(
    client_id: int = Depends(get_client_id_form),
    focuser: FocuserController = Depends(get_focuser)
):
    """Stop movement immediately."""
    try:
        focuser.halt()
        logger.info("Halt command executed")
        response = make_response(None, client_id, get_next_transaction_id())
        return response
    except Exception as e:
        logger.error(f"Error in /halt: {e}")
        return make_response(None, client_id, get_next_transaction_id(), e)


# Backlash endpoints (IFocuserV4)

@router.get("/backlash", response_model=AlpacaResponse)
async def get_backlash(
    client_id: int = Depends(get_client_id),
    focuser: FocuserController = Depends(get_focuser)
):
    """
    Get backlash compensation value.

    Returns signed value:
    - Positive = compensation on OUT motion
    - Negative = compensation on IN motion
    """
    try:
        value = focuser.get_backlash()
        response = make_response(value, client_id, get_next_transaction_id())
        logger.debug(f"GET /backlash -> {value}")
        return response
    except Exception as e:
        logger.error(f"Error in /backlash: {e}")
        return make_response(None, client_id, get_next_transaction_id(), e)


@router.put("/backlash", response_model=AlpacaResponse)
async def put_backlash(
    Backlash: int = Form(...),
    client_id: int = Depends(get_client_id_form),
    focuser: FocuserController = Depends(get_focuser)
):
    """
    Set backlash compensation.

    Accepts signed value (-255 to +255):
    - Positive = compensation on OUT motion
    - Negative = compensation on IN motion
    - Zero = disable compensation
    """
    try:
        focuser.set_backlash(Backlash)
        logger.info(f"Backlash set to {Backlash}")
        response = make_response(None, client_id, get_next_transaction_id())
        return response
    except Exception as e:
        logger.error(f"Error in /backlash PUT: {e}")
        return make_response(None, client_id, get_next_transaction_id(), e)
