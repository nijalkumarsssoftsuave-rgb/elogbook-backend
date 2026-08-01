"""Unit tests for shift history (US-009 ES-312).

``enumerate_shifts``/``parse_shift_id`` are pure domain rules (no I/O); ``list_shift_history``
is the application-layer use case that wraps them with validation. No new store:
everything here is derived from the versioned ``ShiftConfiguration`` rows introduced by
US-008. Pagination and sort are ES-314 and are tested there.
"""

from datetime import UTC, date, datetime

import pytest

from src.api.errors.exceptions import ValidationError
from src.application.shifts.repository import ShiftConfigRepository
from src.application.shifts.shift_history import (
    ShiftHistoryQuery,
    get_shift_by_id,
    list_shift_history,
)
from src.core.config import Settings
from src.domain.shifts.entities import ShiftConfiguration, enumerate_shifts, parse_shift_id

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def make_config(
    *,
    area: str | None = None,
    start_hour: int = 6,
    hours: int = 12,
    overlap_minutes: int = 15,
    effective_from: datetime = BASE_TIME,
    version: int = 1,
    created_by: str = "system",
) -> ShiftConfiguration:
    return ShiftConfiguration(
        id=f"cfg-{area}-{version}-{effective_from.isoformat()}",
        area=area,
        start_hour=start_hour,
        hours=hours,
        overlap_minutes=overlap_minutes,
        effective_from=effective_from,
        version=version,
        created_by=created_by,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


class _FakeShiftConfigRepository(ShiftConfigRepository):
    def __init__(self, configs: list[ShiftConfiguration]) -> None:
        self._configs = list(configs)

    async def list_all(self) -> list[ShiftConfiguration]:
        return list(self._configs)

    async def get(self, config_id: str) -> ShiftConfiguration | None:
        return next((c for c in self._configs if c.id == config_id), None)

    async def add(self, config: ShiftConfiguration) -> ShiftConfiguration:
        self._configs.append(config)
        return config


def _settings(**overrides) -> Settings:
    return Settings(**overrides)


# --- enumerate_shifts ------------------------------------------------------------------


def test_single_day_two_shift_enumeration_with_correct_ids():
    plant = make_config()
    items = enumerate_shifts(
        [plant],
        datetime(2026, 7, 30, tzinfo=UTC),
        datetime(2026, 7, 31, tzinfo=UTC),
        None,
        default_start_hour=6,
        default_hours=12,
        default_overlap_minutes=15,
    )
    ids = [s.shift_id for s, _ in items]
    assert ids == ["20260730-D", "20260730-N"]


def test_window_straddling_start_is_excluded():
    plant = make_config()
    items = enumerate_shifts(
        [plant],
        datetime(2026, 7, 30, tzinfo=UTC),
        datetime(2026, 7, 31, tzinfo=UTC),
        None,
        default_start_hour=6,
        default_hours=12,
        default_overlap_minutes=15,
    )
    # The night shift starting 7/29 18:00 (straddling window_start) must not appear.
    assert "20260729-N" not in [s.shift_id for s, _ in items]


def test_window_starting_exactly_at_window_end_is_excluded():
    plant = make_config()
    items = enumerate_shifts(
        [plant],
        datetime(2026, 7, 30, 6, 0, tzinfo=UTC),
        datetime(2026, 7, 30, 18, 0, tzinfo=UTC),  # ends exactly at the night boundary
        None,
        default_start_hour=6,
        default_hours=12,
        default_overlap_minutes=15,
    )
    ids = [s.shift_id for s, _ in items]
    assert ids == ["20260730-D"]


def test_window_starting_inside_but_ending_after_window_end_is_included():
    plant = make_config()
    items = enumerate_shifts(
        [plant],
        datetime(2026, 7, 30, 6, 0, tzinfo=UTC),
        datetime(2026, 7, 30, 20, 0, tzinfo=UTC),  # ends mid-night-shift
        None,
        default_start_hour=6,
        default_hours=12,
        default_overlap_minutes=15,
    )
    ids = [s.shift_id for s, _ in items]
    assert ids == ["20260730-D", "20260730-N"]


def test_eight_hour_config_yields_three_shifts_with_s_ids():
    cfg = make_config(hours=8)
    items = enumerate_shifts(
        [cfg],
        datetime(2026, 7, 30, tzinfo=UTC),
        datetime(2026, 7, 31, tzinfo=UTC),
        None,
        default_start_hour=6,
        default_hours=12,
        default_overlap_minutes=15,
    )
    ids = [s.shift_id for s, _ in items]
    assert ids == ["20260730-S1", "20260730-S2", "20260730-S3"]


def test_multi_day_range_strictly_increasing_no_duplicates():
    plant = make_config()
    items = enumerate_shifts(
        [plant],
        datetime(2026, 7, 28, tzinfo=UTC),
        datetime(2026, 8, 1, tzinfo=UTC),
        None,
        default_start_hour=6,
        default_hours=12,
        default_overlap_minutes=15,
    )
    ids = [s.shift_id for s, _ in items]
    starts = [s.starts_at for s, _ in items]
    assert len(ids) == 8  # 4 days x 2 shifts
    assert len(set(ids)) == 8
    assert starts == sorted(starts)


def test_config_change_exactly_on_shift_boundary_is_honoured_cleanly():
    """A config change effective exactly at a boundary shared by both the old and new
    grid (midnight-aligned start_hour=6 for both) transitions with no gap and no
    overlap — Day/Night under v1 through the 30th, the new 8h grid cleanly picking up
    at 06:00 on the 31st.
    """
    plant_v1 = make_config(effective_from=BASE_TIME, start_hour=6, hours=12, version=1)
    plant_v2 = make_config(
        effective_from=datetime(2026, 7, 31, 6, 0, tzinfo=UTC), start_hour=6, hours=8, version=2
    )
    configs = [plant_v1, plant_v2]
    items = enumerate_shifts(
        configs,
        datetime(2026, 7, 30, tzinfo=UTC),
        datetime(2026, 8, 1, tzinfo=UTC),
        None,
        default_start_hour=6,
        default_hours=12,
        default_overlap_minutes=15,
    )
    ids = [s.shift_id for s, _ in items]
    assert ids == ["20260730-D", "20260730-N", "20260731-S1", "20260731-S2", "20260731-S3"]
    night, new_grid_start = items[1][0], items[2][0]
    assert night.ends_at == new_grid_start.starts_at  # no gap, no overlap


def test_mid_shift_config_change_does_not_duplicate_id_or_go_backwards():
    """The critical regression test: a config change landing mid-shift must not produce
    two windows resolving to the same id, nor a starts_at that moves backwards."""
    plant_v1 = make_config(effective_from=BASE_TIME, start_hour=6, hours=12, version=1)
    plant_v2 = make_config(
        effective_from=datetime(2026, 7, 30, 15, 0, tzinfo=UTC), start_hour=8, hours=12, version=2
    )
    configs = [plant_v1, plant_v2]
    items = enumerate_shifts(
        configs,
        datetime(2026, 7, 30, tzinfo=UTC),
        datetime(2026, 7, 31, tzinfo=UTC),
        None,
        default_start_hour=6,
        default_hours=12,
        default_overlap_minutes=15,
    )
    ids = [s.shift_id for s, _ in items]
    starts = [s.starts_at for s, _ in items]
    assert len(ids) == len(set(ids))
    assert starts == sorted(starts)
    assert ids == ["20260730-D", "20260730-N"]
    day, night = (s for s, _ in items)
    assert night.starts_at == datetime(2026, 7, 30, 20, 0, tzinfo=UTC)
    assert night.starts_at > day.ends_at  # a deliberate gap, not an overlap


def test_enumeration_is_independent_of_the_requested_window_start():
    """A shift already in progress at ``window_start`` must resolve identically no
    matter which window a caller asks for — a wide multi-day list and a single day's
    window must agree on exactly the same windows for the same instants.
    """
    plant = make_config(effective_from=BASE_TIME, start_hour=6, hours=12, version=1)
    changed = make_config(
        effective_from=datetime(2026, 7, 31, 21, 0, tzinfo=UTC), start_hour=3, hours=8, version=2
    )
    configs = [plant, changed]
    kwargs = {"default_start_hour": 6, "default_hours": 12, "default_overlap_minutes": 15}

    multi_day = enumerate_shifts(
        configs, datetime(2026, 7, 30, tzinfo=UTC), datetime(2026, 8, 2, tzinfo=UTC), None, **kwargs
    )
    single_day_31 = enumerate_shifts(
        configs, datetime(2026, 7, 31, tzinfo=UTC), datetime(2026, 8, 1, tzinfo=UTC), None, **kwargs
    )

    ids = [s.shift_id for s, _ in multi_day]
    assert len(ids) == len(set(ids))
    for (s1, _), (s2, _) in zip(multi_day, multi_day[1:], strict=False):
        assert s1.ends_at <= s2.starts_at

    multi_day_31 = [(s, a) for s, a in multi_day if s.starts_at.date().isoformat() == "2026-07-31"]
    assert single_day_31 == multi_day_31


def test_area_specific_config_effective_partway_flips_resolved_area():
    plant = make_config(area=None, effective_from=BASE_TIME, version=1)
    train1 = make_config(
        area="Train 1",
        effective_from=datetime(2026, 7, 3, 6, 0, tzinfo=UTC),  # a clean shift boundary
        overlap_minutes=30,
        version=1,
    )
    configs = [plant, train1]
    items = enumerate_shifts(
        configs,
        datetime(2026, 7, 2, tzinfo=UTC),
        datetime(2026, 7, 4, tzinfo=UTC),
        "Train 1",
        default_start_hour=6,
        default_hours=12,
        default_overlap_minutes=15,
    )
    resolved_areas = [a for _, a in items]
    # Before Train 1's config exists, falls back to plant-wide (None); after, it's "Train 1".
    assert resolved_areas[0] is None
    assert resolved_areas[-1] == "Train 1"


def test_area_with_no_config_of_its_own_resolves_to_none_for_every_item():
    plant = make_config(area=None, effective_from=BASE_TIME, version=1)
    items = enumerate_shifts(
        [plant],
        datetime(2026, 7, 30, tzinfo=UTC),
        datetime(2026, 7, 31, tzinfo=UTC),
        "Train 1",
        default_start_hour=6,
        default_hours=12,
        default_overlap_minutes=15,
    )
    assert all(a is None for _, a in items)


def test_empty_config_list_falls_back_to_settings_defaults():
    items = enumerate_shifts(
        [],
        datetime(2026, 7, 30, tzinfo=UTC),
        datetime(2026, 7, 31, tzinfo=UTC),
        None,
        default_start_hour=6,
        default_hours=12,
        default_overlap_minutes=15,
    )
    ids = [s.shift_id for s, _ in items]
    assert ids == ["20260730-D", "20260730-N"]


def test_all_configs_future_dated_falls_back_to_defaults_across_whole_range():
    future = make_config(effective_from=datetime(2027, 1, 1, tzinfo=UTC))
    items = enumerate_shifts(
        [future],
        datetime(2026, 7, 30, tzinfo=UTC),
        datetime(2026, 7, 31, tzinfo=UTC),
        None,
        default_start_hour=6,
        default_hours=12,
        default_overlap_minutes=15,
    )
    ids = [s.shift_id for s, _ in items]
    assert ids == ["20260730-D", "20260730-N"]


def test_negative_hours_configuration_raises_value_error_without_infinite_loop():
    bad = ShiftConfiguration(
        id="bad",
        area=None,
        start_hour=6,
        hours=-12,  # bypasses validate() — constructed directly
        overlap_minutes=15,
        effective_from=BASE_TIME,
        version=1,
        created_by="system",
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )
    with pytest.raises(ValueError, match="Non-advancing"):
        enumerate_shifts(
            [bad],
            datetime(2026, 7, 30, tzinfo=UTC),
            datetime(2026, 7, 31, tzinfo=UTC),
            None,
            default_start_hour=6,
            default_hours=12,
            default_overlap_minutes=15,
        )


def test_window_end_leq_window_start_returns_empty_list():
    at = datetime(2026, 7, 30, tzinfo=UTC)
    before = datetime(2026, 7, 29, tzinfo=UTC)
    kwargs = {"default_start_hour": 6, "default_hours": 12, "default_overlap_minutes": 15}
    assert enumerate_shifts([], at, at, None, **kwargs) == []  # equal bounds
    assert enumerate_shifts([], at, before, None, **kwargs) == []  # inverted bounds


# --- parse_shift_id ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "shift_id,expected",
    [
        ("20260730-D", date(2026, 7, 30)),
        ("20260730-S3", date(2026, 7, 30)),
    ],
)
def test_parse_shift_id_valid(shift_id, expected):
    assert parse_shift_id(shift_id) == expected


