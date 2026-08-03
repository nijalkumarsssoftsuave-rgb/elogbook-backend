"""Notification endpoints (ES-355)."""

from fastapi import APIRouter

from src.api.deps import CurrentUser, NotificationRepositoryDep
from src.api.schemas.notification import NotificationResponse
from src.core.logging import correlation_id_ctx
from src.core.response import ok
from src.domain.notifications.entities import NotificationChannel

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
async def list_my_notifications(user: CurrentUser, repo: NotificationRepositoryDep) -> dict:
    """The caller's own in-app notifications, most recent first.

    Self-scoped by the authenticated username — no extra permission needed beyond being
    signed in, same as ``GET /me``. There's no cross-user notification listing: a
    supervisor can't browse an operator's alerts through this endpoint.

    Only ``in_app`` rows come back. ``email`` rows in the same table are a delivery-audit
    fact ("this email was sent"), not something a user reads inside the app — an email
    is never "read" here, so including it would double-count every alert once a caller
    builds an unread-count badge against this endpoint (found in code review).
    """
    notifications = await repo.list_for_recipient(user.username)
    in_app = [n for n in notifications if n.channel == NotificationChannel.IN_APP]
    return ok(
        [NotificationResponse.of(n).model_dump() for n in in_app],
        correlation_id=correlation_id_ctx.get(),
    )
