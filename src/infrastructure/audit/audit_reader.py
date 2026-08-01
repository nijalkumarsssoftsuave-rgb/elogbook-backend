"""SQL audit reader — queries ``audit_log`` for one entity's change history.

Read-only counterpart to ``SqlAuditWriter``: no hash-chain writing, just a filtered
select ordered most-recent-first for admin history views (e.g. GET
``/admin/roles/{id}/history``).
"""

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.audit.reader import AuditReader, AuditRecord
from src.infrastructure.persistence.tables import audit_log


class SqlAuditReader(AuditReader):
    """Reads ``audit_log`` rows for one entity, most recent first."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_entity(self, entity_type: str, entity_id: str) -> list[AuditRecord]:
        result = await self._session.execute(
            select(audit_log)
            .where(audit_log.c.entity_type == entity_type, audit_log.c.entity_id == entity_id)
            .order_by(audit_log.c.seq.desc())
        )
        return [
            AuditRecord(
                event_id=row.event_id,
                occurred_at=row.occurred_at,
                actor=row.actor,
                action=row.action,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                payload=json.loads(row.payload),
            )
            for row in result.all()
        ]