@pytest.mark.parametrize(
    "shift_id",
    ["garbage", "20261332-D", "20260730", "", "-D", "2026073-D"],
)
def test_parse_shift_id_invalid(shift_id):
    assert parse_shift_id(shift_id) is None


# --- list_shift_history (validation + basic filtering) ----------------------------------


async def test_date_from_after_date_to_raises_validation_error():
    repo = _FakeShiftConfigRepository([make_config()])
    query = ShiftHistoryQuery(date_from=date(2026, 7, 31), date_to=date(2026, 7, 30))
    with pytest.raises(ValidationError):
        await list_shift_history(repo, _settings(), query)


async def test_span_exceeding_max_range_days_raises_validation_error():
    repo = _FakeShiftConfigRepository([make_config()])
    query = ShiftHistoryQuery(date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))
    with pytest.raises(ValidationError):
        await list_shift_history(repo, _settings(shift_history_max_range_days=30), query)


async def test_list_shift_history_returns_windows_in_range():
    repo = _FakeShiftConfigRepository([make_config()])
    query = ShiftHistoryQuery(date_from=date(2026, 7, 30), date_to=date(2026, 7, 30))
    items = await list_shift_history(repo, _settings(), query)
    assert [s.shift_id for s, _ in items] == ["20260730-D", "20260730-N"]


