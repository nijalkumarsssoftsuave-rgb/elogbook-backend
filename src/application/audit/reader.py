"""Audit-reader port — the read side of the audit trail.

Kept separate from ``AuditRecorder`` (write side, ``recorder.py``): almost every use
case only ever writes an audit entry, so ``AuditRecorder`` stays a one-method port.
Only admin history views (BE-US002-1 — viewing the AD-group-to-role mapping's change
history) need to read entries back, so that gets its own narrow port.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class AuditRecord:
    """One persisted audit entry, as read back for display."""

    event_id: str
    occurred_at: datetime
    actor: str
    action: str
    entity_type: str
    entity_id: str
    payload: dict[str, Any]


class AuditReader(ABC):
    """Contract for querying the audit trail."""

    @abstractmethod
    async def list_for_entity(self, entity_type: str, entity_id: str) -> list[AuditRecord]:
        """Every audit entry for one entity, most recent first."""
        ...


class NullAuditReader(AuditReader):
    """No-op reader for backends that do not persist an audit trail (in-memory)."""

    async def list_for_entity(self, entity_type: str, entity_id: str) -> list[AuditRecord]:  # noqa: D102
        return []
