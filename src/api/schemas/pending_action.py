"""Pending-action request/response schemas."""

from datetime import UTC, date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, field_validator

from src.domain.pending_actions.entities import (
    PendingAction,
    PendingActionStatus,
    Priority,
    Source,
)


def _reject_blank(v: str | None) -> str | None:
    """Reject a whitespace-only value and strip incidental leading/trailing whitespace.

    ``min_length`` alone doesn't catch a whitespace-only value, since Pydantic counts
    raw characters, not stripped content (``"   "`` satisfies ``min_length=1`` on its
    own). Stripping matters beyond cosmetics: ``owner``/``area``/``equipment`` are
    filtered by exact string equality (``in_memory_pending_actions.py``,
    ``sql_pending_actions.py``) — persisting ``"John "`` unstripped would make
    ``?owner=John`` silently return nothing for a record that really does belong to John.
    """
    if v is None:
        return v
    stripped = v.strip()
    if not stripped:
        raise ValueError("must not be blank")
    return stripped


# min_length/max_length=1000 plus the blank check: a required text field that's
# actually required, not just "at least one character, even if it's whitespace."
RequiredIssueField = Annotated[
    str, Field(min_length=1, max_length=1000), AfterValidator(_reject_blank)
]

# max_length=128 matches the real DB column width (area/equipment/owner are
# NVARCHAR(128) — migrations/0001_init.sql) so a value that passes validation here is
# guaranteed to fit at persistence time, not silently truncated or rejected downstream.
OptionalPlantField = Annotated[
    str | None, Field(default=None, max_length=128), AfterValidator(_reject_blank)
]


class CreateActionRequest(BaseModel):
    """Capture a new pending action — always ``source: manual`` (ES-343).

    An AI-sourced action can't be captured through here: that path is
    ``POST /pending-actions/confirm-inclusion``, gated on ``action:confirm``
    (Supervisor+), not the plain ``action:write`` this endpoint checks. Keeping
    ``source`` out of this request entirely makes that structural, not just a runtime
    check that a future caller could pass around.
    """

    issue: RequiredIssueField
    priority: Priority = Priority.MEDIUM
    area: OptionalPlantField = None
    equipment: OptionalPlantField = None
    owner: OptionalPlantField = None
    due_date: date | None = None

    @field_validator("due_date")
    @classmethod
    def _due_date_not_in_the_past(cls, v: date | None) -> date | None:
        # UTC, matching every other date/time computation in this codebase (e.g.
        # PendingAction.is_overdue()) — a naive date.today() would drift by a day
        # from is_overdue()'s notion of "today" near local midnight in non-UTC zones.
        if v is not None and v < datetime.now(UTC).date():
            raise ValueError("due_date must not be in the past")
        return v


class ConfirmInclusionRequest(BaseModel):
    """A Supervisor's decision to include an AI-suggested candidate (ES-343).

    Deliberately mirrors ``CandidateActionResponse`` — the same fields the extract-
    candidates endpoint handed back — not ``CreateActionRequest``: there's no ``source``
    (always ``ai`` here, never caller-controlled) and no ``owner``/``due_date``
    (assignment is a separate, workflow-gated concern, not part of confirming inclusion).
    """

    issue: RequiredIssueField
    priority: Priority = Priority.MEDIUM
    area: OptionalPlantField = None
    equipment: OptionalPlantField = None


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
