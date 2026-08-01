"""Hash-chained audit writer (append-only).

Implements the ``AuditRecorder`` port over an injected async session. Each call appends
one row whose ``entry_hash`` is ``SHA256(prev_hash + canonical(row))``, so the whole
trail is tamper-evident — altering or deleting any past row breaks every hash after it.

Because the session is shared with the mutation's repository, the audit row commits in
the **same transaction** as the action it records (the Phase-0 requirement): either both
persist or neither does. In production the ``audit_log`` table is also an MS SQL
append-only Ledger table (see ``migrations/0001_init.sql``) — a second, engine-level
guarantee on top of this application-level chain.

Concurrency note: ``prev_hash`` is read at write time. Under a single worker (risk
IF-01) writes serialise; multi-writer chain-fork protection is a Phase-7 hardening item
(serialise audit appends / rely on the Ledger's own sequencing).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.audit.recorder import AuditEntry, AuditRecorder
from src.infrastructure.audit.hashing import (
    GENESIS_HASH,
    canonical_json,
    compute_entry_hash,
    iso_utc,
)
from src.infrastructure.persistence.tables import audit_log


class SqlAuditWriter(AuditRecorder):
    """Appends hash-chained rows to ``audit_log`` on the injected session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _last_hash(self) -> str:
        result = await self._session.execute(
            select(audit_log.c.entry_hash).order_by(audit_log.c.seq.desc()).limit(1)
        )
        row = result.first()
        return row[0] if row is not None else GENESIS_HASH

    async def record(self, entry: AuditEntry) -> None:
        prev_hash = await self._last_hash()
        event_id = uuid.uuid4().hex
        occurred_at = datetime.now(UTC)
        payload_json = canonical_json(entry.payload)

        # The hash covers exactly what is stored, so verification recomputes it from the row.
        material = {
            "event_id": event_id,
            "occurred_at": iso_utc(occurred_at),
            "actor": entry.actor,
            "action": entry.action,
            "entity_type": entry.entity_type,
            "entity_id": entry.entity_id,
            "payload": payload_json,
        }
        entry_hash = compute_entry_hash(prev_hash, material)

        await self._session.execute(
            insert(audit_log).values(
                event_id=event_id,
                occurred_at=occurred_at,
                actor=entry.actor,
                action=entry.action,
                entity_type=entry.entity_type,
                entity_id=entry.entity_id,
                payload=payload_json,
                prev_hash=prev_hash,
                entry_hash=entry_hash,
            )
        )


async def verify_chain(session: AsyncSession) -> bool:
    """Recompute the whole chain in order; True if every hash is intact.

    Used by tests now and by the Phase-7 integrity check. Walks ``audit_log`` by ``seq``,
    re-deriving each ``entry_hash`` from its predecessor and stored content.
    """
    result = await session.execute(audit_log.select().order_by(audit_log.c.seq.asc()))
    prev_hash = GENESIS_HASH
    for row in result.all():
        m = row._mapping
        material = {
            "event_id": m["event_id"],
            "occurred_at": iso_utc(m["occurred_at"]),
            "actor": m["actor"],
            "action": m["action"],
            "entity_type": m["entity_type"],
            "entity_id": m["entity_id"],
            "payload": m["payload"],
        }
        expected = compute_entry_hash(prev_hash, material)
        if m["prev_hash"] != prev_hash or m["entry_hash"] != expected:
            return False
        prev_hash = m["entry_hash"]
    return True
