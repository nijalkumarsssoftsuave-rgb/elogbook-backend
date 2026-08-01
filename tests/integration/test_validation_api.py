"""Integration tests: ES-359 — Validation & Conflicts.

Covers HTTP-level 422 / 409 responses for:
- Invalid user field values (username, display_name, email).
- Invalid role field values (name, permissions, AD groups).
- Assigning a non-existent role_id to a user (422).
- Deleting a role that has users assigned (409).
All tests use the in-memory backend; state is reset between every test.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.deps import _role_repo, _user_repo
from src.core.config import get_settings
from src.domain.users_roles.entities import User
from src.domain.users_roles.seed import BASE_ROLES
from src.main import app
from tests.helpers import bearer

ADMIN = bearer("admin.user", ["OLNG-ELOG-ADMINS"])


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
# Helpers
# ---------------------------------------------------------------------------


def _valid_user_body(**overrides):
    body = {"username": "testuser", "display_name": "Test User", "email": "test@example.com"}
    body.update(overrides)
    return body


def _valid_role_body(**overrides):
    body = {"name": "custom_role", "permissions": ["user:read"], "ad_groups": ["GRP-TEST"]}
    body.update(overrides)
    return body


async def _create_user(client, **overrides):
    resp = await client.post(
        "/api/v1/admin/users",
        json=_valid_user_body(**overrides),
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _create_role(client, **overrides):
    resp = await client.post(
        "/api/v1/admin/roles",
        json=_valid_role_body(**overrides),
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


# ---------------------------------------------------------------------------
# User create — username validation
# ---------------------------------------------------------------------------


async def test_username_empty_returns_422(client):
    resp = await client.post(
        "/api/v1/admin/users", json=_valid_user_body(username=""), headers={"Authorization": ADMIN}
    )
    assert resp.status_code == 422


async def test_username_with_spaces_returns_422(client):
    resp = await client.post(
        "/api/v1/admin/users",
        json=_valid_user_body(username="alice smith"),
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 422


async def test_username_with_at_sign_returns_422(client):
    resp = await client.post(
        "/api/v1/admin/users",
        json=_valid_user_body(username="alice@domain"),
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 422


async def test_username_too_long_returns_422(client):
    resp = await client.post(
        "/api/v1/admin/users",
        json=_valid_user_body(username="a" * 129),
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 422


async def test_username_valid_uppercase_normalised(client):
    resp = await client.post(
        "/api/v1/admin/users",
        json=_valid_user_body(username="ALICE"),
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["username"] == "alice"


# ---------------------------------------------------------------------------
# User create — display_name validation
# ---------------------------------------------------------------------------


async def test_display_name_empty_returns_422(client):
    resp = await client.post(
        "/api/v1/admin/users",
        json=_valid_user_body(display_name=""),
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 422


async def test_display_name_whitespace_only_returns_422(client):
    resp = await client.post(
        "/api/v1/admin/users",
        json=_valid_user_body(display_name="   "),
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 422


async def test_display_name_too_long_returns_422(client):
    resp = await client.post(
        "/api/v1/admin/users",
        json=_valid_user_body(display_name="A" * 257),
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# User create — email validation
# ---------------------------------------------------------------------------


async def test_email_no_at_sign_returns_422(client):
    resp = await client.post(
        "/api/v1/admin/users",
        json=_valid_user_body(email="notanemail"),
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 422


async def test_email_no_dot_after_at_returns_422(client):
    resp = await client.post(
        "/api/v1/admin/users",
        json=_valid_user_body(email="alice@nodot"),
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 422


async def test_email_valid_uppercase_normalised(client):
    resp = await client.post(
        "/api/v1/admin/users",
        json=_valid_user_body(email="ALICE@EXAMPLE.COM"),
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["email"] == "alice@example.com"


# ---------------------------------------------------------------------------
# User create — role_id existence (application-level)
# ---------------------------------------------------------------------------


async def test_create_user_with_nonexistent_role_returns_422(client):
    resp = await client.post(
        "/api/v1/admin/users",
        json=_valid_user_body(role_id="nonexistent-role-id"),
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "validation_error"


async def test_create_user_with_valid_role_id_returns_200(client):
    base_role_id = list(_role_repo._items.keys())[0]
    resp = await client.post(
        "/api/v1/admin/users",
        json=_valid_user_body(role_id=base_role_id),
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["role_id"] == base_role_id


# ---------------------------------------------------------------------------
# User update — display_name and email validation
# ---------------------------------------------------------------------------


async def test_update_user_blank_display_name_returns_422(client):
    user = await _create_user(client)
    resp = await client.patch(
        f"/api/v1/admin/users/{user['id']}",
        json={"display_name": "   "},
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 422


async def test_update_user_invalid_email_returns_422(client):
    user = await _create_user(client)
    resp = await client.patch(
        f"/api/v1/admin/users/{user['id']}",
        json={"email": "bad-email"},
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 422


async def test_update_user_with_nonexistent_role_returns_422(client):
    user = await _create_user(client)
    resp = await client.patch(
        f"/api/v1/admin/users/{user['id']}",
        json={"role_id": "does-not-exist"},
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


async def test_update_user_with_valid_role_id_returns_200(client):
    user = await _create_user(client)
    base_role_id = list(_role_repo._items.keys())[0]
    resp = await client.patch(
        f"/api/v1/admin/users/{user['id']}",
        json={"role_id": base_role_id},
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["role_id"] == base_role_id


# ---------------------------------------------------------------------------
# Role create — name validation
# ---------------------------------------------------------------------------


async def test_role_name_starting_with_digit_returns_422(client):
    resp = await client.post(
        "/api/v1/admin/roles",
        json=_valid_role_body(name="1invalid"),
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 422


async def test_role_name_with_space_returns_422(client):
    resp = await client.post(
        "/api/v1/admin/roles",
        json=_valid_role_body(name="my role"),
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 422


async def test_role_name_with_hyphen_returns_422(client):
    resp = await client.post(
        "/api/v1/admin/roles",
        json=_valid_role_body(name="my-role"),
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 422


async def test_role_name_valid_with_underscore(client):
    resp = await client.post(
        "/api/v1/admin/roles",
        json=_valid_role_body(name="my_role_2"),
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Role create — permissions validation
# ---------------------------------------------------------------------------


async def test_role_permission_invalid_format_returns_422(client):
    resp = await client.post(
        "/api/v1/admin/roles",
        json=_valid_role_body(permissions=["read-only"]),
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 422


async def test_role_permission_empty_string_returns_422(client):
    resp = await client.post(
        "/api/v1/admin/roles",
        json=_valid_role_body(permissions=[""]),
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 422


async def test_role_permissions_empty_list_returns_422(client):
    resp = await client.post(
        "/api/v1/admin/roles",
        json=_valid_role_body(permissions=[]),
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 422


async def test_role_permission_wildcard_rejected_by_catalogue(client):
    resp = await client.post(
        "/api/v1/admin/roles",
        json=_valid_role_body(permissions=["*"]),
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Role create — AD groups validation
# ---------------------------------------------------------------------------


async def test_role_ad_groups_empty_string_returns_422(client):
    resp = await client.post(
        "/api/v1/admin/roles",
        json=_valid_role_body(ad_groups=[""]),
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 422


async def test_role_ad_groups_empty_list_returns_422(client):
    resp = await client.post(
        "/api/v1/admin/roles",
        json=_valid_role_body(ad_groups=[]),
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Role delete — blocked when users are assigned (409)
# ---------------------------------------------------------------------------


async def test_delete_role_with_assigned_users_returns_409(client):
    # Create a custom role
    role = await _create_role(client, name="role_with_users", ad_groups=["GRP-UNIQUE-1"])

    # Manually assign a user to this role in the in-memory store
    user = User.create("testuser99", "Test", "t@x.com", role_id=role["id"])
    _user_repo._items[user.id] = user

    resp = await client.delete(
        f"/api/v1/admin/roles/{role['id']}", headers={"Authorization": ADMIN}
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"]["code"] == "conflict"
    assert "unassign them first" in body["error"]["message"]


async def test_delete_role_no_users_assigned_returns_200(client):
    role = await _create_role(client, name="role_no_users", ad_groups=["GRP-UNIQUE-2"])
    resp = await client.delete(
        f"/api/v1/admin/roles/{role['id']}", headers={"Authorization": ADMIN}
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["deleted"] == role["id"]


async def test_delete_role_with_user_unassigned_then_succeeds(client):
    role = await _create_role(client, name="role_unassign", ad_groups=["GRP-UNIQUE-3"])

    # Add and then unassign the user
    user = User.create("unassignme", "UA", "ua@x.com", role_id=role["id"])
    _user_repo._items[user.id] = user

    # First delete attempt fails
    resp = await client.delete(
        f"/api/v1/admin/roles/{role['id']}", headers={"Authorization": ADMIN}
    )
    assert resp.status_code == 409

    # Unassign the user by clearing role_id
    user.role_id = None

    # Second attempt succeeds
    resp2 = await client.delete(
        f"/api/v1/admin/roles/{role['id']}", headers={"Authorization": ADMIN}
    )
    assert resp2.status_code == 200
