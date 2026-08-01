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
    # The *effective per-request* data scope, NOT the role's static area_scope already
    # exposed elsewhere (e.g. GET /me) — same shape, different meaning: this one
    # reflects this specific request's caller, not a general role property.
    scope: list[str] | None = None
