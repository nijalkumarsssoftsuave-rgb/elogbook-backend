"""Shift-context response schemas."""

from pydantic import BaseModel

from src.api.schemas.pending_action import ActionResponse


class ShiftContext(BaseModel):
    """The payload returned by the shift endpoints."""

    shift_id: str
    label: str  # e.g. "Day" / "Night"
    starts_at: str  # ISO-8601
    ends_at: str  # ISO-8601
    overlap_minutes: int


class ShiftActionsReport(BaseModel):
    """A shift's window plus every confirmed action captured within it (ES-344)."""

    shift_id: str
    label: str
    starts_at: str
    ends_at: str
    actions: list[ActionResponse]
