"""Unit tests for ES-360: audit entries recorded for every admin mutation.

Uses a CapturingAuditRecorder so no DB is needed. Each use case is called directly with
a real in-memory repository; assertions verify the exact action name, entity type, actor,
and payload written to the recorder.
"""

import pytest

from src.application.admin.manage_roles import (
    create_custom_role,
    delete_custom_role,
    update_custom_role,
)
from src.application.admin.manage_users import create_user, delete_user, update_user
from src.application.audit.recorder import AuditEntry, AuditRecorder
from src.domain.users_roles.seed import BASE_ROLES
from src.infrastructure.persistence.in_memory_roles import InMemoryRoleRepository
from src.infrastructure.persistence.in_memory_users import InMemoryUserRepository


class CapturingAuditRecorder(AuditRecorder):
    """Stores every recorded entry in-memory for test assertions."""

    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    async def record(self, entry: AuditEntry) -> None:
        self.entries.append(entry)

    @property
    def last(self) -> AuditEntry:
        return self.entries[-1]


@pytest.fixture
def user_repo():
    return InMemoryUserRepository()


@pytest.fixture
def role_repo():
    repo = InMemoryRoleRepository()
    repo._items = {r.id: r for r in BASE_ROLES}
    return repo


@pytest.fixture
def audit():
    return CapturingAuditRecorder()


# ---------------------------------------------------------------------------
# User audit entries
# ---------------------------------------------------------------------------


async def test_create_user_records_user_create(user_repo, audit):
    await create_user(
        user_repo,
        username="alice",
        display_name="Alice",
        email="alice@x.com",
        audit=audit,
        actor="admin.user",
    )
    assert len(audit.entries) == 1
    e = audit.last
    assert e.action == "user.create"
    assert e.entity_type == "user"
    assert e.actor == "admin.user"
    assert e.payload["username"] == "alice"
    assert e.payload["email"] == "alice@x.com"
    assert e.payload["role_id"] is None


async def test_create_user_records_role_id_in_payload(user_repo, audit):
    await create_user(
        user_repo,
        username="bob",
        display_name="Bob",
        email="bob@x.com",
        role_id="base-operator",
        audit=audit,
        actor="admin.user",
    )
    assert audit.last.payload["role_id"] == "base-operator"


async def test_create_user_no_audit_skips_silently(user_repo):
    user = await create_user(
        user_repo, username="carol", display_name="Carol", email="c@x.com", audit=None
    )
    assert user.username == "carol"


async def test_update_user_records_user_update(user_repo, audit):
    user = await create_user(user_repo, username="dave", display_name="Dave", email="d@x.com")
    audit.entries.clear()
    await update_user(
        user_repo,
        user.id,
        display_name="Dave Updated",
        audit=audit,
        actor="admin.user",
    )
    assert len(audit.entries) == 1
    e = audit.last
    assert e.action == "user.update"
    assert e.entity_type == "user"
    assert e.entity_id == user.id
    assert e.actor == "admin.user"
    assert e.payload["display_name"] == "Dave Updated"


async def test_update_user_payload_includes_all_current_fields(user_repo, audit):
    user = await create_user(user_repo, username="eve", display_name="Eve", email="eve@x.com")
    await update_user(user_repo, user.id, is_active=False, audit=audit, actor="admin.user")
    payload = audit.last.payload
    assert "username" in payload
    assert "display_name" in payload
    assert "email" in payload
    assert "role_id" in payload
    assert "is_active" in payload
    assert payload["is_active"] is False


async def test_update_user_no_audit_skips_silently(user_repo):
    user = await create_user(user_repo, username="frank", display_name="Frank", email="f@x.com")
    updated = await update_user(user_repo, user.id, display_name="Frank New", audit=None)
    assert updated.display_name == "Frank New"


async def test_delete_user_records_user_delete(user_repo, audit):
    user = await create_user(user_repo, username="grace", display_name="Grace", email="g@x.com")
    audit.entries.clear()
    await delete_user(user_repo, user.id, audit=audit, actor="admin.user")
    assert len(audit.entries) == 1
    e = audit.last
    assert e.action == "user.delete"
    assert e.entity_type == "user"
    assert e.entity_id == user.id
    assert e.actor == "admin.user"
    assert e.payload["username"] == "grace"


