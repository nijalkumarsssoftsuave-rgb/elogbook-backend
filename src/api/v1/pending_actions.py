"""Pending-action endpoints.

Capture, list, fetch and transition follow-up actions. Assignment and lifecycle
tracking are available only when the Administrator enables the action workflow
(BRD FR-PA-05) — enforced here via the ``action_workflow_enabled`` setting.

Every request runs inside a unit of work; mutations write a hash-chained audit entry in
the same transaction as the change (see ``get_pending_action_uow``).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.api.deps import Config, PendingActionUoW, require_permission
from src.api.errors.exceptions import ForbiddenError, NotFoundError
from src.api.schemas.pending_action import (
    ActionResponse,
    CreateActionRequest,
    TransitionRequest,
)
from src.application.pending_actions.create_action import capture_action
from src.application.pending_actions.list_actions import get_action, list_actions
from src.application.pending_actions.repository import ActionFilter
from src.application.pending_actions.transition_action import transition_action
from src.core.logging import correlation_id_ctx
from src.core.response import ok
from src.domain.pending_actions.entities import PendingActionStatus, Priority
from src.infrastructure.auth.token_validator import Principal

router = APIRouter(prefix="/pending-actions", tags=["pending-actions"])


def _cid() -> str:
    return correlation_id_ctx.get()


def _in_scope(area: str | None, area_scope: list[str] | None) -> bool:
    """Full-plant (``area_scope=None``) sees everything; a scoped role only its areas."""
    return area_scope is None or area in area_scope


@router.get("")
async def list_pending_actions(
    uow: PendingActionUoW,
    user: Annotated[Principal, Depends(require_permission("action:read"))],
    status: Annotated[PendingActionStatus | None, Query()] = None,
    owner: Annotated[str | None, Query()] = None,
    area: Annotated[str | None, Query()] = None,
    equipment: Annotated[str | None, Query()] = None,
    priority: Annotated[Priority | None, Query()] = None,
) -> dict:
    """List pending actions with optional filters, restricted to the caller's area scope."""
    actions = await list_actions(
        uow.actions,
        ActionFilter(status=status, owner=owner, area=area, equipment=equipment, priority=priority),
    )
    visible = [a for a in actions if _in_scope(a.area, user.area_scope)]
    return ok([ActionResponse.of(a).model_dump() for a in visible], correlation_id=_cid())


@router.get("/{action_id}")
async def get_pending_action(
    action_id: str,
    uow: PendingActionUoW,
    user: Annotated[Principal, Depends(require_permission("action:read"))],
) -> dict:
    """Fetch a single pending action, if it is within the caller's area scope."""
    action = await get_action(uow.actions, action_id)
    if action is None or not _in_scope(action.area, user.area_scope):
        raise NotFoundError(f"Pending action {action_id} was not found.")
    return ok(ActionResponse.of(action).model_dump(), correlation_id=_cid())


@router.post("")
async def create_pending_action(
    body: CreateActionRequest,
    uow: PendingActionUoW,
    config: Config,
    user: Annotated[Principal, Depends(require_permission("action:write"))],
) -> dict:
    """Capture a pending action.

    Assigning an owner or due date requires the Admin-enabled action workflow.
    """
    if (body.owner or body.due_date) and not config.action_workflow_enabled:
        raise ForbiddenError("Assignment is available only when the action workflow is enabled.")
    action = await capture_action(
        uow.actions,
        issue=body.issue,
        priority=body.priority,
        source=body.source,
        area=body.area,
        equipment=body.equipment,
        owner=body.owner,
        due_date=body.due_date,
        audit=uow.audit,
        actor=user.username,
    )
    return ok(ActionResponse.of(action).model_dump(), correlation_id=_cid())


@router.patch("/{action_id}/transition")
async def transition_pending_action(
    action_id: str,
    body: TransitionRequest,
    uow: PendingActionUoW,
    config: Config,
    user: Annotated[Principal, Depends(require_permission("action:write"))],
) -> dict:
    """Move an action to a new lifecycle state (workflow must be enabled)."""
    if not config.action_workflow_enabled:
        raise ForbiddenError("Action tracking is available only when the workflow is enabled.")
    action = await transition_action(
        uow.actions,
        action_id,
        body.target,
        audit=uow.audit,
        actor=user.username,
    )
    return ok(ActionResponse.of(action).model_dump(), correlation_id=_cid())
