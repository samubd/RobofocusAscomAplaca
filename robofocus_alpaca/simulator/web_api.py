"""
Web API endpoints for simulator control via GUI.
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from robofocus_alpaca.simulator.mock_serial import MockSerialProtocol
from robofocus_alpaca.utils.exceptions import RobofocusException


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulator", tags=["simulator"])


def get_simulator(request: Request) -> MockSerialProtocol:
    """Get simulator from app.state."""
    simulator = getattr(request.app.state, 'simulator', None)
    if simulator is None:
        raise HTTPException(status_code=503, detail="Simulator not available")
    return simulator


class SimulatorStatus(BaseModel):
    """Simulator status response."""
    position: int
    target_position: int
    is_moving: bool
    temperature: float
    firmware_version: str
    max_step: int


class MoveRequest(BaseModel):
    """Request to move simulator."""
    steps: Optional[int] = Field(None, description="Number of steps to move (relative)")
    direction: Optional[str] = Field(None, description="Direction: 'in' or 'out'")
    position: Optional[int] = Field(None, description="Absolute position (alternative to steps)")


@router.get("/status", response_model=SimulatorStatus)
async def get_status(request: Request):
    """Get current simulator status."""
    simulator = get_simulator(request)

    try:
        status = SimulatorStatus(
            position=simulator._position,
            target_position=simulator._target_position,
            is_moving=simulator.is_moving(),
            temperature=simulator._get_simulated_temperature(),
            firmware_version=simulator._firmware_version,
            max_step=simulator._max_limit
        )
        return status
    except Exception as e:
        logger.error(f"Error getting simulator status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/move")
async def move_simulator(request: Request, move_data: MoveRequest):
    """Move simulator (relative or absolute)."""
    simulator = get_simulator(request)

    try:
        current_pos = simulator._position

        # Absolute move
        if move_data.position is not None:
            target = move_data.position
            if target < simulator._min_limit or target > simulator._max_limit:
                raise HTTPException(
                    status_code=400,
                    detail=f"Position {target} out of range [0, {simulator._max_limit}]"
                )

            logger.info(f"[Web GUI] User action: GoTo position {target} (current: {current_pos})")
            simulator.move_absolute(target)

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
                target = min(current_pos + move_data.steps, simulator._max_limit)
            else:
                target = max(current_pos - move_data.steps, simulator._min_limit)

            if target != current_pos + move_data.steps * (1 if move_data.direction == "out" else -1):
                logger.warning(f"Move clamped to limits: {current_pos} -> {target}")

            logger.info(f"[Web GUI] User action: {'+' if move_data.direction == 'out' else '-'}{move_data.steps} steps (from {current_pos} to {target})")
            simulator.move_absolute(target)

            return {
                "status": "ok",
                "message": f"Moving {move_data.direction} {move_data.steps} steps",
                "from": current_pos,
                "to": target
            }

        raise HTTPException(status_code=400, detail="Must specify either 'position' or 'steps' + 'direction'")

    except RobofocusException as e:
        logger.error(f"Robofocus error during move: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during move: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/halt")
async def halt_simulator(request: Request):
    """Stop simulator movement immediately."""
    simulator = get_simulator(request)

    try:
        current_pos = simulator._position
        simulator.halt()
        logger.info(f"[Web GUI] User action: HALT (stopped at position {current_pos})")

        return {
            "status": "ok",
            "message": "Movement halted",
            "position": current_pos
        }
    except Exception as e:
        logger.error(f"Error halting simulator: {e}")
        raise HTTPException(status_code=500, detail=str(e))
