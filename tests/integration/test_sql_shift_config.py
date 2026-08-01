"""SQL shift-configuration integration tests (US-008 ES-308/309/311).

Exercises the real production path — ``SqlShiftConfigRepository`` + the hash-chained
audit writer sharing one transaction via ``SqlShiftConfigUnitOfWork`` — against an
in-memory SQLite database, so no SQL Server is required. Skips if SQLAlchemy/aiosqlite
are not installed.
"""

import uuid
from datetime import UTC, datetime

import pytest

try:
    import aiosqlite  # noqa: F401
    import greenlet  # noqa: F401
    import sqlalchemy  # noqa: F401
except ImportError as exc:  # pragma: no cover - environment-dependent
    pytest.skip(f"SQLAlchemy async stack unavailable: {exc}", allow_module_level=True)

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from src.api.errors.exceptions import ConflictError  # noqa: E402
from src.application.admin.manage_config import create_shift_configuration  # noqa: E402
from src.domain.shifts.entities import ShiftConfiguration  # noqa: E402
from src.infrastructure.audit.audit_reader import SqlAuditReader  # noqa: E402
from src.infrastructure.audit.audit_writer import verify_chain  # noqa: E402
from src.infrastructure.persistence.tables import audit_log, metadata  # noqa: E402
from src.infrastructure.persistence.unit_of_work import SqlShiftConfigUnitOfWork  # noqa: E402


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


async def test_create_persists_and_audits_together(sessionmaker):
    async with SqlShiftConfigUnitOfWork(sessionmaker) as uow:
        created = await create_shift_configuration(
            uow,
            area=None,
            start_hour=7,
            hours=12,
            overlap_minutes=20,
            effective_from=datetime(2026, 6, 1, tzinfo=UTC),
            expected_version=0,
            actor="admin.user",
        )

    async with SqlShiftConfigUnitOfWork(sessionmaker) as uow:
        configs = await uow.shift_configs.list_all()
    assert any(c.id == created.id and c.start_hour == 7 for c in configs)

    async with sessionmaker() as s:
        assert await verify_chain(s) is True
        rows = (await s.execute(audit_log.select())).all()
    assert len(rows) == 1
    assert rows[0]._mapping["action"] == "shift_config.create"
    assert rows[0]._mapping["actor"] == "admin.user"
    assert rows[0]._mapping["entity_id"] == "__plant__"


async def test_get_by_id_and_unknown_id(sessionmaker):
    async with SqlShiftConfigUnitOfWork(sessionmaker) as uow:
        created = await create_shift_configuration(
            uow,
            area=None,
            start_hour=7,
            hours=12,
            overlap_minutes=20,
            effective_from=datetime(2026, 6, 1, tzinfo=UTC),
            expected_version=0,
            actor="admin.user",
        )

    async with SqlShiftConfigUnitOfWork(sessionmaker) as uow:
        fetched = await uow.shift_configs.get(created.id)
        missing = await uow.shift_configs.get("does-not-exist")
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.effective_from.tzinfo is not None  # normalised to tz-aware UTC
    assert missing is None


async def test_rollback_on_exception_leaves_nothing_persisted(sessionmaker):
    with pytest.raises(RuntimeError):
        async with SqlShiftConfigUnitOfWork(sessionmaker) as uow:
            await create_shift_configuration(
                uow,
                area=None,
                start_hour=7,
                hours=12,
                overlap_minutes=20,
                effective_from=datetime(2026, 6, 1, tzinfo=UTC),
                expected_version=0,
                actor="admin.user",
            )
            raise RuntimeError("boom before commit")

    async with SqlShiftConfigUnitOfWork(sessionmaker) as uow:
        configs = await uow.shift_configs.list_all()
    assert configs == []
    async with sessionmaker() as s:
        assert (await s.execute(audit_log.select())).all() == []


