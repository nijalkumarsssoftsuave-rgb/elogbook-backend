"""MS SQL / SQLAlchemy shift-configuration repository.

Implements the ``ShiftConfigRepository`` port with SQLAlchemy Core over one injected
``AsyncSession``. Append-only — only ``add`` mutates; a config change inserts a new
effective-dated version rather than updating one in place (US-008), so there is no
``update``/``delete`` here. Mutating methods do **not** commit — the unit of work owns
the transaction.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Row, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.errors.exceptions import ConflictError
from src.application.shifts.repository import ShiftConfigRepository
from src.domain.shifts.entities import ShiftConfiguration
from src.infrastructure.persistence.tables import shift_configurations


def _to_values(cfg: ShiftConfiguration) -> dict[str, Any]:
    return {
        "id": cfg.id,
        "area": cfg.area,
        "start_hour": cfg.start_hour,
        "hours": cfg.hours,
        "overlap_minutes": cfg.overlap_minutes,
        "effective_from": cfg.effective_from,
        "version": cfg.version,
        "created_by": cfg.created_by,
        "created_at": cfg.created_at,
        "updated_at": cfg.updated_at,
    }


def _as_utc(dt: datetime) -> datetime:
    """Normalise a timestamp read back from the store to tz-aware UTC.

    Independent of how the store round-trips timezones: MS SQL's ``DATETIMEOFFSET``
    preserves the offset, but SQLite (local/CI tests) has no native timezone-aware type
    and hands back a naive ``datetime`` — treated as UTC, since every value this
    repository ever writes is UTC (mirrors ``infrastructure/audit/hashing.py:iso_utc``).
    The domain layer (``ShiftConfiguration.effective_for``) requires tz-aware values to
    compare against other tz-aware instants.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _to_entity(row: Row) -> ShiftConfiguration:
    m = row._mapping
    return ShiftConfiguration(
        id=m["id"],
        area=m["area"],
        start_hour=m["start_hour"],
        hours=m["hours"],
        overlap_minutes=m["overlap_minutes"],
        effective_from=_as_utc(m["effective_from"]),
        version=m["version"],
        created_by=m["created_by"],
        created_at=_as_utc(m["created_at"]),
        updated_at=_as_utc(m["updated_at"]),
    )


class SqlShiftConfigRepository(ShiftConfigRepository):
    """Persistence adapter over an injected async session (no autocommit)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[ShiftConfiguration]:
        result = await self._session.execute(
            select(shift_configurations).order_by(shift_configurations.c.effective_from)
        )
        return [_to_entity(row) for row in result.all()]

    async def get(self, config_id: str) -> ShiftConfiguration | None:
        result = await self._session.execute(
            select(shift_configurations).where(shift_configurations.c.id == config_id)
        )
        row = result.first()
        return _to_entity(row) if row is not None else None

    async def add(self, config: ShiftConfiguration) -> ShiftConfiguration:
        """Insert a new version row.

        The application-level ``expected_version`` check in ``manage_config.py`` is
        optimistic and has a genuine TOCTOU gap under real concurrency: two requests can
        both read the same "previous version" before either commits. The two filtered
        unique indexes on this table (see ``tables.py``) are the actual safety net — a
        second writer racing on the same version (per area, or per plant-wide) gets an
        ``IntegrityError`` here, translated to the same 409 the optimistic check would
        have produced had it seen the write in time.
        """
        try:
            await self._session.execute(insert(shift_configurations).values(**_to_values(config)))
        except IntegrityError as exc:
            raise ConflictError(
                "Another change to this area's shift configuration was committed at the "
                "same time; retry with the latest version."
            ) from exc
        return config
