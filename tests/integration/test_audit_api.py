"""Integration tests for ES-360: admin audit history endpoints.

Tests cover:
- GET /admin/users/{id}/history — new endpoint
- GET /admin/roles/{id}/history — existing endpoint (permission + shape)
- Permission enforcement on both history endpoints
- Endpoint behaviour with a live CapturingAuditRecorder overriding the default NullAuditReader
"""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.deps import _role_repo, _user_repo, get_audit_reader
from src.application.audit.reader import AuditReader, AuditRecord
from src.core.config import get_settings
from src.domain.users_roles.seed import BASE_ROLES
from src.main import app
from tests.helpers import bearer

ADMIN = bearer("admin.user", ["OLNG-ELOG-ADMINS"])
OPERATOR = bearer("jane.operator", ["OLNG-ELOG-OPERATORS"])


def _fake_record(entity_type: str, entity_id: str, action: str, actor: str, payload: dict) -> AuditRecord:
    return AuditRecord(
        event_id="evt-" + action,
        occurred_at=datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC),
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
    )


class FakeAuditReader(AuditReader):
    """Returns pre-seeded records filtered by entity_type + entity_id."""

    def __init__(self, records: list[AuditRecord]) -> None:
        self._records = records

    async def list_for_entity(self, entity_type: str, entity_id: str) -> list[AuditRecord]:
        return [r for r in self._records if r.entity_type == entity_type and r.entity_id == entity_id]


@pytest.fixture(autouse=True)
def _reset_state():
    _user_repo._items.clear()
    _role_repo._items = {r.id: r for r in BASE_ROLES}
    get_settings.cache_clear()
    yield
    _user_repo._items.clear()
    _role_repo._items = {r.id: r for r in BASE_ROLES}
    get_settings.cache_clear()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# User history — default (NullAuditReader returns empty list)
# ---------------------------------------------------------------------------


