"""Unit tests for shift resolution — pure domain rule (BRD FR-HOME-03), no I/O.

Previously only exercised indirectly through ``GET /shifts/current`` at the real wall
clock, so the day/night boundary and previous-day wraparound branches had no
deterministic coverage.
"""

from datetime import UTC, datetime

from src.application.shifts.current_shift import get_current_shift, resolve_current_shift
from src.application.shifts.repository import ShiftConfigRepository
from src.core.config import get_settings
from src.domain.shifts.entities import Shift, ShiftConfiguration

START_HOUR = 6
HOURS = 12
OVERLAP = 15


class _EmptyShiftConfigRepository(ShiftConfigRepository):
    """A ``ShiftConfigRepository`` with nothing persisted — forces the Settings fallback."""

    async def list_all(self) -> list[ShiftConfiguration]:
        return []

    async def get(self, config_id: str) -> ShiftConfiguration | None:
        return None

    async def add(self, config: ShiftConfiguration) -> ShiftConfiguration:
        raise NotImplementedError


class _SeededShiftConfigRepository(ShiftConfigRepository):
    """A ``ShiftConfigRepository`` with fixed rows — exercises the real config-driven
    resolution path, as opposed to ``_EmptyShiftConfigRepository``'s Settings fallback."""

    def __init__(self, configs: list[ShiftConfiguration]) -> None:
        self._configs = configs

    async def list_all(self) -> list[ShiftConfiguration]:
        return self._configs

    async def get(self, config_id: str) -> ShiftConfiguration | None:
        return next((c for c in self._configs if c.id == config_id), None)

    async def add(self, config: ShiftConfiguration) -> ShiftConfiguration:
        raise NotImplementedError


def _seeded_config(area: str | None, start_hour: int, hours: int = 12) -> ShiftConfiguration:
    """A config row whose ``start_hour`` deliberately differs from the ``Settings``
    default (6) — so a test asserting on it can only pass via the real repo-driven
    path, not by coincidentally matching the Settings-fallback shift too."""
    stamp = datetime(2020, 1, 1, tzinfo=UTC)
    return ShiftConfiguration(
        id=f"cfg-{area or 'plant'}",
        area=area,
        start_hour=start_hour,
        hours=hours,
        overlap_minutes=15,
        effective_from=stamp,
        version=1,
        created_by="admin.user",
        created_at=stamp,
        updated_at=stamp,
    )


def test_shift_starting_exactly_at_start_hour_is_day():
    now = datetime(2026, 7, 30, 6, 0, tzinfo=UTC)
    shift = Shift.resolve(now, START_HOUR, HOURS, OVERLAP)
    assert shift.label == "Day"
    assert shift.shift_id == "20260730-D"
    assert shift.starts_at == datetime(2026, 7, 30, 6, 0, tzinfo=UTC)
    assert shift.ends_at == datetime(2026, 7, 30, 18, 0, tzinfo=UTC)
    assert shift.overlap_minutes == OVERLAP


def test_just_before_day_ends_is_still_day():
    now = datetime(2026, 7, 30, 17, 59, tzinfo=UTC)
    shift = Shift.resolve(now, START_HOUR, HOURS, OVERLAP)
    assert shift.label == "Day"


def test_shift_starting_exactly_at_night_boundary_is_night():
    now = datetime(2026, 7, 30, 18, 0, tzinfo=UTC)
    shift = Shift.resolve(now, START_HOUR, HOURS, OVERLAP)
    assert shift.label == "Night"
    assert shift.shift_id == "20260730-N"
    assert shift.starts_at == datetime(2026, 7, 30, 18, 0, tzinfo=UTC)
    assert shift.ends_at == datetime(2026, 7, 31, 6, 0, tzinfo=UTC)


def test_before_start_hour_belongs_to_previous_days_night_shift():
    now = datetime(2026, 7, 30, 5, 0, tzinfo=UTC)
    shift = Shift.resolve(now, START_HOUR, HOURS, OVERLAP)
    assert shift.label == "Night"
    assert shift.starts_at == datetime(2026, 7, 29, 18, 0, tzinfo=UTC)
    assert shift.ends_at == datetime(2026, 7, 30, 6, 0, tzinfo=UTC)


def test_custom_shift_hours_and_start_are_respected():
    now = datetime(2026, 7, 30, 9, 0, tzinfo=UTC)
    shift = Shift.resolve(now, start_hour=8, hours=4, overlap_minutes=10)
    # 08:00-12:00, 12:00-16:00, 16:00-20:00, 20:00-08:00(next day) -> 09:00 falls in 08:00-12:00
    assert shift.starts_at == datetime(2026, 7, 30, 8, 0, tzinfo=UTC)
    assert shift.ends_at == datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    assert shift.overlap_minutes == 10


