"""SQL notification-repository integration tests (ES-355).

Exercises the real production path — ``SqlNotificationRepository`` and ``alert_owner``
against an in-memory SQLite database, so no SQL Server is required. Skips if
SQLAlchemy/aiosqlite are not installed.
"""

import pytest

try:
    import aiosqlite  # noqa: F401
    import greenlet  # noqa: F401
    import sqlalchemy  # noqa: F401
except ImportError as exc:  # pragma: no cover - environment-dependent
    pytest.skip(f"SQLAlchemy async stack unavailable: {exc}", allow_module_level=True)

from datetime import date, timedelta  # noqa: E402

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from src.application.notifications.alert_owner import alert_owner  # noqa: E402
from src.application.notifications.email_sender import EmailSender  # noqa: E402
from src.domain.notifications.entities import NotificationChannel  # noqa: E402
from src.domain.pending_actions.entities import PendingAction, Priority, Source  # noqa: E402
from src.infrastructure.persistence.sql_notifications import SqlNotificationRepository  # noqa: E402
from src.infrastructure.persistence.tables import metadata  # noqa: E402


class SpyEmailSender(EmailSender):
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    async def send(self, to: str, subject: str, body: str) -> None:
        self.sent.append((to, subject, body))


@pytest.fixture
async def sessionmaker():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_alert_owner_persists_both_channels_through_real_sql(sessionmaker):
    action = PendingAction.create(
        "Inspect PSV on V-101", Priority.HIGH, Source.MANUAL, owner="jane.operator"
    )
    action.due_date = date.today() - timedelta(days=1)
    email_sender = SpyEmailSender()

    async with sessionmaker() as session:
        await alert_owner(action, SqlNotificationRepository(session), email_sender)
        await session.commit()

    # a fresh session sees the committed rows (real persistence, not process memory)
    async with sessionmaker() as session:
        stored = await SqlNotificationRepository(session).list_for_recipient("jane.operator")

    assert {n.channel for n in stored} == {NotificationChannel.IN_APP, NotificationChannel.EMAIL}
    assert all(n.related_entity_id == action.id for n in stored)
    assert len(email_sender.sent) == 1


async def test_list_for_recipient_only_returns_that_recipients_rows(sessionmaker):
    jane = PendingAction.create("Issue A", Priority.LOW, Source.MANUAL, owner="jane.operator")
    jane.due_date = date.today() - timedelta(days=1)
    sam = PendingAction.create("Issue B", Priority.LOW, Source.MANUAL, owner="sam.super")
    sam.due_date = date.today() - timedelta(days=1)

    async with sessionmaker() as session:
        repo = SqlNotificationRepository(session)
        await alert_owner(jane, repo, SpyEmailSender())
        await alert_owner(sam, repo, SpyEmailSender())
        await session.commit()

    async with sessionmaker() as session:
        jane_notifications = await SqlNotificationRepository(session).list_for_recipient(
            "jane.operator"
        )
    assert {n.related_entity_id for n in jane_notifications} == {jane.id}


async def test_exists_for_entity_prevents_duplicate_alerts_across_separate_sweeps(sessionmaker):
    """A fresh session/transaction per sweep run (like the real script uses) must still

    see the previous run's committed rows and skip re-alerting.
    """
    action = PendingAction.create(
        "Inspect PSV on V-101", Priority.HIGH, Source.MANUAL, owner="jane.operator"
    )
    action.due_date = date.today() - timedelta(days=1)

    # first "sweep run"
    async with sessionmaker() as session:
        await alert_owner(action, SqlNotificationRepository(session), SpyEmailSender())
        await session.commit()

    # second "sweep run" — same action still overdue, fresh session (as the real
    # sweep script opens per-action), must be a no-op
    second_email_sender = SpyEmailSender()
    async with sessionmaker() as session:
        await alert_owner(action, SqlNotificationRepository(session), second_email_sender)
        await session.commit()

    assert second_email_sender.sent == []
    async with sessionmaker() as session:
        stored = await SqlNotificationRepository(session).list_for_recipient("jane.operator")
    assert len(stored) == 2  # still just the original in_app + email pair
