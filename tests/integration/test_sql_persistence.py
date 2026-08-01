"""SQL persistence + audit-chain integration tests.

Exercises the real production path — the SQLAlchemy repository and the hash-chained audit
writer sharing one transaction via the unit of work — against an in-memory SQLite database,
so no SQL Server is required. Skips if SQLAlchemy/aiosqlite are not installed.
"""

from datetime import UTC, datetime

import pytest

# The SQLAlchemy async stack needs greenlet's compiled extension; on a box missing the
# VC++ runtime `import greenlet` raises ImportError. Skip the whole module in that case
# (it runs in CI / a properly provisioned environment).
try:
    import aiosqlite  # noqa: F401
    import greenlet  # noqa: F401
    import sqlalchemy  # noqa: F401
except ImportError as exc:  # pragma: no cover - environment-dependent
    pytest.skip(f"SQLAlchemy async stack unavailable: {exc}", allow_module_level=True)

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from src.application.pending_actions.confirm_inclusion import confirm_inclusion  # noqa: E402
from src.application.pending_actions.create_action import capture_action  # noqa: E402
from src.application.pending_actions.list_actions import get_action, list_actions  # noqa: E402
from src.application.pending_actions.repository import ActionFilter  # noqa: E402
from src.application.pending_actions.transition_action import transition_action  # noqa: E402
from src.domain.pending_actions.entities import (  # noqa: E402
    PendingActionStatus,
    Priority,
    Source,
)
from src.infrastructure.audit.audit_writer import verify_chain  # noqa: E402
from src.infrastructure.persistence.tables import audit_log, metadata  # noqa: E402
from src.infrastructure.persistence.unit_of_work import SqlUnitOfWork  # noqa: E402


@pytest.fixture
async def sessionmaker():
    # StaticPool keeps a single connection so the :memory: DB persists across sessions.
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_capture_persists_and_audits(sessionmaker):
    async with SqlUnitOfWork(sessionmaker) as uow:
        created = await capture_action(
            uow.actions,
            issue="Inspect PSV on V-101",
            priority=Priority.HIGH,
            source=Source.MANUAL,
            audit=uow.audit,
            actor="jane.operator",
        )
    action_id = created.id

    # A fresh unit of work sees the committed row (real persistence, not process memory).
    async with SqlUnitOfWork(sessionmaker) as uow:
        fetched = await get_action(uow.actions, action_id)
    assert fetched is not None
    assert fetched.issue == "Inspect PSV on V-101"
    assert fetched.status == PendingActionStatus.OPEN

    async with sessionmaker() as s:
        assert await verify_chain(s) is True
        rows = (await s.execute(audit_log.select())).all()
    assert len(rows) == 1
    assert rows[0]._mapping["action"] == "pending_action.create"
    assert rows[0]._mapping["actor"] == "jane.operator"


async def test_transition_persists_and_extends_chain(sessionmaker):
    async with SqlUnitOfWork(sessionmaker) as uow:
        created = await capture_action(
            uow.actions,
            issue="Calibrate transmitter",
            priority=Priority.MEDIUM,
            source=Source.MANUAL,
            audit=uow.audit,
            actor="sam.super",
        )
    async with SqlUnitOfWork(sessionmaker) as uow:
        moved = await transition_action(
            uow.actions,
            created.id,
            PendingActionStatus.IN_PROGRESS,
            audit=uow.audit,
            actor="sam.super",
        )
    assert moved.status == PendingActionStatus.IN_PROGRESS

    async with SqlUnitOfWork(sessionmaker) as uow:
        fetched = await get_action(uow.actions, created.id)
    assert fetched.status == PendingActionStatus.IN_PROGRESS

    async with sessionmaker() as s:
        assert await verify_chain(s) is True
        rows = (await s.execute(audit_log.select().order_by(audit_log.c.seq))).all()
    assert [r._mapping["action"] for r in rows] == [
        "pending_action.create",
        "pending_action.transition",
    ]
    assert rows[1]._mapping["prev_hash"] == rows[0]._mapping["entry_hash"]  # chain linked


