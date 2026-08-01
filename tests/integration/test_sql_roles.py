"""SQL role-repository integration tests.

Exercises the real production path — ``SqlRoleRepository`` + the hash-chained audit
writer sharing one transaction via ``SqlRoleUnitOfWork`` — against an in-memory SQLite
database, so no SQL Server is required. Skips if SQLAlchemy/aiosqlite are not installed.
"""

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
from src.application.admin.manage_roles import (  # noqa: E402
    create_custom_role,
    delete_custom_role,
    list_roles,
    update_custom_role,
)
from src.infrastructure.audit.audit_reader import SqlAuditReader  # noqa: E402
from src.infrastructure.audit.audit_writer import verify_chain  # noqa: E402
from src.infrastructure.persistence.tables import audit_log, metadata  # noqa: E402
from src.infrastructure.persistence.unit_of_work import SqlRoleUnitOfWork  # noqa: E402


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


async def test_create_persists_and_audits(sessionmaker):
    async with SqlRoleUnitOfWork(sessionmaker) as uow:
        created = await create_custom_role(
            uow.roles,
            name="train1_operator",
            permissions=["action:read"],
            ad_groups=["OLNG-ELOG-TRAIN1"],
            area_scope=["Train 1"],
            audit=uow.audit,
            actor="admin.user",
        )

    async with SqlRoleUnitOfWork(sessionmaker) as uow:
        roles = await list_roles(uow.roles)
    assert any(r.id == created.id and r.name == "train1_operator" for r in roles)

    async with sessionmaker() as s:
        assert await verify_chain(s) is True
        rows = (await s.execute(audit_log.select())).all()
    assert len(rows) == 1
    assert rows[0]._mapping["action"] == "role.create"
    assert rows[0]._mapping["actor"] == "admin.user"


async def test_update_and_delete_persist_and_extend_chain(sessionmaker):
    async with SqlRoleUnitOfWork(sessionmaker) as uow:
        created = await create_custom_role(
            uow.roles,
            name="temp_role",
            permissions=["action:read"],
            ad_groups=["G1"],
            audit=uow.audit,
            actor="admin.user",
        )
    async with SqlRoleUnitOfWork(sessionmaker) as uow:
        updated = await update_custom_role(
            uow.roles,
            created.id,
            permissions=["action:read", "action:write"],
            audit=uow.audit,
            actor="admin.user",
        )
    assert updated.permissions == ["action:read", "action:write"]

    async with SqlRoleUnitOfWork(sessionmaker) as uow:
        await delete_custom_role(uow.roles, created.id, audit=uow.audit, actor="admin.user")

    async with SqlRoleUnitOfWork(sessionmaker) as uow:
        roles = await list_roles(uow.roles)
    assert all(r.id != created.id for r in roles)

    async with sessionmaker() as s:
        assert await verify_chain(s) is True
        rows = (await s.execute(audit_log.select().order_by(audit_log.c.seq))).all()
    assert [r._mapping["action"] for r in rows] == ["role.create", "role.update", "role.delete"]


async def test_get_for_groups_resolves_across_roles(sessionmaker):
    async with SqlRoleUnitOfWork(sessionmaker) as uow:
        await create_custom_role(
            uow.roles,
            name="area_a",
            permissions=["action:read"],
            ad_groups=["GROUP-A"],
            area_scope=["Area A"],
            audit=uow.audit,
        )
        await create_custom_role(
            uow.roles,
            name="area_b",
            permissions=["action:write"],
            ad_groups=["GROUP-B"],
            area_scope=["Area B"],
            audit=uow.audit,
        )

    async with SqlRoleUnitOfWork(sessionmaker) as uow:
        matched = await uow.roles.get_for_groups(["GROUP-A", "GROUP-B", "UNRELATED"])
    assert {r.name for r in matched} == {"area_a", "area_b"}


async def test_role_history_reads_back_most_recent_first(sessionmaker):
    async with SqlRoleUnitOfWork(sessionmaker) as uow:
        created = await create_custom_role(
            uow.roles,
            name="history_role",
            permissions=["action:read"],
            ad_groups=["G-HIST"],
            audit=uow.audit,
            actor="admin.user",
        )
    async with SqlRoleUnitOfWork(sessionmaker) as uow:
        await update_custom_role(
            uow.roles,
            created.id,
            permissions=["action:read", "action:write"],
            audit=uow.audit,
            actor="admin.user",
        )
    async with SqlRoleUnitOfWork(sessionmaker) as uow:
        await delete_custom_role(uow.roles, created.id, audit=uow.audit, actor="admin.user")

    async with sessionmaker() as s:
        entries = await SqlAuditReader(s).list_for_entity("role", created.id)

    assert [e.action for e in entries] == ["role.delete", "role.update", "role.create"]
    assert all(e.actor == "admin.user" for e in entries)
    assert entries[-1].payload["ad_groups"] == ["G-HIST"]


async def test_role_history_survives_deletion(sessionmaker):
    """A deleted role's mapping history is still governed configuration — stays readable."""
    async with SqlRoleUnitOfWork(sessionmaker) as uow:
        created = await create_custom_role(
            uow.roles,
            name="gone_role",
            permissions=["action:read"],
            ad_groups=["G-GONE"],
            audit=uow.audit,
        )
    async with SqlRoleUnitOfWork(sessionmaker) as uow:
        await delete_custom_role(uow.roles, created.id, audit=uow.audit)
        assert await uow.roles.get(created.id) is None

    async with sessionmaker() as s:
        entries = await SqlAuditReader(s).list_for_entity("role", created.id)
    assert len(entries) == 2


async def test_role_history_unknown_entity_returns_empty(sessionmaker):
    async with sessionmaker() as s:
        entries = await SqlAuditReader(s).list_for_entity("role", "never-existed")
    assert entries == []


async def test_duplicate_ad_group_rejected(sessionmaker):
    async with SqlRoleUnitOfWork(sessionmaker) as uow:
        await create_custom_role(
            uow.roles,
            name="first",
            permissions=["action:read"],
            ad_groups=["SHARED-GROUP"],
            audit=uow.audit,
        )
    with pytest.raises(ConflictError):
        async with SqlRoleUnitOfWork(sessionmaker) as uow:
            await create_custom_role(
                uow.roles,
                name="second",
                permissions=["action:read"],
                ad_groups=["SHARED-GROUP"],
                audit=uow.audit,
            )