async def test_delete_user_no_audit_skips_silently(user_repo):
    user = await create_user(user_repo, username="henry", display_name="Henry", email="h@x.com")
    await delete_user(user_repo, user.id, audit=None)


# ---------------------------------------------------------------------------
# Role audit entries
# ---------------------------------------------------------------------------


async def test_create_role_records_role_create(role_repo, audit):
    role = await create_custom_role(
        role_repo,
        name="site_lead",
        permissions=["user:read"],
        ad_groups=["GRP-SITE-LEAD"],
        audit=audit,
        actor="admin.user",
    )
    assert len(audit.entries) == 1
    e = audit.last
    assert e.action == "role.create"
    assert e.entity_type == "role"
    assert e.entity_id == role.id
    assert e.actor == "admin.user"
    assert e.payload["name"] == "site_lead"
    assert e.payload["permissions"] == ["user:read"]
    assert e.payload["ad_groups"] == ["GRP-SITE-LEAD"]
    assert e.payload["area_scope"] is None


async def test_create_role_payload_includes_area_scope(role_repo, audit):
    await create_custom_role(
        role_repo,
        name="area_op",
        permissions=["user:read"],
        ad_groups=["GRP-AREA"],
        area_scope=["Area-A", "Area-B"],
        audit=audit,
        actor="admin.user",
    )
    assert audit.last.payload["area_scope"] == ["Area-A", "Area-B"]


async def test_create_role_no_audit_skips_silently(role_repo):
    role = await create_custom_role(
        role_repo,
        name="quiet_role",
        permissions=["role:read"],
        ad_groups=["GRP-Q"],
        audit=None,
    )
    assert role.name == "quiet_role"


async def test_update_role_records_role_update(role_repo, audit):
    role = await create_custom_role(
        role_repo,
        name="patch_me",
        permissions=["user:read"],
        ad_groups=["GRP-PATCH"],
    )
    audit.entries.clear()
    await update_custom_role(
        role_repo,
        role.id,
        permissions=["user:read", "role:manage"],
        audit=audit,
        actor="admin.user",
    )
    assert len(audit.entries) == 1
    e = audit.last
    assert e.action == "role.update"
    assert e.entity_type == "role"
    assert e.entity_id == role.id
    assert e.actor == "admin.user"
    assert sorted(e.payload["permissions"]) == ["role:manage", "user:read"]


async def test_update_role_no_audit_skips_silently(role_repo):
    role = await create_custom_role(
        role_repo,
        name="noop_role",
        permissions=["user:read"],
        ad_groups=["GRP-NOOP"],
    )
    updated = await update_custom_role(role_repo, role.id, permissions=["role:read"], audit=None)
    assert updated.permissions == ["role:read"]


async def test_delete_role_records_role_delete(role_repo, audit):
    role = await create_custom_role(
        role_repo,
        name="bye_role",
        permissions=["user:read"],
        ad_groups=["GRP-BYE"],
    )
    audit.entries.clear()
    await delete_custom_role(role_repo, role.id, audit=audit, actor="admin.user")
    assert len(audit.entries) == 1
    e = audit.last
    assert e.action == "role.delete"
    assert e.entity_type == "role"
    assert e.entity_id == role.id
    assert e.actor == "admin.user"
    assert e.payload["name"] == "bye_role"


async def test_delete_role_no_audit_skips_silently(role_repo):
    role = await create_custom_role(
        role_repo,
        name="silent_del",
        permissions=["user:read"],
        ad_groups=["GRP-SD"],
    )
    await delete_custom_role(role_repo, role.id, audit=None)


# ---------------------------------------------------------------------------
# Actor field propagation
# ---------------------------------------------------------------------------


async def test_actor_defaults_to_system_when_not_provided(user_repo, audit):
    await create_user(
        user_repo, username="sys_user", display_name="System", email="s@x.com", audit=audit
    )
    assert audit.last.actor == "system"


async def test_actor_is_set_from_caller(user_repo, audit):
    await create_user(
        user_repo,
        username="act_user",
        display_name="Act",
        email="a@x.com",
        audit=audit,
        actor="real.admin",
    )
    assert audit.last.actor == "real.admin"
