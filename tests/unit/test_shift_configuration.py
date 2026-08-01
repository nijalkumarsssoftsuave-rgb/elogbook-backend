"""Unit tests for the ``ShiftConfiguration`` domain entity (US-008 ES-308).

Pure domain rules — no I/O. ``validate()`` range-checks a single row. Historical
resolution (``effective_for``) is ES-309 and is tested there once it exists.
"""

from datetime import UTC, datetime

import pytest

from src.domain.shifts.entities import ShiftConfiguration

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


# --- validate() ----------------------------------------------------------------------


@pytest.mark.parametrize("start_hour", [-1, 24, 100])
def test_validate_rejects_bad_start_hour(start_hour):
    cfg = make_config(start_hour=start_hour)
    with pytest.raises(ValueError, match="start_hour"):
        cfg.validate()


@pytest.mark.parametrize("hours", [0, -5, 25])
def test_validate_rejects_hours_out_of_range(hours):
    cfg = make_config(hours=hours)
    with pytest.raises(ValueError, match="hours"):
        cfg.validate()


@pytest.mark.parametrize("hours", [5, 7, 9, 10, 11, 13])
def test_validate_rejects_hours_that_do_not_evenly_divide_24(hours):
    cfg = make_config(hours=hours, overlap_minutes=0)
    with pytest.raises(ValueError, match="evenly divide"):
        cfg.validate()


@pytest.mark.parametrize("hours", [1, 2, 3, 4, 6, 8, 12, 24])
def test_validate_accepts_hours_that_evenly_divide_24(hours):
    cfg = make_config(hours=hours, overlap_minutes=0)
    cfg.validate()  # no raise


def test_validate_rejects_negative_overlap():
    cfg = make_config(hours=12, overlap_minutes=-1)
    with pytest.raises(ValueError, match="overlap_minutes"):
        cfg.validate()


def test_validate_rejects_overlap_at_or_above_hours_in_minutes():
    cfg = make_config(hours=12, overlap_minutes=12 * 60)
    with pytest.raises(ValueError, match="overlap_minutes"):
        cfg.validate()


def test_validate_accepts_overlap_just_under_the_full_window():
    cfg = make_config(hours=12, overlap_minutes=12 * 60 - 1)
    cfg.validate()  # no raise


def test_validate_accepts_the_default_configuration():
    make_config().validate()  # no raise


def test_validate_rejects_naive_effective_from():
    naive = datetime(2026, 1, 1)  # no tzinfo
    cfg = make_config(effective_from=naive)
    with pytest.raises(ValueError, match="timezone-aware"):
        cfg.validate()


# --- effective_for ---------------------------------------------------------------------


def test_effective_for_picks_greatest_effective_from_leq_at():
    v1 = make_config(effective_from=datetime(2026, 1, 1, tzinfo=UTC), version=1)
    v2 = make_config(effective_from=datetime(2026, 3, 1, tzinfo=UTC), version=2)
    at = datetime(2026, 6, 1, tzinfo=UTC)
    result = ShiftConfiguration.effective_for([v1, v2], at, area=None)
    assert result is v2


def test_effective_for_ignores_future_rows():
    past = make_config(effective_from=datetime(2026, 1, 1, tzinfo=UTC), version=1)
    future = make_config(effective_from=datetime(2027, 1, 1, tzinfo=UTC), version=2)
    at = datetime(2026, 6, 1, tzinfo=UTC)
    result = ShiftConfiguration.effective_for([past, future], at, area=None)
    assert result is past


def test_effective_for_prefers_area_match_over_plant_wide():
    plant_wide = make_config(area=None, effective_from=datetime(2026, 1, 1, tzinfo=UTC), version=1)
    train1 = make_config(area="Train 1", effective_from=datetime(2026, 2, 1, tzinfo=UTC), version=1)
    at = datetime(2026, 6, 1, tzinfo=UTC)
    result = ShiftConfiguration.effective_for([plant_wide, train1], at, area="Train 1")
    assert result is train1


def test_effective_for_falls_back_to_plant_wide_when_no_area_specific_row():
    plant_wide = make_config(area=None, effective_from=datetime(2026, 1, 1, tzinfo=UTC), version=1)
    train2 = make_config(area="Train 2", effective_from=datetime(2026, 1, 1, tzinfo=UTC), version=1)
    at = datetime(2026, 6, 1, tzinfo=UTC)
    result = ShiftConfiguration.effective_for([plant_wide, train2], at, area="Train 1")
    assert result is plant_wide


def test_effective_for_falls_back_to_plant_wide_when_area_specific_row_not_yet_effective():
    plant_wide = make_config(area=None, effective_from=datetime(2026, 1, 1, tzinfo=UTC), version=1)
    train1_future = make_config(
        area="Train 1", effective_from=datetime(2027, 1, 1, tzinfo=UTC), version=1
    )
    at = datetime(2026, 6, 1, tzinfo=UTC)
    result = ShiftConfiguration.effective_for([plant_wide, train1_future], at, area="Train 1")
    assert result is plant_wide


def test_effective_for_returns_none_when_nothing_is_effective_yet():
    future = make_config(effective_from=datetime(2027, 1, 1, tzinfo=UTC), version=1)
    at = datetime(2026, 6, 1, tzinfo=UTC)
    assert ShiftConfiguration.effective_for([future], at, area=None) is None


def test_effective_for_returns_none_for_empty_list():
    at = datetime(2026, 6, 1, tzinfo=UTC)
    assert ShiftConfiguration.effective_for([], at, area=None) is None
    assert ShiftConfiguration.effective_for([], at, area="Train 1") is None


def test_effective_for_tie_on_effective_from_highest_version_wins():
    same_date = datetime(2026, 1, 1, tzinfo=UTC)
    v1 = make_config(effective_from=same_date, version=1, start_hour=6)
    v2 = make_config(effective_from=same_date, version=2, start_hour=7)
    at = datetime(2026, 6, 1, tzinfo=UTC)
    result = ShiftConfiguration.effective_for([v1, v2], at, area=None)
    assert result is v2
    assert result.start_hour == 7
