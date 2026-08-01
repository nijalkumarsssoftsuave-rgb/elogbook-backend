"""Unit tests for the alert-owner use case (ES-355)."""

from datetime import date, timedelta

from src.application.notifications.alert_owner import alert_owner
from src.application.notifications.email_sender import EmailSender
from src.domain.notifications.entities import NotificationChannel
from src.domain.pending_actions.entities import PendingAction, Priority, Source
from src.infrastructure.persistence.in_memory_notifications import (
    InMemoryNotificationRepository,
)


class SpyEmailSender(EmailSender):
    """Records what would have been sent, without any real transport."""

    def __init__(self, raises: bool = False) -> None:
        self.sent: list[tuple[str, str, str]] = []
        self._raises = raises

    async def send(self, to: str, subject: str, body: str) -> None:
        if self._raises:
            raise RuntimeError("SMTP relay unreachable")
        self.sent.append((to, subject, body))


def _overdue_action(owner: str | None) -> PendingAction:
    action = PendingAction.create("Inspect PSV on V-101", Priority.HIGH, Source.MANUAL, owner=owner)
    action.due_date = date.today() - timedelta(days=1)
    return action


async def test_no_owner_is_a_no_op():
    notifications = InMemoryNotificationRepository()
    email_sender = SpyEmailSender()
    action = _overdue_action(owner=None)

    sent = await alert_owner(action, notifications, email_sender)

    assert sent is False
    assert notifications._items == []
    assert email_sender.sent == []


async def test_alerts_owner_in_app_and_by_email():
    notifications = InMemoryNotificationRepository()
    email_sender = SpyEmailSender()
    action = _overdue_action(owner="jane.operator")

    sent = await alert_owner(action, notifications, email_sender)

    assert sent is True
    stored = await notifications.list_for_recipient("jane.operator")
    assert {n.channel for n in stored} == {NotificationChannel.IN_APP, NotificationChannel.EMAIL}
    assert all(n.related_entity_type == "pending_action" for n in stored)
    assert all(n.related_entity_id == action.id for n in stored)
    assert all(n.subject == f"Overdue: {action.issue}" for n in stored)

    assert len(email_sender.sent) == 1
    to, subject, body = email_sender.sent[0]
    assert to == "jane.operator"
    assert subject == f"Overdue: {action.issue}"
    assert action.issue in body


async def test_does_not_alert_a_different_recipient():
    notifications = InMemoryNotificationRepository()
    email_sender = SpyEmailSender()
    action = _overdue_action(owner="jane.operator")

    await alert_owner(action, notifications, email_sender)

    assert await notifications.list_for_recipient("sam.super") == []


async def test_second_call_for_the_same_action_is_a_no_op():
    """Idempotent — a sweep re-run while the action stays overdue must not spam."""
    notifications = InMemoryNotificationRepository()
    email_sender = SpyEmailSender()
    action = _overdue_action(owner="jane.operator")

    first = await alert_owner(action, notifications, email_sender)
    second = await alert_owner(action, notifications, email_sender)

    assert first is True
    assert second is False
    stored = await notifications.list_for_recipient("jane.operator")
    assert len(stored) == 2  # still just the one in_app + one email row, not four
    assert len(email_sender.sent) == 1  # not re-sent


async def test_long_issue_text_is_truncated_in_the_subject():
    """Subject must fit the DB column (NVARCHAR(256)) even though issue allows 1000 chars."""
    notifications = InMemoryNotificationRepository()
    email_sender = SpyEmailSender()
    action = _overdue_action(owner="jane.operator")
    action.issue = "x" * 1000

    await alert_owner(action, notifications, email_sender)

    stored = await notifications.list_for_recipient("jane.operator")
    assert all(len(n.subject) <= 256 for n in stored)
    assert stored[0].subject.startswith("Overdue: ")


async def test_email_failure_still_leaves_the_in_app_alert_recorded():
    """A failed send must not produce a false 'email sent' record.

    And must not prevent the in-app alert (a separate, lower-risk write) from standing.
    """
    notifications = InMemoryNotificationRepository()
    email_sender = SpyEmailSender(raises=True)
    action = _overdue_action(owner="jane.operator")

    try:
        await alert_owner(action, notifications, email_sender)
    except RuntimeError:
        pass

    stored = await notifications.list_for_recipient("jane.operator")
    assert [n.channel for n in stored] == [NotificationChannel.IN_APP]
