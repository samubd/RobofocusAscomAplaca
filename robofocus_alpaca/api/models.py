"""
Pydantic models for ASCOM Alpaca API responses.
"""

from typing import Any, Optional
from pydantic import BaseModel, Field


class AlpacaResponse(BaseModel):
    """
    Standard ASCOM Alpaca response envelope.

    All API endpoints return this format.
    """
    Value: Any = Field(description="Response value (type varies by endpoint)")
    ClientTransactionID: int = Field(0, description="Client transaction ID (echo from request)")
    ServerTransactionID: int = Field(description="Server transaction ID (auto-incremented)")
    ErrorNumber: int = Field(0, description="Error code (0 = success, non-zero = error)")
    ErrorMessage: str = Field("", description="Error message (empty string if no error)")


def make_response(
    value: Any,
    client_id: int = 0,
    server_id: int = 0,
    error: Optional[Exception] = None
) -> AlpacaResponse:
    """
    Helper to create Alpaca response.

    Args:
        value: Response value (None if error).
        client_id: Client transaction ID.
        server_id: Server transaction ID.
        error: Exception (if any).

    Returns:
        AlpacaResponse instance.
    """
    if error is None:
        return AlpacaResponse(
            Value=value,
            ClientTransactionID=client_id,
            ServerTransactionID=server_id,
            ErrorNumber=0,
            ErrorMessage=""
        )
    else:
        # Will be handled by error_mapper
        from robofocus_alpaca.api.error_mapper import map_exception_to_alpaca
        error_number, error_message = map_exception_to_alpaca(error)

        return AlpacaResponse(
            Value=None,
            ClientTransactionID=client_id,
            ServerTransactionID=server_id,
            ErrorNumber=error_number,
            ErrorMessage=error_message
        )
