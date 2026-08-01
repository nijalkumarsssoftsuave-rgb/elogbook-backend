"""Shift domain entity — pure business rules, no framework or I/O.

A shift is a configurable 12-hour period with a short overlap at handover
(default 06:00 start, 15-minute overlap — BRD FR-HOME-03).
"""

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta


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

    @staticmethod
    def from_id(shift_id: str, start_hour: int, hours: int, overlap_minutes: int) -> "Shift":
        """Reconstruct a past/future shift's window from its id (ES-344 shift report).

        Inverts ``resolve()``'s id scheme (``YYYYmmdd-D``/``YYYYmmdd-N``) — the date is
        always the shift's own start date, so the night shift's start hour wraps via
        ``% 24`` without needing to know which calendar day it was requested relative to.
        Always resolves in UTC, since there's no ``now`` to inherit a timezone from (every
        stored timestamp this compares against — ``PendingAction.created_at`` — is UTC).
        """
        try:
            date_part, code = shift_id.split("-")
            the_date = datetime.strptime(date_part, "%Y%m%d").date()
        except ValueError as exc:
            raise ValueError(f"Malformed shift id: {shift_id!r}") from exc

        if code == "D":
            starts_at = datetime.combine(the_date, time(hour=start_hour), tzinfo=UTC)
            label = "Day"
        elif code == "N":
            starts_at = datetime.combine(the_date, time(hour=(start_hour + hours) % 24), tzinfo=UTC)
            label = "Night"
        else:
            raise ValueError(f"Unknown shift id: {shift_id!r}")

        return Shift(
            shift_id=shift_id,
            label=label,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=hours),
            overlap_minutes=overlap_minutes,
        )
