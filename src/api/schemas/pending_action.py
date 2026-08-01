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
    """Capture a new pending action."""

    issue: str = Field(min_length=1, max_length=1000)
    priority: Priority = Priority.MEDIUM
    source: Source = Source.MANUAL
    area: str | None = None
    equipment: str | None = None
    owner: str | None = None
    due_date: date | None = None


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
