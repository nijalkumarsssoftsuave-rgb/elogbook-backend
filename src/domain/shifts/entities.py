"""Shift domain entity — pure business rules, no framework or I/O.

A shift is a configurable 12-hour period with a short overlap at handover
(default 06:00 start, 15-minute overlap — BRD FR-HOME-03).
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta


@dataclass(frozen=True)
class Shift:
    """A single shift window."""

    shift_id: str
    label: str
    starts_at: datetime
    ends_at: datetime
    overlap_minutes: int

    @staticmethod
    def resolve(now: datetime, start_hour: int, hours: int, overlap_minutes: int) -> "Shift":
        """Resolve which shift ``now`` falls into, given the shift configuration.

        Two shifts per day for a 12-hour period: Day starts at ``start_hour``, Night
        ``hours`` later. Pure function — deterministic and unit-testable without a clock.
        """
        day_start = datetime.combine(now.date(), time(hour=start_hour), tzinfo=now.tzinfo)

        if now >= day_start:
            elapsed = now - day_start
        else:
            # before today's start -> belongs to the previous day's cycle
            day_start = day_start - timedelta(days=1)
            elapsed = now - day_start

        index = int(elapsed.total_seconds() // (hours * 3600))
        starts_at = day_start + timedelta(hours=hours * index)
        ends_at = starts_at + timedelta(hours=hours)
        label = "Day" if starts_at.hour == start_hour else "Night"
        shift_id = f"{starts_at:%Y%m%d}-{label[0]}"

        return Shift(
            shift_id=shift_id,
            label=label,
            starts_at=starts_at,
            ends_at=ends_at,
            overlap_minutes=overlap_minutes,
        )
