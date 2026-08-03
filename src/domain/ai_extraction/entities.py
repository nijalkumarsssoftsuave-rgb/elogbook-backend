"""AI-extraction domain entity — pure business data, no framework or I/O.

A candidate action is a *suggestion*, not a committed ``PendingAction`` (ES-341): the
ai-service proposes it from free text, a supervisor confirms or discards it before it
becomes a real, audited pending action (see ``Source.AI_EXTRACTED`` in
``domain/pending_actions/entities.py``). Nothing here is persisted — extraction is a
stateless read, so this is a plain value object, never stored.
"""

from dataclasses import dataclass

from src.domain.pending_actions.entities import Priority


@dataclass(frozen=True)
class CandidateAction:
    """One AI-suggested action, awaiting a supervisor's confirm/discard decision."""

    issue: str
    priority: Priority
    area: str | None = None
    equipment: str | None = None
    confidence: float | None = None  # 0..1 when the source model provides one
