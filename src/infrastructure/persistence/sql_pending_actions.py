"""MS SQL / SQLAlchemy pending-action repository.

Implements the ``PendingActionRepository`` port with SQLAlchemy Core over one injected
``AsyncSession``. It does **not** commit — the unit of work owns the transaction so the
action write and its audit row commit atomically. Swapping this in for the in-memory
adapter is a configuration change (``ELOG_PERSISTENCE_BACKEND=sql``); the use cases and
API are untouched, which is the point of the port.
"""

from typing import Any

from sqlalchemy import Row, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.pending_actions.repository import ActionFilter, PendingActionRepository
from src.domain.pending_actions.entities import (
    PendingAction,
    PendingActionStatus,
    Priority,
    Source,
)
from src.infrastructure.persistence.tables import pending_actions


def _to_values(action: PendingAction) -> dict[str, Any]:
    """Entity -> column values (enum members store as their string value)."""
    return {
        "id": action.id,
        "issue": action.issue,
        "priority": action.priority.value,
        "status": action.status.value,
        "source": action.source.value,
        "area": action.area,
        "equipment": action.equipment,
        "owner": action.owner,
        "due_date": action.due_date,
        "created_at": action.created_at,
        "updated_at": action.updated_at,
    }


def _to_entity(row: Row) -> PendingAction:
    """Row -> domain entity."""
    m = row._mapping
    return PendingAction(
        id=m["id"],
        issue=m["issue"],
        priority=Priority(m["priority"]),
        status=PendingActionStatus(m["status"]),
        source=Source(m["source"]),
        area=m["area"],
        equipment=m["equipment"],
        owner=m["owner"],
        due_date=m["due_date"],
        created_at=m["created_at"],
        updated_at=m["updated_at"],
    )


class SqlPendingActionRepository(PendingActionRepository):
    """Persistence adapter over an injected async session (no autocommit)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, action: PendingAction) -> PendingAction:
        await self._session.execute(insert(pending_actions).values(**_to_values(action)))
        return action

    async def get(self, action_id: str) -> PendingAction | None:
        result = await self._session.execute(
            select(pending_actions).where(pending_actions.c.id == action_id)
        )
        row = result.first()
        return _to_entity(row) if row is not None else None

    async def update(self, action: PendingAction) -> PendingAction:
        values = _to_values(action)
        values.pop("id")
        await self._session.execute(
            update(pending_actions).where(pending_actions.c.id == action.id).values(**values)
        )
        return action

    async def list(self, filters: ActionFilter) -> list[PendingAction]:
        stmt = select(pending_actions)
        c = pending_actions.c
        if filters.status is not None:
            stmt = stmt.where(c.status == filters.status.value)
        if filters.owner is not None:
            stmt = stmt.where(c.owner == filters.owner)
        if filters.area is not None:
            stmt = stmt.where(c.area == filters.area)
        if filters.equipment is not None:
            stmt = stmt.where(c.equipment == filters.equipment)
        if filters.priority is not None:
            stmt = stmt.where(c.priority == filters.priority.value)
        if filters.created_from is not None:
            stmt = stmt.where(c.created_at >= filters.created_from)
        if filters.created_to is not None:
            stmt = stmt.where(c.created_at < filters.created_to)
        stmt = stmt.order_by(c.created_at.desc())
        result = await self._session.execute(stmt)
        return [_to_entity(row) for row in result.all()]
