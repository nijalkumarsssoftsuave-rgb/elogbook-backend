"""Use case: alert an overdue action's owner, in-app and by email (ES-355).

One flat notification per channel when triggered — no separate escalation tier: this
doesn't step up to a supervisor after some delay or re-notify on a growing cadence, it
just tells the owner once, ever, per overdue action (see the idempotency check below).
"""

from src.application.notifications.email_sender import EmailSender
from src.application.notifications.repository import NotificationRepository
from src.domain.notifications.entities import Notification, NotificationChannel
from src.domain.pending_actions.entities import PendingAction

_ENTITY_TYPE = "pending_action"

# "Overdue: " (9 chars) + this must fit inside the subject column (NVARCHAR(256)) with
# room to spare — action.issue itself is validated up to 1000 chars at capture time
# (CreateActionRequest), which would otherwise silently overflow the column and fail
# the insert (found in code review).
_MAX_ISSUE_IN_SUBJECT = 200


def _subject_for(issue: str) -> str:
    truncated = (
        issue if len(issue) <= _MAX_ISSUE_IN_SUBJECT else issue[: _MAX_ISSUE_IN_SUBJECT - 1] + "…"
    )
    return f"Overdue: {truncated}"


async def alert_owner(
    action: PendingAction,
    notifications: NotificationRepository,
    email_sender: EmailSender,
) -> bool:
    """Notify ``action.owner`` in-app and by email that it's overdue.

    A no-op if the action has no owner (nobody to alert) or if it's already been
    alerted for once before (idempotent — a sweep re-run while the same action stays
    overdue must not re-notify every tick; found in code review).

    The in-app row is always recorded first — it's just a local write, low risk of
    failure. The email is sent *before* its own "sent" notification row is persisted,
    so a failed send never produces a false record claiming it succeeded; if
    ``email_sender.send()`` raises, the in-app alert still stands, and the caller
    (the sweep script) decides how to handle the failure without losing that.

    Returns ``True`` if an alert was actually sent, ``False`` if skipped (no owner, or
    already alerted) — so a caller counting "how many owners did I alert this run"
    doesn't count a no-op skip as a real alert.
    """
    if not action.owner:
        return False
    if await notifications.exists_for_entity(_ENTITY_TYPE, action.id):
        return False

    subject = _subject_for(action.issue)
    message = f"'{action.issue}' was due {action.due_date} and is still {action.status.value}."

    await notifications.add(
        Notification.create(
            recipient=action.owner,
            channel=NotificationChannel.IN_APP,
            subject=subject,
            message=message,
            related_entity_type=_ENTITY_TYPE,
            related_entity_id=action.id,
        )
    )

    await email_sender.send(to=action.owner, subject=subject, body=message)

    await notifications.add(
        Notification.create(
            recipient=action.owner,
            channel=NotificationChannel.EMAIL,
            subject=subject,
            message=message,
            related_entity_type=_ENTITY_TYPE,
            related_entity_id=action.id,
        )
    )
    return True
