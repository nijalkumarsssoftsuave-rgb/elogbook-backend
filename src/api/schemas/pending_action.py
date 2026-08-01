"""Pending-action request/response schemas."""

from datetime import date

from pydantic import BaseModel, Field

from src.domain.pending_actions.entities import (
    PendingAction,
    PendingActionStatus,
    Priority,
    Source,
)


class CreateActionRequest(BaseModel):
    """Capture a new pending action — always ``source: manual`` (ES-343).

    An AI-sourced action can't be captured through here: that path is
    ``POST /pending-actions/confirm-inclusion``, gated on ``action:confirm``
    (Supervisor+), not the plain ``action:write`` this endpoint checks. Keeping
    ``source`` out of this request entirely makes that structural, not just a runtime
    check that a future caller could pass around.
    """

    issue: str = Field(min_length=1, max_length=1000)
    priority: Priority = Priority.MEDIUM
    area: str | None = None
    equipment: str | None = None
    owner: str | None = None
    due_date: date | None = None


class ConfirmInclusionRequest(BaseModel):
    """A Supervisor's decision to include an AI-suggested candidate (ES-343).

    Deliberately mirrors ``CandidateActionResponse`` — the same fields the extract-
    candidates endpoint handed back — not ``CreateActionRequest``: there's no ``source``
    (always ``ai`` here, never caller-controlled) and no ``owner``/``due_date``
    (assignment is a separate, workflow-gated concern, not part of confirming inclusion).
    """

    issue: str = Field(min_length=1, max_length=1000)
    priority: Priority = Priority.MEDIUM
    area: str | None = None
    equipment: str | None = None


class TransitionRequest(BaseModel):
    """Move an action to a new lifecycle state."""

    target: PendingActionStatus


class ActionResponse(BaseModel):
    """The pending-action representation returned to clients."""

    id: str
    issue: str
    priority: Priority
    status: PendingActionStatus
    source: Source
    area: str | None
    equipment: str | None
    owner: str | None
    due_date: date | None
    is_overdue: bool
    created_at: str
    updated_at: str

    @staticmethod
    def of(a: PendingAction) -> "ActionResponse":
        return ActionResponse(
            id=a.id,
            issue=a.issue,
            priority=a.priority,
            status=a.status,
            source=a.source,
            area=a.area,
            equipment=a.equipment,
            owner=a.owner,
            due_date=a.due_date,
            is_overdue=a.is_overdue(),
            created_at=a.created_at.isoformat(),
            updated_at=a.updated_at.isoformat(),
        )
