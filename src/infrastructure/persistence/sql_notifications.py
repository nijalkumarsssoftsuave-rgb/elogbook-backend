"""MS SQL / SQLAlchemy notification repository.

Implements the ``NotificationRepository`` port with SQLAlchemy Core over one injected
``AsyncSession``, same pattern as ``sql_pending_actions.py``. Does **not** commit — the
caller's unit of work (or the standalone caller, for notifications fired outside a
request) owns the transaction.
"""

from typing import Any

from sqlalchemy import Row, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.notifications.repository import NotificationRepository
from src.domain.notifications.entities import Notification, NotificationChannel
from src.infrastructure.persistence.tables import notifications


def _to_values(n: Notification) -> dict[str, Any]:
    return {
        "id": n.id,
        "recipient": n.recipient,
        "channel": n.channel.value,
        "subject": n.subject,
        "message": n.message,
        "related_entity_type": n.related_entity_type,
        "related_entity_id": n.related_entity_id,
        "read": n.read,
        "created_at": n.created_at,
    }


def _to_entity(row: Row) -> Notification:
    m = row._mapping
    return Notification(
        id=m["id"],
        recipient=m["recipient"],
        channel=NotificationChannel(m["channel"]),
        subject=m["subject"],
        message=m["message"],
        related_entity_type=m["related_entity_type"],
        related_entity_id=m["related_entity_id"],
        read=m["read"],
        created_at=m["created_at"],
    )


class SqlNotificationRepository(NotificationRepository):
    """Persistence adapter over an injected async session (no autocommit)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, notification: Notification) -> Notification:
        await self._session.execute(insert(notifications).values(**_to_values(notification)))
        return notification

    async def list_for_recipient(self, recipient: str) -> list[Notification]:
        # (created_at, id) desc — a secondary tie-break so rows added in the same
        # instant (e.g. alert_owner's in-app + email pair) sort deterministically,
        # matching InMemoryNotificationRepository.
        stmt = (
            select(notifications)
            .where(notifications.c.recipient == recipient)
            .order_by(notifications.c.created_at.desc(), notifications.c.id.desc())
        )
        result = await self._session.execute(stmt)
        return [_to_entity(row) for row in result.all()]

    async def exists_for_entity(self, related_entity_type: str, related_entity_id: str) -> bool:
        # select(exists().where(...)) generates SELECT EXISTS(...) AS anon_1 — valid on
        # SQLite/Postgres but invalid on MS SQL (EXISTS may only appear inside a WHERE/
        # CASE, not as a selected column). Found live: passed against SQLite in tests,
        # failed with a real syntax error against the actual MS SQL Server. A plain
        # "does any row match" SELECT ... LIMIT 1 is portable across both dialects.
        stmt = (
            select(notifications.c.id)
            .where(
                notifications.c.related_entity_type == related_entity_type,
                notifications.c.related_entity_id == related_entity_id,
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.first() is not None