async def test_list_shift_history_filters_by_area():
    plant = make_config(area=None, version=1)
    train1 = make_config(
        area="Train 1", effective_from=datetime(2026, 7, 30, 6, 0, tzinfo=UTC), hours=8, version=1
    )
    repo = _FakeShiftConfigRepository([plant, train1])
    query = ShiftHistoryQuery(
        date_from=date(2026, 7, 30), date_to=date(2026, 7, 30), area="Train 1"
    )
    items = await list_shift_history(repo, _settings(), query)
    assert all(a == "Train 1" or a is None for _, a in items)


# --- get_shift_by_id (ES-313) -----------------------------------------------------------


async def test_get_shift_by_id_matches_list_enumeration():
    repo = _FakeShiftConfigRepository([make_config()])
    result = await get_shift_by_id(repo, _settings(), "20260730-D", None)
    assert result is not None
    shift, resolved_area = result
    assert shift.shift_id == "20260730-D"
    assert resolved_area is None


async def test_get_shift_by_id_returns_none_for_unknown_or_malformed_ids():
    repo = _FakeShiftConfigRepository([make_config()])
    assert await get_shift_by_id(repo, _settings(), "20260730-X", None) is None  # no such window
    assert await get_shift_by_id(repo, _settings(), "garbage", None) is None


