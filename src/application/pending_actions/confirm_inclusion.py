"""Use case: a Supervisor confirms an AI-suggested candidate as a real action (ES-343).

ES-341's extraction is stateless — candidates are never persisted, so there is no
server-side candidate to reference by id. This is the other half of the "suggested by
ai-service, confirmed by a supervisor" flow (see ``Source.AI_EXTRACTED``): the caller's
own accepted candidate fields come back in, a real ``PendingAction`` is created with
``source`` forced to ``ai`` (never caller-controlled — that's the whole point of this
endpoint existing separately from plain capture), and the audit trail records the
inclusion decision distinctly from an ordinary manual capture.

Persist-and-audit is identical to ``capture_action`` in every way except the forced
``source`` and the audit event name, so this delegates to it rather than duplicating the
create/persist/audit-payload shape — a future change to that shape (a new field, a
different payload key) only needs to happen once.
"""

from src.application.audit.recorder import AuditRecorder
from src.application.pending_actions.create_action import capture_action
from src.application.pending_actions.repository import PendingActionRepository
from src.domain.pending_actions.entities import PendingAction, Priority, Source


async def confirm_inclusion(
    repo: PendingActionRepository,
    issue: str,
    priority: Priority,
    area: str | None = None,
    equipment: str | None = None,
    audit: AuditRecorder | None = None,
    actor: str = "system",
) -> PendingAction:
    """Persist a Supervisor-confirmed, AI-sourced candidate as a real pending action."""
    return await capture_action(
        repo,
        issue=issue,
        priority=priority,
        source=Source.AI_EXTRACTED,
        area=area,
        equipment=equipment,
        audit=audit,
        actor=actor,
        audit_action="pending_action.confirm_inclusion",
    )
