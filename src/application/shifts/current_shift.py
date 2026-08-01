"""Use case: resolve the current shift.

Application layer — orchestrates the domain rule with configuration. Depends inward
on the domain only; the API layer calls this, not the entity directly.
"""

from datetime import UTC, datetime

from src.core.config import Settings
from src.domain.shifts.entities import Shift


def get_current_shift(settings: Settings, now: datetime | None = None) -> Shift:
    """Return the shift the current instant falls into."""
    now = now or datetime.now(UTC)
    return Shift.resolve(
        now=now,
        start_hour=settings.shift_start_hour,
        hours=settings.shift_hours,
        overlap_minutes=settings.shift_overlap_minutes,
    )
