"""Shift-context response schemas."""

from pydantic import BaseModel


class ShiftContext(BaseModel):
    """The payload returned by the shift endpoints."""

    shift_id: str
    label: str  # e.g. "Day" / "Night"
    starts_at: str  # ISO-8601
    ends_at: str  # ISO-8601
    overlap_minutes: int
    area: str | None = (
        None  # the area whose shift configuration produced this window; None = plant-wide
    )
