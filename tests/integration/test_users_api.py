"""Integration tests for admin user management (ES-358)."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.deps import _role_repo, _user_repo
from src.core.config import get_settings
from src.domain.users_roles.seed import BASE_ROLES
from src.main import app
from tests.helpers import bearer

ADMIN = bearer("admin.user", ["OLNG-ELOG-ADMINS"])
SUPER_USER = bearer("super.user", ["OLNG-ELOG-SUPERUSERS"])
OPERATOR = bearer("jane.operator", ["OLNG-ELOG-OPERATORS"])


@pytest.fixture(autouse=True)
def _reset_state():
    """Isolate tests: reset in-memory stores before and after each test."""
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
# List / get
# ---------------------------------------------------------------------------


async def test_list_users_initially_empty(client):
    resp = await client.get("/api/v1/admin/users", headers={"Authorization": ADMIN})
    assert resp.status_code == 200
    assert resp.json()["data"] == []


async def test_super_user_can_list_users(client):
    resp = await client.get("/api/v1/admin/users", headers={"Authorization": SUPER_USER})
    assert resp.status_code == 200


async def test_operator_cannot_list_users(client):
    resp = await client.get("/api/v1/admin/users", headers={"Authorization": OPERATOR})
    assert resp.status_code == 403


async def test_unauthenticated_cannot_list_users(client):
    resp = await client.get("/api/v1/admin/users")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


async def test_create_user_returns_user_record(client):
    resp = await client.post(
        "/api/v1/admin/users",
        headers={"Authorization": ADMIN},
        json={"username": "john.doe", "display_name": "John Doe", "email": "john.doe@olng.com"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["username"] == "john.doe"
    assert data["display_name"] == "John Doe"
    assert data["email"] == "john.doe@olng.com"
    assert data["is_active"] is True
    assert data["role_id"] is None
    assert "id" in data


async def test_create_user_normalises_username_to_lowercase(client):
    resp = await client.post(
        "/api/v1/admin/users",
        headers={"Authorization": ADMIN},
        json={"username": "JOHN.DOE", "display_name": "John Doe", "email": "john@olng.com"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["username"] == "john.doe"


async def test_create_user_with_role_override(client):
    resp = await client.post(
        "/api/v1/admin/users",
        headers={"Authorization": ADMIN},
        json={
            "username": "temp.user",
            "display_name": "Temp User",
            "email": "temp@olng.com",
            "role_id": "base-operator",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["role_id"] == "base-operator"


async def test_operator_cannot_create_user(client):
    resp = await client.post(
        "/api/v1/admin/users",
        headers={"Authorization": OPERATOR},
        json={"username": "x", "display_name": "X", "email": "x@x.com"},
    )
    assert resp.status_code == 403


async def test_duplicate_username_is_conflict(client):
    payload = {"username": "john.doe", "display_name": "John Doe", "email": "john@olng.com"}
    await client.post("/api/v1/admin/users", headers={"Authorization": ADMIN}, json=payload)
    resp = await client.post("/api/v1/admin/users", headers={"Authorization": ADMIN}, json=payload)
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Get single
# ---------------------------------------------------------------------------


async def test_get_user_returns_correct_record(client):
    create = await client.post(
        "/api/v1/admin/users",
        headers={"Authorization": ADMIN},
        json={"username": "alice", "display_name": "Alice", "email": "alice@olng.com"},
    )
    user_id = create.json()["data"]["id"]

    resp = await client.get(f"/api/v1/admin/users/{user_id}", headers={"Authorization": ADMIN})
    assert resp.status_code == 200
    assert resp.json()["data"]["username"] == "alice"


async def test_get_unknown_user_is_404(client):
    resp = await client.get("/api/v1/admin/users/does-not-exist", headers={"Authorization": ADMIN})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


async def test_update_user_display_name(client):
    create = await client.post(
        "/api/v1/admin/users",
        headers={"Authorization": ADMIN},
        json={"username": "bob", "display_name": "Bob Old", "email": "bob@olng.com"},
    )
    user_id = create.json()["data"]["id"]

    resp = await client.patch(
        f"/api/v1/admin/users/{user_id}",
        headers={"Authorization": ADMIN},
        json={"display_name": "Bob New"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["display_name"] == "Bob New"


async def test_deactivate_user(client):
    create = await client.post(
        "/api/v1/admin/users",
        headers={"Authorization": ADMIN},
        json={"username": "carol", "display_name": "Carol", "email": "carol@olng.com"},
    )
    user_id = create.json()["data"]["id"]

    resp = await client.patch(
        f"/api/v1/admin/users/{user_id}",
        headers={"Authorization": ADMIN},
        json={"is_active": False},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["is_active"] is False


async def test_assign_role_override(client):
    create = await client.post(
        "/api/v1/admin/users",
        headers={"Authorization": ADMIN},
        json={"username": "dave", "display_name": "Dave", "email": "dave@olng.com"},
    )
    user_id = create.json()["data"]["id"]

    resp = await client.patch(
        f"/api/v1/admin/users/{user_id}",
        headers={"Authorization": ADMIN},
        json={"role_id": "base-supervisor"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["role_id"] == "base-supervisor"


async def test_clear_role_override(client):
    create = await client.post(
        "/api/v1/admin/users",
        headers={"Authorization": ADMIN},
        json={
            "username": "eve",
            "display_name": "Eve",
            "email": "eve@olng.com",
            "role_id": "base-operator",
        },
    )
    user_id = create.json()["data"]["id"]

    resp = await client.patch(
        f"/api/v1/admin/users/{user_id}",
        headers={"Authorization": ADMIN},
        json={"clear_role": True},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["role_id"] is None


async def test_update_unknown_user_is_404(client):
    resp = await client.patch(
        "/api/v1/admin/users/does-not-exist",
        headers={"Authorization": ADMIN},
        json={"display_name": "X"},
    )
    assert resp.status_code == 404


async def test_operator_cannot_update_user(client):
    create = await client.post(
        "/api/v1/admin/users",
        headers={"Authorization": ADMIN},
        json={"username": "frank", "display_name": "Frank", "email": "frank@olng.com"},
    )
    user_id = create.json()["data"]["id"]

    resp = await client.patch(
        f"/api/v1/admin/users/{user_id}",
        headers={"Authorization": OPERATOR},
        json={"display_name": "Hacker"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


async def test_delete_user_removes_record(client):
    create = await client.post(
        "/api/v1/admin/users",
        headers={"Authorization": ADMIN},
        json={"username": "grace", "display_name": "Grace", "email": "grace@olng.com"},
    )
    user_id = create.json()["data"]["id"]

    delete = await client.delete(f"/api/v1/admin/users/{user_id}", headers={"Authorization": ADMIN})
    assert delete.status_code == 200
    assert delete.json()["data"]["deleted"] == user_id

    listed = await client.get("/api/v1/admin/users", headers={"Authorization": ADMIN})
    assert user_id not in {u["id"] for u in listed.json()["data"]}


async def test_delete_unknown_user_is_404(client):
    resp = await client.delete(
        "/api/v1/admin/users/does-not-exist", headers={"Authorization": ADMIN}
    )
    assert resp.status_code == 404


async def test_operator_cannot_delete_user(client):
    create = await client.post(
        "/api/v1/admin/users",
        headers={"Authorization": ADMIN},
        json={"username": "henry", "display_name": "Henry", "email": "henry@olng.com"},
    )
    user_id = create.json()["data"]["id"]

    resp = await client.delete(
        f"/api/v1/admin/users/{user_id}", headers={"Authorization": OPERATOR}
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Full CRUD flow
# ---------------------------------------------------------------------------


async def test_full_create_read_update_delete_flow(client):
    # Create
    created = await client.post(
        "/api/v1/admin/users",
        headers={"Authorization": ADMIN},
        json={"username": "ivan", "display_name": "Ivan", "email": "ivan@olng.com"},
    )
    assert created.status_code == 200
    user = created.json()["data"]
    user_id = user["id"]

    # List — appears in list
    listed = await client.get("/api/v1/admin/users", headers={"Authorization": ADMIN})
    assert any(u["id"] == user_id for u in listed.json()["data"])

    # Get single
    got = await client.get(f"/api/v1/admin/users/{user_id}", headers={"Authorization": ADMIN})
    assert got.json()["data"]["username"] == "ivan"

    # Update
    updated = await client.patch(
        f"/api/v1/admin/users/{user_id}",
        headers={"Authorization": ADMIN},
        json={"display_name": "Ivan Updated", "is_active": False},
    )
    assert updated.json()["data"]["display_name"] == "Ivan Updated"
    assert updated.json()["data"]["is_active"] is False

    # Delete
    deleted = await client.delete(
        f"/api/v1/admin/users/{user_id}", headers={"Authorization": ADMIN}
    )
    assert deleted.status_code == 200

    # Gone
    gone = await client.get(f"/api/v1/admin/users/{user_id}", headers={"Authorization": ADMIN})
    assert gone.status_code == 404