async def test_user_history_returns_200_empty_list(client):
    resp = await client.get(
        "/api/v1/admin/users/any-user-id/history", headers={"Authorization": ADMIN}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"] == []


async def test_user_history_unknown_id_returns_empty_list(client):
    resp = await client.get(
        "/api/v1/admin/users/nonexistent-id-xyz/history", headers={"Authorization": ADMIN}
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == []


async def test_user_history_requires_user_read_permission(client):
    resp = await client.get(
        "/api/v1/admin/users/some-id/history", headers={"Authorization": OPERATOR}
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


async def test_user_history_requires_authentication(client):
    resp = await client.get("/api/v1/admin/users/some-id/history")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# User history — with seeded records (FakeAuditReader override)
# ---------------------------------------------------------------------------


async def test_user_history_returns_audit_entries_for_user(client):
    user_id = "user-abc-123"
    records = [
        _fake_record("user", user_id, "user.update", "admin.user", {"display_name": "Alice"}),
        _fake_record("user", user_id, "user.create", "admin.user", {"username": "alice"}),
        _fake_record("user", "other-user", "user.create", "admin.user", {"username": "other"}),
    ]
    reader = FakeAuditReader(records)
    app.dependency_overrides[get_audit_reader] = lambda: reader
    try:
        resp = await client.get(
            f"/api/v1/admin/users/{user_id}/history", headers={"Authorization": ADMIN}
        )
    finally:
        app.dependency_overrides.pop(get_audit_reader, None)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 2
    assert data[0]["action"] == "user.update"
    assert data[1]["action"] == "user.create"


async def test_user_history_entry_shape(client):
    user_id = "shape-test-user"
    records = [
        _fake_record("user", user_id, "user.create", "admin.user", {"username": "alice", "role_id": None})
    ]
    reader = FakeAuditReader(records)
    app.dependency_overrides[get_audit_reader] = lambda: reader
    try:
        resp = await client.get(
            f"/api/v1/admin/users/{user_id}/history", headers={"Authorization": ADMIN}
        )
    finally:
        app.dependency_overrides.pop(get_audit_reader, None)

    entry = resp.json()["data"][0]
    assert "event_id" in entry
    assert "occurred_at" in entry
    assert "actor" in entry
    assert "action" in entry
    assert "payload" in entry
    assert entry["actor"] == "admin.user"
    assert entry["action"] == "user.create"
    assert entry["payload"]["username"] == "alice"


# ---------------------------------------------------------------------------
# Role history — existing endpoint (ensure permission + shape still correct)
# ---------------------------------------------------------------------------


async def test_role_history_returns_200_empty_list(client):
    resp = await client.get(
        "/api/v1/admin/roles/base-operator/history", headers={"Authorization": ADMIN}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"] == []


async def test_role_history_unknown_id_returns_empty_list(client):
    resp = await client.get(
        "/api/v1/admin/roles/nonexistent-role-xyz/history", headers={"Authorization": ADMIN}
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == []


async def test_role_history_requires_role_read_permission(client):
    resp = await client.get(
        "/api/v1/admin/roles/base-operator/history", headers={"Authorization": OPERATOR}
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


async def test_role_history_requires_authentication(client):
    resp = await client.get("/api/v1/admin/roles/base-operator/history")
    assert resp.status_code == 401


async def test_role_history_returns_entries_for_role(client):
    role_id = "custom-role-xyz"
    records = [
        _fake_record("role", role_id, "role.update", "admin.user", {"name": "my_role", "permissions": ["user:read"]}),
        _fake_record("role", role_id, "role.create", "admin.user", {"name": "my_role"}),
        _fake_record("role", "other-role", "role.create", "admin.user", {"name": "other"}),
    ]
    reader = FakeAuditReader(records)
    app.dependency_overrides[get_audit_reader] = lambda: reader
    try:
        resp = await client.get(
            f"/api/v1/admin/roles/{role_id}/history", headers={"Authorization": ADMIN}
        )
    finally:
        app.dependency_overrides.pop(get_audit_reader, None)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 2
    assert data[0]["action"] == "role.update"
    assert data[1]["action"] == "role.create"


async def test_role_history_entry_shape(client):
    role_id = "shape-test-role"
    records = [
        _fake_record("role", role_id, "role.create", "admin.user", {"name": "site_lead", "permissions": ["user:read"]})
    ]
    reader = FakeAuditReader(records)
    app.dependency_overrides[get_audit_reader] = lambda: reader
    try:
        resp = await client.get(
            f"/api/v1/admin/roles/{role_id}/history", headers={"Authorization": ADMIN}
        )
    finally:
        app.dependency_overrides.pop(get_audit_reader, None)

    entry = resp.json()["data"][0]
    assert "event_id" in entry
    assert "occurred_at" in entry
    assert "actor" in entry
    assert "action" in entry
    assert "payload" in entry
    assert entry["actor"] == "admin.user"
    assert entry["action"] == "role.create"
    assert entry["payload"]["name"] == "site_lead"


# ---------------------------------------------------------------------------
# Both history endpoints: verify they do NOT interfere with each other
# ---------------------------------------------------------------------------


async def test_user_and_role_history_are_scoped_separately(client):
    shared_id = "same-id-for-both"
    records = [
        _fake_record("user", shared_id, "user.create", "admin.user", {"username": "alice"}),
        _fake_record("role", shared_id, "role.create", "admin.user", {"name": "my_role"}),
    ]
    reader = FakeAuditReader(records)
    app.dependency_overrides[get_audit_reader] = lambda: reader
    try:
        user_resp = await client.get(
            f"/api/v1/admin/users/{shared_id}/history", headers={"Authorization": ADMIN}
        )
        role_resp = await client.get(
            f"/api/v1/admin/roles/{shared_id}/history", headers={"Authorization": ADMIN}
        )
    finally:
        app.dependency_overrides.pop(get_audit_reader, None)

    user_data = user_resp.json()["data"]
    role_data = role_resp.json()["data"]
    assert len(user_data) == 1
    assert user_data[0]["action"] == "user.create"
    assert len(role_data) == 1
    assert role_data[0]["action"] == "role.create"