async def test_get_shift_by_id_matches_list_enumeration_across_config_change():
    """The by-id lookup must agree with what a list query covering the same day would
    have returned, even when a config change happened partway through that day.
    """
    plant_v1 = make_config(effective_from=BASE_TIME, start_hour=6, hours=12, version=1)
    plant_v2 = make_config(
        effective_from=datetime(2026, 7, 30, 15, 0, tzinfo=UTC), start_hour=8, hours=12, version=2
    )
    repo = _FakeShiftConfigRepository([plant_v1, plant_v2])

    listed = await list_shift_history(
        repo, _settings(), ShiftHistoryQuery(date_from=date(2026, 7, 30), date_to=date(2026, 7, 30))
    )
    for shift, resolved_area in listed:
        looked_up = await get_shift_by_id(repo, _settings(), shift.shift_id, None)
        assert looked_up == (shift, resolved_area)


async def test_get_shift_by_id_resolves_area_specific_configuration():
    train1 = make_config(area="Train 1", start_hour=8, hours=8, version=1)
    repo = _FakeShiftConfigRepository([train1])
    result = await get_shift_by_id(repo, _settings(), "20260730-S1", "Train 1")
    assert result is not None
    shift, resolved_area = result
    assert resolved_area == "Train 1"
    assert shift.starts_at.hour == 8
