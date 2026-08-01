"""The one unified response envelope.

Engineering Code Standards, discipline 6 (API design): every response — success or
error — follows one identical structure, so clients rely on a single predictable shape.
The frontend reads this envelope in exactly one place.
"""

from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Meta(BaseModel):
    """Metadata attached to every response."""

    correlation_id: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class ErrorDetail(BaseModel):
    """Structured error body — present only on failure."""

    code: str
    message: str
    details: Any | None = None


class Envelope(BaseModel, Generic[T]):
    """Standard response envelope for both success and error."""

    success: bool
    data: T | None = None
    error: ErrorDetail | None = None
    meta: Meta = Field(default_factory=Meta)


def ok(data: Any = None, correlation_id: str | None = None) -> dict:
    """Build a success envelope."""
    return Envelope(success=True, data=data, meta=Meta(correlation_id=correlation_id)).model_dump(
        exclude_none=True
    )


def fail(
    code: str,
    message: str,
    details: Any = None,
    correlation_id: str | None = None,
) -> dict:
    """Build an error envelope."""
    return Envelope(
        success=False,
        error=ErrorDetail(code=code, message=message, details=details),
        meta=Meta(correlation_id=correlation_id),
    ).model_dump(exclude_none=True)
