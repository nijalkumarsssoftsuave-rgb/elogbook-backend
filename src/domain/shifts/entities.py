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
from datetime import date, datetime, time, timedelta


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


def enumerate_shifts(
    configs: list[ShiftConfiguration],
    window_start: datetime,
    window_end: datetime,
    area: str | None,
    *,
    default_start_hour: int,
    default_hours: int,
    default_overlap_minutes: int,
) -> list[tuple[Shift, str | None]]:
    """Enumerate shift windows in [window_start, window_end) by walking a cursor
    (US-009 ES-312).

    Returns (Shift, resolved_area) pairs ascending by starts_at, mirroring
    resolve_current_shift's (Shift, area) tuple convention (ES-307) — resolved_area is
    the actual config's own area (None for plant-wide/fallback), not necessarily the
    `area` argument. Domain-pure: no Settings import (the app layer passes its shift_*
    defaults as the default_* args) — duplicates a few lines of Settings-fallback logic
    already in resolve_current_shift; that's intentional (the domain can't see Settings).

    Emits a window only when Shift.starts_at == cursor — this single rule drops any
    window straddling the true walk start, skips the overlapping re-derivation right
    after a mid-shift config change, and guarantees strictly increasing starts_at /
    unique ids. A config change mid-shift leaves a short, deliberately un-enumerated gap
    between the old shift's clean end and the new shift's next clean boundary — a known,
    accepted trade-off (not a bug): re-deriving that stretch under the new config would
    produce a window that conflicts with what was already resolved for it under the old
    one, which is worse than a gap. See ``GET /shifts``'s docstring for the API-visible
    consequence (a shift can be absent from results even though it briefly overlaps the
    requested range).

    Correctness note: the cursor walk does NOT start exactly at ``window_start``. A
    shift already in progress at ``window_start`` may have begun under a DIFFERENT
    configuration than whatever is effective exactly at ``window_start`` (the same
    mid-shift-change scenario the emit rule above handles — it just also happens to
    straddle the caller's requested window, not only a shift boundary). Restarting the
    walk fresh at ``window_start`` would silently re-derive that in-progress shift under
    the newer configuration, producing a window that overlaps/conflicts with what a
    continuous walk — or a differently-windowed query for the same instant, e.g.
    ``GET /shifts/{id}`` vs. a multi-day ``GET /shifts`` — would produce. A shift is at
    most 24h long (``ShiftConfiguration.validate()`` bounds ``hours`` to 1..24), so any
    shift touching ``window_start`` must itself have started no earlier than
    ``window_start - 24h``. Seeding the cursor there and filtering the emitted results
    back down to ``starts_at >= window_start`` guarantees every caller — regardless of
    the window it asks for — derives the same, single, consistent answer for any given
    instant.
    """
    if window_end <= window_start:
        return []
    result: list[tuple[Shift, str | None]] = []
    cursor = window_start - timedelta(hours=24)
    while cursor < window_end:
        cfg = ShiftConfiguration.effective_for(configs, cursor, area)
        if cfg is None:
            shift = Shift.resolve(
                cursor, default_start_hour, default_hours, default_overlap_minutes
            )
            resolved_area = None
        else:
            shift = Shift.from_config(cfg, cursor)
            resolved_area = cfg.area
        if shift.ends_at <= cursor:
            raise ValueError(
                f"Non-advancing shift window at {cursor.isoformat()} "
                f"(ends_at={shift.ends_at.isoformat()}) — a configuration bypassed validate()."
            )
        if shift.starts_at == cursor and shift.starts_at >= window_start:
            result.append((shift, resolved_area))
        cursor = shift.ends_at
    return result


def parse_shift_id(shift_id: str) -> date | None:
    """The calendar date encoded in ``shift_id`` (its ``YYYYMMDD`` component).

    Returns ``None`` for anything malformed: no ``-`` separator, a prefix that isn't 8
    digits, an invalid calendar date (e.g. month 13), or an empty label after the dash.
    Matching a shift by id must compare the full id string against an enumerated shift's
    own ``shift_id`` — this helper only narrows the enumeration window; it must never be
    used to re-derive the window from the label.
    """
    prefix, sep, label = shift_id.partition("-")
    if not sep or not label:
        return None
    if len(prefix) != 8 or not prefix.isdigit():
        return None
    try:
        return datetime.strptime(prefix, "%Y%m%d").date()
    except ValueError:
        return None
