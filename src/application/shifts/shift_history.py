"""Use case: browse shift history (US-009 — EP-05, ES-312).

Derive, don't store: a shift window is fully determined by the versioned configuration
from US-008 (``ShiftConfiguration``, append-only and effective-dated). This story adds
no new table, no migration, no repository change and no new permission string — it
enumerates windows from the existing configuration versions on every request via
``domain.shifts.entities.enumerate_shifts``. Pagination and sorting are ES-314.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from src.api.errors.exceptions import ValidationError
from src.application.shifts.repository import ShiftConfigRepository
from src.core.config import Settings
from src.domain.shifts.entities import Shift, enumerate_shifts


@dataclass(frozen=True)
class ShiftHistoryQuery:
    """Parameters for a shift-history query.

    ``area`` is already scope-resolved by the API layer (``resolve_query_scope`` +
    ``sole_area``, ES-307) — this use case does not re-check scope.
    """

    date_from: date
    date_to: date
    area: str | None = None


async def list_shift_history(
    repo: ShiftConfigRepository, settings: Settings, query: ShiftHistoryQuery
) -> list[tuple[Shift, str | None]]:
    """List shift windows in ``[date_from, date_to]`` (inclusive UTC calendar days).

    Validates the query first (422 ``ValidationError``): ``date_from`` must not be after
    ``date_to``; the span must not exceed ``settings.shift_history_max_range_days``.
    """
    if query.date_from > query.date_to:
        raise ValidationError("date_from must not be after date_to.")
    span_days = (query.date_to - query.date_from).days
    if span_days > settings.shift_history_max_range_days:
        raise ValidationError(
            f"The requested range spans {span_days} days, exceeding the maximum of "
            f"{settings.shift_history_max_range_days} days."
        )

    window_start = datetime.combine(query.date_from, time.min, tzinfo=UTC)
    window_end = datetime.combine(query.date_to, time.min, tzinfo=UTC) + timedelta(days=1)

    configs = await repo.list_all()
    return enumerate_shifts(
        configs,
        window_start,
        window_end,
        query.area,
        default_start_hour=settings.shift_start_hour,
        default_hours=settings.shift_hours,
        default_overlap_minutes=settings.shift_overlap_minutes,
    )