async def test_conflict_inside_uow_leaves_nothing_persisted(sessionmaker):
    async with SqlShiftConfigUnitOfWork(sessionmaker) as uow:
        await create_shift_configuration(
            uow,
            area=None,
            start_hour=7,
            hours=12,
            overlap_minutes=20,
            effective_from=datetime(2026, 6, 1, tzinfo=UTC),
            expected_version=0,
            actor="admin.user",
        )

    with pytest.raises(ConflictError):
        async with SqlShiftConfigUnitOfWork(sessionmaker) as uow:
            await create_shift_configuration(
                uow,
                area=None,
                start_hour=8,
                hours=12,
                overlap_minutes=20,
                effective_from=datetime(2026, 7, 1, tzinfo=UTC),
                expected_version=99,  # stale
                actor="admin.user",
            )

    async with SqlShiftConfigUnitOfWork(sessionmaker) as uow:
        configs = await uow.shift_configs.list_all()
    assert len(configs) == 1  # only the first, successful create

    async with sessionmaker() as s:
        rows = (await s.execute(audit_log.select())).all()
    assert len(rows) == 1  # only the first, successful create


async def test_audit_entity_id_distinguishes_empty_string_area_from_plant_wide(sessionmaker):
    """``area=""`` is a distinct (if unusual) area key from plant-wide (``area=None``).

    Both ``effective_for``/``_latest_for_area`` compare with ``==``/``is``, so the audit
    trail must not conflate the two under a shared ``"__plant__"`` bucket.
    """
    async with SqlShiftConfigUnitOfWork(sessionmaker) as uow:
        await create_shift_configuration(
            uow,
            area=None,
            start_hour=6,
            hours=12,
            overlap_minutes=15,
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            expected_version=0,
            actor="admin.user",
        )
    async with SqlShiftConfigUnitOfWork(sessionmaker) as uow:
        await create_shift_configuration(
            uow,
            area="",
            start_hour=6,
            hours=12,
            overlap_minutes=15,
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            expected_version=0,
            actor="admin.user",
        )

    async with sessionmaker() as s:
        rows = (await s.execute(audit_log.select())).all()
    entity_ids = {r._mapping["entity_id"] for r in rows}
    assert entity_ids == {"__plant__", ""}


async def test_db_constraint_catches_two_inserts_racing_on_the_same_version(sessionmaker):
    """The real safety net behind ``expected_version``.

    ``create_shift_configuration``'s optimistic check alone has a TOCTOU gap: two
    concurrent callers can both read "previous version = 0" before either commits. Bypass
    that use case entirely and call the repository directly with two rows that both claim
    ``(area=None, version=1)`` — exactly what two such racing callers would produce. The
    ``uq_shift_configurations_plant_version`` filtered index (tables.py) — the one that
    applies when ``area IS NULL`` — must be what actually stops the second one, not
    silently accept a duplicate version.
    """

    def racing_config(start_hour: int) -> ShiftConfiguration:
        now = datetime(2026, 1, 1, tzinfo=UTC)
        return ShiftConfiguration(
            id=uuid.uuid4().hex,
            area=None,
            start_hour=start_hour,
            hours=12,
            overlap_minutes=15,
            effective_from=now,
            version=1,  # both "requests" computed the same next version
            created_by="admin.user",
            created_at=now,
            updated_at=now,
        )

    async with SqlShiftConfigUnitOfWork(sessionmaker) as uow:
        await uow.shift_configs.add(racing_config(start_hour=7))

    with pytest.raises(ConflictError):
        async with SqlShiftConfigUnitOfWork(sessionmaker) as uow:
            await uow.shift_configs.add(racing_config(start_hour=8))

    async with SqlShiftConfigUnitOfWork(sessionmaker) as uow:
        configs = await uow.shift_configs.list_all()
    assert len(configs) == 1
    assert configs[0].start_hour == 7  # the loser never landed