async def test_confirm_inclusion_persists_with_ai_source_and_distinct_audit_action(sessionmaker):
    """ES-343 — a Supervisor's inclusion decision is real, persisted, and traceable."""
    async with SqlUnitOfWork(sessionmaker) as uow:
        created = await confirm_inclusion(
            uow.actions,
            issue="Inspect PSV on V-101",
            priority=Priority.HIGH,
            area="Train 1",
            audit=uow.audit,
            actor="sam.super",
        )
    assert created.source == Source.AI_EXTRACTED

    async with SqlUnitOfWork(sessionmaker) as uow:
        fetched = await get_action(uow.actions, created.id)
    assert fetched.source == Source.AI_EXTRACTED
    assert fetched.status == PendingActionStatus.OPEN

    async with sessionmaker() as s:
        assert await verify_chain(s) is True
        rows = (await s.execute(audit_log.select())).all()
    assert len(rows) == 1
    assert rows[0]._mapping["action"] == "pending_action.confirm_inclusion"
    assert rows[0]._mapping["actor"] == "sam.super"


async def test_rollback_leaves_nothing_persisted(sessionmaker):
    with pytest.raises(RuntimeError):
        async with SqlUnitOfWork(sessionmaker) as uow:
            await capture_action(
                uow.actions,
                issue="doomed",
                priority=Priority.LOW,
                source=Source.MANUAL,
                audit=uow.audit,
                actor="jane.operator",
            )
            raise RuntimeError("boom before commit")

    # Neither the action nor its audit row survived — atomic rollback.
    async with SqlUnitOfWork(sessionmaker) as uow:
        assert await list_actions(uow.actions, ActionFilter()) == []
    async with sessionmaker() as s:
        assert (await s.execute(audit_log.select())).all() == []


async def test_created_at_range_filter_scopes_to_a_shift_window(sessionmaker):
    """ES-344 — the shift-actions report's filter works against real persistence too."""
    async with SqlUnitOfWork(sessionmaker) as uow:
        inside = await capture_action(
            uow.actions, issue="inside", priority=Priority.LOW, source=Source.MANUAL
        )
        outside = await capture_action(
            uow.actions, issue="outside", priority=Priority.LOW, source=Source.MANUAL
        )

    async with SqlUnitOfWork(sessionmaker) as uow:
        inside.created_at = datetime(2026, 7, 30, 10, 0, tzinfo=UTC)
        await uow.actions.update(inside)
        outside.created_at = datetime(2026, 7, 29, 10, 0, tzinfo=UTC)
        await uow.actions.update(outside)

    async with SqlUnitOfWork(sessionmaker) as uow:
        result = await list_actions(
            uow.actions,
            ActionFilter(
                created_from=datetime(2026, 7, 30, 6, 0, tzinfo=UTC),
                created_to=datetime(2026, 7, 30, 18, 0, tzinfo=UTC),
            ),
        )
    assert [a.issue for a in result] == ["inside"]


async def test_list_filters(sessionmaker):
    async with SqlUnitOfWork(sessionmaker) as uow:
        await capture_action(
            uow.actions,
            issue="a",
            priority=Priority.HIGH,
            source=Source.MANUAL,
            area="Train 1",
            audit=uow.audit,
        )
        await capture_action(
            uow.actions,
            issue="b",
            priority=Priority.LOW,
            source=Source.MANUAL,
            area="Utilities",
            audit=uow.audit,
        )
        await confirm_inclusion(
            uow.actions, issue="c", priority=Priority.LOW, area="Utilities", audit=uow.audit
        )

    async with SqlUnitOfWork(sessionmaker) as uow:
        train1 = await list_actions(uow.actions, ActionFilter(area="Train 1"))
        high = await list_actions(uow.actions, ActionFilter(priority=Priority.HIGH))
        all_open = await list_actions(uow.actions, ActionFilter(status=PendingActionStatus.OPEN))
        ai_sourced = await list_actions(uow.actions, ActionFilter(source=Source.AI_EXTRACTED))
    assert [a.issue for a in train1] == ["a"]
    assert [a.issue for a in high] == ["a"]
    assert len(all_open) == 3
    assert [a.issue for a in ai_sourced] == ["c"]
