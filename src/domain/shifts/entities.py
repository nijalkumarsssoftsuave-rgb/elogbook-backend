"""Shift domain entity — pure business rules, no framework or I/O.

A shift is a configurable 12-hour period with a short overlap at handover
(default 06:00 start, 15-minute overlap — BRD FR-HOME-03). Shift *configuration* is
append-only and effective-dated (US-008, ES-308): a config change INSERTs a new version
row, it never UPDATEs one in place. ``area`` is nullable — ``None`` means plant-wide; an
area-specific row overrides the plant-wide row for that area when resolving (see
ES-309's ``effective_for``). This gives correct historical resolution "for free" and an
immutable, audit-friendly change history.
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

        ``hours`` divides each day into ``24 / hours`` equal windows starting at
        ``start_hour``. Pure function — deterministic and unit-testable without a clock.
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

        if hours == 12:
            # Preserve the original Day/Night labelling exactly — existing callers and
            # tests depend on ids shaped like "20260730-D" / "20260730-N".
            label = "Day" if starts_at.hour == start_hour else "Night"
            shift_id = f"{starts_at:%Y%m%d}-{label[0]}"
        else:
            # Day/Night only makes sense for exactly two windows a day. Once ``hours``
            # is configurable (ES-308) — e.g. hours=8 -> 3 windows/day — two windows
            # would collide on the same id under that scheme, so index them instead:
            # S1, S2, ... Sn. (``index`` already IS the window's position in the day —
            # no need to re-derive it from ``starts_at.hour``.)
            label = f"S{index + 1}"
            shift_id = f"{starts_at:%Y%m%d}-{label}"

        return Shift(
            shift_id=shift_id,
            label=label,
            starts_at=starts_at,
            ends_at=ends_at,
            overlap_minutes=overlap_minutes,
        )

    @staticmethod
    def from_config(cfg: "ShiftConfiguration", now: datetime) -> "Shift":
        """Build the shift window ``now`` falls into from an effective configuration row."""
        return Shift.resolve(
            now=now,
            start_hour=cfg.start_hour,
            hours=cfg.hours,
            overlap_minutes=cfg.overlap_minutes,
        )


@dataclass(frozen=True)
class ShiftConfiguration:
    """One effective-dated version of the plant's (or one area's) shift definition.

    Append-only (ES-308): a change always inserts a new row with an incremented
    ``version`` — repositories expose no update/delete for this entity. ``area is
    None`` means plant-wide; ``effective_for`` resolves which stored row applies at a
    given instant. Turning that row into an actual *shift window* (start/end times,
    a Day/Night or S1..Sn label) is ``Shift.from_config``, ES-309's job — this class
    only carries, validates, and looks up configuration rows.
    """

    id: str
    area: str | None
    start_hour: int
    hours: int
    overlap_minutes: int
    effective_from: datetime
    version: int
    created_by: str
    created_at: datetime
    updated_at: datetime

    def validate(self) -> None:
        """Raise ``ValueError`` if this configuration's values are out of range.

        A domain entity must not depend on the API layer's exception types (clean-
        architecture dependency rule), so this stays a plain ``ValueError``; the use
        case that calls it (``application/admin/manage_config.py``) translates that
        into the codebase's ``ValidationError`` (422).
        """
        if not (0 <= self.start_hour <= 23):
            raise ValueError("start_hour must be between 0 and 23.")
        if not (1 <= self.hours <= 24):
            raise ValueError("hours must be between 1 and 24.")
        if 24 % self.hours != 0:
            raise ValueError("hours must evenly divide 24.")
        if self.overlap_minutes < 0 or self.overlap_minutes >= self.hours * 60:
            raise ValueError("overlap_minutes must be >= 0 and less than hours * 60.")
        if self.effective_from.tzinfo is None:
            # A naive value can't be compared against the tz-aware effective_from of
            # every other row (effective_for below, the "history must move forward"
            # check in manage_config.py), and once persisted would keep failing on
            # every later read. The API schema already rejects this (AwareDatetime);
            # this is the domain's own guarantee for any other caller that constructs
            # a ShiftConfiguration directly.
            raise ValueError("effective_from must be timezone-aware.")

    @staticmethod
    def effective_for(
        configs: list["ShiftConfiguration"], at: datetime, area: str | None
    ) -> "ShiftConfiguration | None":
        """The configuration in effect at ``at`` for ``area``.

        Picks the greatest ``effective_from <= at`` (future rows are ignored); an exact
        area match is preferred over the plant-wide row, falling back to plant-wide when
        no area-specific row is effective yet. A tie on ``effective_from`` is broken by
        the highest ``version``. ``None`` if nothing is effective yet.
        """

        def _best(rows: list["ShiftConfiguration"]) -> "ShiftConfiguration | None":
            candidates = [c for c in rows if c.effective_from <= at]
            if not candidates:
                return None
            return max(candidates, key=lambda c: (c.effective_from, c.version))

        if area is not None:
            area_specific = _best([c for c in configs if c.area == area])
            if area_specific is not None:
                return area_specific
        return _best([c for c in configs if c.area is None])