def test_get_current_shift_delegates_to_domain_resolve():
    now = datetime(2026, 7, 30, 6, 0, tzinfo=UTC)
    settings = get_settings()
    shift = get_current_shift(settings, now=now)
    expected = Shift.resolve(
        now, settings.shift_start_hour, settings.shift_hours, settings.shift_overlap_minutes
    )
    assert shift == expected


# --- regression: hours != 12 must not collide on shift_id (ES-309 bug fix) -----------


def test_twelve_hour_shifts_still_use_day_night_ids():
    """Unchanged behaviour: hours=12 keeps the original "-D"/"-N" labelling."""
    day = Shift.resolve(datetime(2026, 7, 30, 6, 0, tzinfo=UTC), START_HOUR, HOURS, OVERLAP)
    night = Shift.resolve(datetime(2026, 7, 30, 18, 0, tzinfo=UTC), START_HOUR, HOURS, OVERLAP)
    assert day.shift_id == "20260730-D"
    assert night.shift_id == "20260730-N"


def test_eight_hour_shifts_yield_three_distinct_ids_per_day():
    """hours=8 -> 3 windows/day; each must resolve to its own, distinct shift_id."""
    s1 = Shift.resolve(datetime(2026, 7, 30, 6, 0, tzinfo=UTC), START_HOUR, 8, OVERLAP)
    s2 = Shift.resolve(datetime(2026, 7, 30, 14, 0, tzinfo=UTC), START_HOUR, 8, OVERLAP)
    s3 = Shift.resolve(datetime(2026, 7, 30, 22, 0, tzinfo=UTC), START_HOUR, 8, OVERLAP)
    ids = {s1.shift_id, s2.shift_id, s3.shift_id}
    assert len(ids) == 3
    assert ids == {"20260730-S1", "20260730-S2", "20260730-S3"}
    assert [s1.label, s2.label, s3.label] == ["S1", "S2", "S3"]


# --- resolve_current_shift (ES-309) ---------------------------------------------------


async def test_resolve_current_shift_falls_back_to_settings_when_repo_is_empty():
    settings = get_settings()
    now = datetime(2026, 7, 30, 6, 0, tzinfo=UTC)
    shift, resolved_area = await resolve_current_shift(
        _EmptyShiftConfigRepository(), settings, now=now, area=None
    )
    assert shift == get_current_shift(settings, now=now)
    assert resolved_area is None


async def test_resolve_current_shift_uses_plant_wide_row_when_one_is_effective():
    """A plant-wide row in the repo must actually drive resolution, not just happen to
    be present while the Settings fallback silently does the real work."""
    settings = get_settings()
    now = datetime(2026, 7, 30, 6, 0, tzinfo=UTC)
    plant_wide = _seeded_config(area=None, start_hour=7)
    repo = _SeededShiftConfigRepository([plant_wide])

    shift, resolved_area = await resolve_current_shift(repo, settings, now=now, area=None)

    assert shift == Shift.from_config(plant_wide, now)
    assert shift != get_current_shift(settings, now=now)  # proves the repo path, not fallback
    assert resolved_area is None


async def test_resolve_current_shift_uses_area_specific_row_when_present():
    """An area-specific row takes precedence over the plant-wide row for that area,
    and the resolved area reported back must be the requested area, since it was
    actually the row that produced the shift."""
    settings = get_settings()
    now = datetime(2026, 7, 30, 6, 0, tzinfo=UTC)
    plant_wide = _seeded_config(area=None, start_hour=7)
    train1 = _seeded_config(area="Train 1", start_hour=8, hours=8)
    repo = _SeededShiftConfigRepository([plant_wide, train1])

    shift, resolved_area = await resolve_current_shift(repo, settings, now=now, area="Train 1")

    assert shift == Shift.from_config(train1, now)
    assert resolved_area == "Train 1"


async def test_resolve_current_shift_reports_none_when_requested_area_has_no_config_of_its_own():
    """The resolved area must reflect what actually produced the shift, not the lookup
    key the caller asked for. Asking for an area that has no configuration of its own
    falls back to the plant-wide row — the returned area must say so (``None``), not
    echo back the requested area. Uses a plant-wide row that's actually present (not an
    empty repo) so the fallback-within-a-populated-repo branch is what's exercised.
    """
    settings = get_settings()
    now = datetime(2026, 7, 30, 6, 0, tzinfo=UTC)
    plant_wide = _seeded_config(area=None, start_hour=7)
    repo = _SeededShiftConfigRepository([plant_wide])

    shift, resolved_area = await resolve_current_shift(repo, settings, now=now, area="Train 1")

    assert shift == Shift.from_config(plant_wide, now)
    assert resolved_area is None
