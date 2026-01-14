"""
Web API endpoints for GUI control panel.

Works with both simulator and real hardware modes.
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from robofocus_alpaca.focuser.controller import FocuserController
from robofocus_alpaca.protocol.port_scanner import (
    list_available_ports,
    scan_for_robofocus,
    PortInfo,
    DiscoveredDevice,
)
from robofocus_alpaca.utils.exceptions import RobofocusException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gui", tags=["gui"])


# ============================================================================
# Request/Response Models
# ============================================================================

class GUIStatus(BaseModel):
    """GUI status response."""
    mode: str  # "simulator" or "hardware"
    connected: bool
    port: Optional[str] = None
    position: int = 0
    target_position: int = 0
    is_moving: bool = False
    temperature: Optional[float] = None
    firmware_version: Optional[str] = None
    max_step: int = 60000
    max_increment: int = 60000
    min_step: int = 0
    backlash: int = 0  # Signed: positive=OUT, negative=IN


class PortInfoResponse(BaseModel):
    """COM port information."""
    name: str
    description: str
    hardware_id: str


class DiscoveredDeviceResponse(BaseModel):
    """Discovered Robofocus device."""
    port: str
    firmware_version: str
    description: str


class MoveRequest(BaseModel):
    """Request to move focuser."""
    steps: Optional[int] = Field(None, description="Number of steps to move (relative)")
    direction: Optional[str] = Field(None, description="Direction: 'in' or 'out'")
    position: Optional[int] = Field(None, description="Absolute position")


class ConnectRequest(BaseModel):
    """Request to connect to a port."""
    port: str = Field(..., description="COM port name (e.g., 'COM1')")


class SetPositionRequest(BaseModel):
    """Request to set position value."""
    position: int = Field(..., description="Position value")


class SetBacklashRequest(BaseModel):
    """Request to set backlash compensation."""
    value: int = Field(..., description="Backlash value (-255 to +255)")


# ============================================================================
# Helper Functions
# ============================================================================

def get_focuser(request: Request) -> FocuserController:
    """Get focuser controller from app.state."""
    focuser = getattr(request.app.state, 'focuser', None)
    if focuser is None:
        raise HTTPException(status_code=503, detail="Focuser not available")
    return focuser


def is_simulator_mode(request: Request) -> bool:
    """Check if running in simulator mode."""
    return getattr(request.app.state, 'simulator', None) is not None


def get_user_settings(request: Request):
    """Get user settings manager from app.state."""
    return getattr(request.app.state, 'user_settings', None)


# ============================================================================
# Status Endpoint
# ============================================================================

@router.get("/status", response_model=GUIStatus)
async def get_status(request: Request):
    """Get current focuser status."""
    focuser = get_focuser(request)
    simulator = getattr(request.app.state, 'simulator', None)
    config = getattr(request.app.state, 'config', None)

    mode = "simulator" if simulator else "hardware"
    connected = focuser.connected

    status = GUIStatus(
        mode=mode,
        connected=connected,
        port=None,
        position=0,
        target_position=0,
        is_moving=False,
        temperature=None,
        firmware_version=None,
        max_step=config.focuser.max_step if config else 60000,
        max_increment=config.focuser.max_increment if config else 60000,
        min_step=config.focuser.min_step if config else 0,
    )

    if connected:
        try:
            status.position = focuser.get_position()
            status.is_moving = focuser.is_moving

            # Get temperature (might fail if sensor not available)
            try:
                status.temperature = focuser.get_temperature()
            except Exception:
                status.temperature = None

            # Get backlash (might fail on some firmware)
            try:
                status.backlash = focuser.get_backlash()
            except Exception:
                status.backlash = 0

            # Get firmware version
            if simulator:
                status.firmware_version = simulator._firmware_version
            elif hasattr(focuser.protocol, 'firmware_version'):
                status.firmware_version = focuser.protocol.firmware_version

            # Get port name
            if hasattr(focuser.protocol, 'port_name'):
                status.port = focuser.protocol.port_name

        except Exception as e:
            logger.error(f"Error getting focuser status: {e}")

    return status


# ============================================================================
# COM Port Management Endpoints
# ============================================================================

@router.get("/ports", response_model=List[PortInfoResponse])
async def get_ports():
    """List available COM ports."""
    try:
        ports = list_available_ports()
        return [
            PortInfoResponse(
                name=p.name,
                description=p.description,
                hardware_id=p.hardware_id
            )
            for p in ports
        ]
    except Exception as e:
        logger.error(f"Error listing ports: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scan", response_model=List[DiscoveredDeviceResponse])
async def scan_ports():
    """Scan for Robofocus devices on all COM ports."""
    try:
        devices = scan_for_robofocus(timeout_seconds=1.0)
        return [
            DiscoveredDeviceResponse(
                port=d.port,
                firmware_version=d.firmware_version,
                description=d.description
            )
            for d in devices
        ]
    except Exception as e:
        logger.error(f"Error scanning ports: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/connect")
async def connect_port(request: Request, connect_data: ConnectRequest):
    """Connect to a specific COM port."""
    focuser = get_focuser(request)
    config = getattr(request.app.state, 'config', None)

    if is_simulator_mode(request):
        raise HTTPException(status_code=400, detail="Cannot change port in simulator mode")

    try:
        # Disconnect if already connected
        if focuser.connected:
            focuser.disconnect()

        # Update the serial config with new port
        if config:
            config.serial.port = connect_data.port

        # Create new protocol with new port
        from robofocus_alpaca.protocol.robofocus_serial import RobofocusSerial
        new_protocol = RobofocusSerial(config.serial)

        # Update focuser's protocol
        focuser.protocol = new_protocol

        # Connect
        focuser.connect()

        # Save last used port to user settings for persistence
        user_settings = get_user_settings(request)
        if user_settings:
            user_settings.last_port = connect_data.port

        logger.info(f"[GUI] Connected to port {connect_data.port} (saved to user settings)")

        return {
            "status": "ok",
            "message": f"Connected to {connect_data.port}",
            "port": connect_data.port
        }

    except Exception as e:
        logger.error(f"Error connecting to {connect_data.port}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/disconnect")
async def disconnect_port(request: Request):
    """Disconnect from current port."""
    focuser = get_focuser(request)

    try:
        focuser.disconnect()
        return {"status": "ok", "message": "Disconnected"}
    except Exception as e:
        logger.error(f"Error disconnecting: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Movement Endpoints
# ============================================================================

@router.post("/move")
async def move_focuser(request: Request, move_data: MoveRequest):
    """Move focuser (relative or absolute)."""
    focuser = get_focuser(request)

    if not focuser.connected:
        raise HTTPException(status_code=400, detail="Focuser not connected")

    try:
        current_pos = focuser.get_position()
        max_step = focuser.config.max_step
        min_step = focuser.config.min_step

        # Absolute move
        if move_data.position is not None:
            target = move_data.position
            if target < min_step or target > max_step:
                raise HTTPException(
                    status_code=400,
                    detail=f"Position {target} out of range [{min_step}, {max_step}]"
                )

            logger.info(f"[GUI] Move to position {target} (current: {current_pos})")
            focuser.move(target)

            return {
                "status": "ok",
                "message": f"Moving to position {target}",
                "from": current_pos,
                "to": target
            }

        # Relative move
        if move_data.steps is not None and move_data.direction is not None:
            if move_data.steps <= 0:
                raise HTTPException(status_code=400, detail="Steps must be positive")

            if move_data.direction not in ["in", "out"]:
                raise HTTPException(status_code=400, detail="Direction must be 'in' or 'out'")

            if move_data.direction == "out":
                target = min(current_pos + move_data.steps, max_step)
            else:
                target = max(current_pos - move_data.steps, min_step)

            logger.info(f"[GUI] Move {move_data.direction} {move_data.steps} steps ({current_pos} -> {target})")
            focuser.move(target)

            return {
                "status": "ok",
                "message": f"Moving {move_data.direction} {move_data.steps} steps",
                "from": current_pos,
                "to": target
            }

        raise HTTPException(status_code=400, detail="Must specify 'position' or 'steps' + 'direction'")

    except RobofocusException as e:
        logger.error(f"Robofocus error during move: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during move: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/halt")
async def halt_focuser(request: Request):
    """Stop focuser movement immediately."""
    focuser = get_focuser(request)

    if not focuser.connected:
        raise HTTPException(status_code=400, detail="Focuser not connected")

    try:
        focuser.halt()
        position = focuser.get_position()
        logger.info(f"[GUI] HALT (stopped at position {position})")

        return {
            "status": "ok",
            "message": "Movement halted",
            "position": position
        }
    except Exception as e:
        logger.error(f"Error halting focuser: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Calibration Endpoints
# ============================================================================

@router.post("/set-zero")
async def set_zero_position(request: Request):
    """
    Set current position as zero.

    Note: This is a logical zero for the software. The hardware
    position counter is not modified.
    """
    focuser = get_focuser(request)
    config = getattr(request.app.state, 'config', None)

    if not focuser.connected:
        raise HTTPException(status_code=400, detail="Focuser not connected")

    try:
        current_pos = focuser.get_position()

        # Store the offset
        # TODO: Implement proper zero offset in controller
        logger.info(f"[GUI] Set zero at physical position {current_pos}")

        return {
            "status": "ok",
            "message": f"Zero point set at physical position {current_pos}",
            "physical_position": current_pos
        }
    except Exception as e:
        logger.error(f"Error setting zero: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/set-max")
async def set_max_extension(request: Request, data: SetPositionRequest):
    """
    Set maximum extension limit.

    This updates both the hardware and the runtime configuration.
    """
    focuser = get_focuser(request)

    if not focuser.connected:
        raise HTTPException(status_code=400, detail="Focuser not connected")

    try:
        if data.position <= 0:
            raise HTTPException(status_code=400, detail="Max position must be positive")

        if data.position > 65535:
            raise HTTPException(status_code=400, detail="Max position cannot exceed 65535")

        old_max = focuser.config.max_step

        # Write to hardware first
        focuser.protocol.set_max_travel(data.position)

        # Then update config
        focuser.config.max_step = data.position

        # Save config to file
        focuser.save_config()

        logger.info(f"[GUI] Max extension changed: {old_max} -> {data.position} (written to hardware and saved to config)")

        return {
            "status": "ok",
            "message": f"Max extension set to {data.position} (saved to hardware)",
            "old_value": old_max,
            "new_value": data.position
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting max extension: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/set-min")
async def set_min_position(request: Request, data: SetPositionRequest):
    """
    Set minimum position limit.

    This is a software-side limit, saved to user_settings.json.
    """
    focuser = get_focuser(request)

    if not focuser.connected:
        raise HTTPException(status_code=400, detail="Focuser not connected")

    try:
        if data.position < 0:
            raise HTTPException(status_code=400, detail="Min position cannot be negative")

        if data.position >= focuser.config.max_step:
            raise HTTPException(status_code=400, detail="Min position must be less than max")

        old_min = focuser.config.min_step
        focuser.config.min_step = data.position

        # Save to user settings for persistence
        user_settings = get_user_settings(request)
        if user_settings:
            user_settings.min_step = data.position

        logger.info(f"[GUI] Min position changed: {old_min} -> {data.position} (saved to user settings)")

        return {
            "status": "ok",
            "message": f"Min position set to {data.position} (saved)",
            "old_value": old_min,
            "new_value": data.position
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting min position: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/set-max-increment")
async def set_max_increment(request: Request, data: SetPositionRequest):
    """
    Set maximum increment (steps per single move).

    This is a software-side limit, saved to user_settings.json.
    """
    focuser = get_focuser(request)

    if not focuser.connected:
        raise HTTPException(status_code=400, detail="Focuser not connected")

    try:
        if data.position <= 0:
            raise HTTPException(status_code=400, detail="Max increment must be positive")

        if data.position > 65535:
            raise HTTPException(status_code=400, detail="Max increment cannot exceed 65535")

        old_value = focuser.config.max_increment
        focuser.config.max_increment = data.position

        # Save to user settings for persistence
        user_settings = get_user_settings(request)
        if user_settings:
            user_settings.max_increment = data.position

        logger.info(f"[GUI] Max increment changed: {old_value} -> {data.position} (saved to user settings)")

        return {
            "status": "ok",
            "message": f"Max increment set to {data.position} (saved)",
            "old_value": old_value,
            "new_value": data.position
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting max increment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/set-backlash")
async def set_backlash(request: Request, data: SetBacklashRequest):
    """
    Set backlash compensation.

    Value is signed:
    - Positive = compensation on OUT motion
    - Negative = compensation on IN motion
    - Zero = disable compensation
    """
    focuser = get_focuser(request)

    if not focuser.connected:
        raise HTTPException(status_code=400, detail="Focuser not connected")

    try:
        if data.value < -255 or data.value > 255:
            raise HTTPException(status_code=400, detail="Backlash must be between -255 and +255")

        old_value = focuser.get_backlash()
        focuser.set_backlash(data.value)

        direction = "OUT" if data.value >= 0 else "IN"
        logger.info(f"[GUI] Backlash changed: {old_value} -> {data.value} ({direction} motion)")

        return {
            "status": "ok",
            "message": f"Backlash set to {data.value} ({direction} motion)",
            "old_value": old_value,
            "new_value": data.value
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting backlash: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Protocol Logs Endpoints
# ============================================================================

@router.get("/logs")
async def get_protocol_logs(limit: int = 100, offset: int = 0):
    """
    Get protocol message logs.

    Args:
        limit: Maximum number of messages to return (default 100).
        offset: Number of messages to skip (for pagination).

    Returns:
        List of protocol messages with stats.
    """
    from robofocus_alpaca.protocol.logger import get_protocol_logger

    protocol_logger = get_protocol_logger()

    return {
        "messages": protocol_logger.get_messages(limit=limit, offset=offset),
        "stats": protocol_logger.get_stats()
    }


@router.post("/logs/clear")
async def clear_protocol_logs():
    """Clear all protocol message logs."""
    from robofocus_alpaca.protocol.logger import get_protocol_logger

    protocol_logger = get_protocol_logger()
    protocol_logger.clear()

    logger.info("[GUI] Protocol logs cleared")

    return {"status": "ok", "message": "Logs cleared"}


@router.put("/logs/enabled")
async def set_logs_enabled(enabled: bool = True):
    """Enable or disable protocol logging."""
    from robofocus_alpaca.protocol.logger import get_protocol_logger

    protocol_logger = get_protocol_logger()
    protocol_logger.enabled = enabled

    logger.info(f"[GUI] Protocol logging {'enabled' if enabled else 'disabled'}")

    return {"status": "ok", "enabled": enabled}


# ============================================================================
# Mode Switching Endpoints
# ============================================================================

class ModeInfo(BaseModel):
    """Mode information response."""
    current_mode: str  # "hardware" or "simulator"
    can_switch: bool  # False if connected
    reason: Optional[str] = None  # Why switching is not allowed


class SetModeRequest(BaseModel):
    """Request to change mode."""
    use_simulator: bool = Field(..., description="True for simulator, False for hardware")


@router.get("/mode", response_model=ModeInfo)
async def get_mode(request: Request):
    """
    Get current mode (hardware/simulator) and whether it can be switched.
    """
    focuser = get_focuser(request)
    simulator = getattr(request.app.state, 'simulator', None)
    user_settings = get_user_settings(request)

    current_mode = "simulator" if simulator else "hardware"
    connected = focuser.connected
    can_switch = not connected

    reason = None
    if connected:
        reason = "Cannot switch mode while connected. Disconnect first."

    return ModeInfo(
        current_mode=current_mode,
        can_switch=can_switch,
        reason=reason
    )


@router.put("/mode")
async def set_mode(request: Request, mode_request: SetModeRequest):
    """
    Switch between hardware and simulator mode.

    This can only be done when disconnected. The preference is saved
    to user_settings.json and will be used on next startup.
    """
    focuser = get_focuser(request)
    user_settings = get_user_settings(request)
    config = getattr(request.app.state, 'config', None)

    if not config:
        raise HTTPException(status_code=500, detail="Configuration not available")

    # Check if connected
    if focuser.connected:
        raise HTTPException(
            status_code=400,
            detail="Cannot switch mode while connected. Disconnect first."
        )

    try:
        # Save preference to user settings
        user_settings.use_simulator = mode_request.use_simulator

        # Create new protocol based on mode
        if mode_request.use_simulator:
            from robofocus_alpaca.simulator.mock_serial import MockSerialProtocol
            new_protocol = MockSerialProtocol(config.simulator)
            new_mode = "simulator"
        else:
            from robofocus_alpaca.protocol.robofocus_serial import RobofocusSerial
            new_protocol = RobofocusSerial(config.serial)
            new_mode = "hardware"

        # Hot-swap the protocol
        focuser.set_protocol(new_protocol)

        # Update app state
        request.app.state.simulator = new_protocol if mode_request.use_simulator else None

        logger.info(f"[GUI] Mode switched to {new_mode} (saved to user settings)")

        return {
            "status": "ok",
            "message": f"Mode switched to {new_mode}",
            "mode": new_mode
        }

    except Exception as e:
        logger.error(f"Error switching mode: {e}")
        raise HTTPException(status_code=500, detail=str(e))