async def test_area_specific_and_plant_wide_rows_coexist(sessionmaker):
    async with SqlShiftConfigUnitOfWork(sessionmaker) as uow:
        await create_shift_configuration(
            uow,
            area=None,
            start_hour=6,
            hours=12,
            overlap_minutes=15,
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            expected_version=0,
            actor="admin.user",
        )
        await create_shift_configuration(
            uow,
            area="Train 1",
            start_hour=8,
            hours=8,
            overlap_minutes=10,
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            expected_version=0,
            actor="admin.user",
        )

    async with SqlShiftConfigUnitOfWork(sessionmaker) as uow:
        configs = await uow.shift_configs.list_all()
    assert {c.area for c in configs} == {None, "Train 1"}

    at = datetime(2026, 6, 1, tzinfo=UTC)
    train1_effective = ShiftConfiguration.effective_for(configs, at, area="Train 1")
    plant_effective = ShiftConfiguration.effective_for(configs, at, area=None)
    other_area_effective = ShiftConfiguration.effective_for(configs, at, area="Train 2")

    assert train1_effective.area == "Train 1"
    assert train1_effective.start_hour == 8
    assert plant_effective.area is None
    assert plant_effective.start_hour == 6
    # Train 2 has no area-specific row -> falls back to the plant-wide row.
    assert other_area_effective.area is None


async def test_historical_resolution_before_and_after_effective_date(sessionmaker):
    """The core guarantee: resolving 'now' picks the version effective at that instant."""
    async with SqlShiftConfigUnitOfWork(sessionmaker) as uow:
        await create_shift_configuration(
            uow,
            area=None,
            start_hour=6,
            hours=12,
            overlap_minutes=15,
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            expected_version=0,
            actor="admin.user",
        )
        await create_shift_configuration(
            uow,
            area=None,
            start_hour=9,
            hours=12,
            overlap_minutes=15,
            effective_from=datetime(2026, 6, 15, tzinfo=UTC),
            expected_version=1,
            actor="admin.user",
        )

    async with SqlShiftConfigUnitOfWork(sessionmaker) as uow:
        configs = await uow.shift_configs.list_all()

    before = ShiftConfiguration.effective_for(
        configs, datetime(2026, 6, 14, 23, 59, tzinfo=UTC), area=None
    )
    on_the_day = ShiftConfiguration.effective_for(
        configs, datetime(2026, 6, 15, 0, 0, tzinfo=UTC), area=None
    )
    after = ShiftConfiguration.effective_for(configs, datetime(2026, 12, 1, tzinfo=UTC), area=None)

    assert before.start_hour == 6
    assert before.version == 1
    assert on_the_day.start_hour == 9
    assert on_the_day.version == 2
    assert after.start_hour == 9
    assert after.version == 2


async def test_history_reads_back_most_recent_first_with_correct_payloads(sessionmaker):
    """Exercises the exact read path ``GET /admin/config/shift/history`` uses
    (``SqlAuditReader.list_for_entity``) against real persisted rows — the create-time
    audit write alone (``test_create_persists_and_audits_together``) doesn't prove the
    history endpoint's own query returns them in the right order with the right content.
    """
    async with SqlShiftConfigUnitOfWork(sessionmaker) as uow:
        first = await create_shift_configuration(
            uow,
            area=None,
            start_hour=6,
            hours=12,
            overlap_minutes=15,
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            expected_version=0,
            actor="admin.user",
        )
    async with SqlShiftConfigUnitOfWork(sessionmaker) as uow:
        second = await create_shift_configuration(
            uow,
            area=None,
            start_hour=9,
            hours=12,
            overlap_minutes=15,
            effective_from=datetime(2026, 6, 15, tzinfo=UTC),
            expected_version=1,
            actor="admin.user",
        )

    async with sessionmaker() as s:
        entries = await SqlAuditReader(s).list_for_entity("shift_config", "__plant__")

    assert [e.payload["version"] for e in entries] == [2, 1]  # most recent first
    assert entries[0].payload["id"] == second.id
    assert entries[0].payload["start_hour"] == 9
    assert entries[1].payload["id"] == first.id
    assert entries[1].payload["start_hour"] == 6
    assert all(e.action == "shift_config.create" for e in entries)
    assert all(e.actor == "admin.user" for e in entries)
