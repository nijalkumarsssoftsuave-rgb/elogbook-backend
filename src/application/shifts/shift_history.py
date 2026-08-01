"""Use case: browse shift history (US-009 — EP-05, ES-312/313/314).

Derive, don't store: a shift window is fully determined by the versioned configuration
from US-008 (``ShiftConfiguration``, append-only and effective-dated). This story adds
no new table, no migration, no repository change and no new permission string — it
enumerates windows from the existing configuration versions on every request via
``domain.shifts.entities.enumerate_shifts``.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from math import ceil
from typing import Literal

from src.api.errors.exceptions import ValidationError
from src.application.shifts.repository import ShiftConfigRepository
from src.core.config import Settings
from src.domain.shifts.entities import Shift, enumerate_shifts, parse_shift_id


@dataclass(frozen=True)
class ShiftHistoryQuery:
    """Parameters for a shift-history list request.

    ``area`` is already scope-resolved by the API layer (``resolve_query_scope`` +
    ``sole_area``, ES-307) — this use case does not re-check scope. ``sort`` is typed
    as a ``Literal``, not a plain ``str``: the API layer already constrains it the same
    way (``src/api/v1/shifts.py``'s ``Query`` annotation), but this use case must not
    depend on that alone — any other caller gets the same guarantee for free instead of
    a silent fall-through to ascending on an unrecognised value.
    """

    date_from: date
    date_to: date
    area: str | None = None
    page: int = 1
    page_size: int | None = None  # None -> settings default
    sort: Literal["starts_at:asc", "starts_at:desc"] = "starts_at:desc"


@dataclass(frozen=True)
class ShiftHistoryPage:
    """One page of enumerated shift windows."""

    items: list[tuple[Shift, str | None]]
    page: int
    page_size: int
    total: int
    total_pages: int
    sort: str


async def list_shift_history(
    repo: ShiftConfigRepository, settings: Settings, query: ShiftHistoryQuery
) -> ShiftHistoryPage:
    """List shift windows in ``[date_from, date_to]`` (inclusive UTC calendar days), paginated.

    Validates the query first (422 ``ValidationError``): ``date_from`` must not be after
    ``date_to``; the span must not exceed ``settings.shift_history_max_range_days``; an
    explicit ``page_size`` must not exceed ``settings.shift_history_page_size_max``.
    """
    if query.date_from > query.date_to:
        raise ValidationError("date_from must not be after date_to.")
    span_days = (query.date_to - query.date_from).days
    if span_days > settings.shift_history_max_range_days:
        raise ValidationError(
            f"The requested range spans {span_days} days, exceeding the maximum of "
            f"{settings.shift_history_max_range_days} days."
        )
    # Re-validated here, not just trusted from the API layer's Query(ge=1) — same
    # defense-in-depth reasoning as `sort` above: any other caller of this use case
    # gets the same guarantee for free instead of a silently-corrupted slice.
    if query.page < 1:
        raise ValidationError(f"page must be >= 1, got {query.page}.")
    if query.page_size is not None and query.page_size < 1:
        raise ValidationError(f"page_size must be >= 1, got {query.page_size}.")
    if query.page_size is not None and query.page_size > settings.shift_history_page_size_max:
        raise ValidationError(
            f"page_size {query.page_size} exceeds the maximum of "
            f"{settings.shift_history_page_size_max}."
        )

    window_start = datetime.combine(query.date_from, time.min, tzinfo=UTC)
    window_end = datetime.combine(query.date_to, time.min, tzinfo=UTC) + timedelta(days=1)

    configs = await repo.list_all()
    items = enumerate_shifts(
        configs,
        window_start,
        window_end,
        query.area,
        default_start_hour=settings.shift_start_hour,
        default_hours=settings.shift_hours,
        default_overlap_minutes=settings.shift_overlap_minutes,
    )

    if query.sort == "starts_at:desc":
        items = list(reversed(items))

    page_size = query.page_size or settings.shift_history_page_size_default
    total = len(items)
    total_pages = ceil(total / page_size) if total else 0
    start = (query.page - 1) * page_size
    page_items = items[start : start + page_size]

    return ShiftHistoryPage(
        items=page_items,
        page=query.page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
        sort=query.sort,
    )


async def get_shift_by_id(
    repo: ShiftConfigRepository, settings: Settings, shift_id: str, area: str | None
) -> tuple[Shift, str | None] | None:
    """Return the single shift window matching ``shift_id``, or ``None`` if not found.

    The only match path is the full id string against the ids produced by enumerating
    that day — ``parse_shift_id`` narrows the enumeration window (its own calendar day)
    but the window itself is never re-derived from the label.
    """
    day = parse_shift_id(shift_id)
    if day is None:
        return None

    configs = await repo.list_all()
    try:
        window_start = datetime.combine(day, time.min, tzinfo=UTC)
        window_end = window_start + timedelta(days=1)
        items = enumerate_shifts(
            configs,
            window_start,
            window_end,
            area,
            default_start_hour=settings.shift_start_hour,
            default_hours=settings.shift_hours,
            default_overlap_minutes=settings.shift_overlap_minutes,
        )
    except OverflowError:
        # A calendar-valid but implausible year (e.g. 9999 or 1) can push the internal
        # 24h-lookback/1-day-forward window arithmetic past datetime's own MINYEAR/MAXYEAR
        # bounds. No real shift could exist at such a date, so this is honestly a 404,
        # not an unhandled 500 — the whole point of parse_shift_id accepting any
        # calendar-valid date is that this function, not the caller, decides "not found."
        return None

    for shift, resolved_area in items:
        if shift.shift_id == shift_id:
            return shift, resolved_area
    return None
