"""Audit-history response schema (admin audit-trail views)."""

from typing import Any

from pydantic import BaseModel

from src.application.audit.reader import AuditRecord


class AuditEntryResponse(BaseModel):
    """One audit-trail entry as returned to admin clients."""

    event_id: str
    occurred_at: str
    actor: str
    action: str
    payload: dict[str, Any]

    @staticmethod
    def of(r: AuditRecord) -> "AuditEntryResponse":
        return AuditEntryResponse(
            event_id=r.event_id,
            occurred_at=r.occurred_at.isoformat(),
            actor=r.actor,
            action=r.action,
            payload=r.payload,
        )
