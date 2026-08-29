from typing import Any

from pydantic import BaseModel

from app.core import ErrorCode


class ErrorResponse(BaseModel):
    """One envelope for every error response the API returns."""

    code: ErrorCode
    message: str
    request_id: str | None = None
    details: dict[str, Any] | None = None
