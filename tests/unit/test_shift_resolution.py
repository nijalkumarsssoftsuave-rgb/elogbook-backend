"""Unit tests for shift resolution — pure domain rule (BRD FR-HOME-03), no I/O.

Previously only exercised indirectly through ``GET /shifts/current`` at the real wall
clock, so the day/night boundary and previous-day wraparound branches had no
deterministic coverage.
"""
from datetime import UTC, datetime

from src.application.shifts.current_shift import get_current_shift
from src.core.config import get_settings
from src.domain.shifts.entities import Shift

START_HOUR = 6
HOURS = 12
OVERLAP = 15


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
