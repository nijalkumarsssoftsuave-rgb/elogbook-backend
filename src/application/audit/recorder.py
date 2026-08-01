"""Audit-recorder port.

Defined in the application layer so use cases can record an auditable event without
knowing how or where it is stored (clean-architecture dependency rule). The concrete
hash-chained MS SQL writer and the no-op recorder both implement this and are injected.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AuditEntry:
    """One auditable event, produced by a use case at the point of a mutation.

    The writer stamps the event id, timestamp and hash chain — the use case only states
    *who did what to which entity*, plus a snapshot payload for the record.
    """

    actor: str  # username of the acting principal
    action: str  # e.g. "pending_action.create", "pending_action.transition"
    entity_type: str  # e.g. "pending_action"
    entity_id: str
    payload: dict[str, Any] = field(default_factory=dict)


class AuditRecorder(ABC):
    """Contract for appending to the immutable audit trail."""

    @abstractmethod
    async def record(self, entry: AuditEntry) -> None:
        """Append an entry. Runs in the same transaction as the mutation it records."""
        ...


class NullAuditRecorder(AuditRecorder):
    """No-op recorder for backends/tests that do not persist an audit trail."""

    async def record(self, entry: AuditEntry) -> None:  # noqa: D102
        return None
