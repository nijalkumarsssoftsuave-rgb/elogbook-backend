"""Integration tests for ES-362: GET /admin/permissions endpoint.

Covers:
- 200 with full catalogue list
- Entry shape (permission, module, description)
- Wildcard excluded from response
- Expected permissions present
- Permission gate: requires role:read (403 for operator)
- Authentication required (401)
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.deps import _role_repo, _user_repo
from src.core.config import get_settings
from src.domain.users_roles.permissions import PERMISSION_CATALOGUE, VALID_PERMISSIONS
from src.domain.users_roles.seed import BASE_ROLES
from src.main import app
from tests.helpers import bearer

ADMIN = bearer("admin.user", ["OLNG-ELOG-ADMINS"])
OPERATOR = bearer("jane.operator", ["OLNG-ELOG-OPERATORS"])


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
# Happy path
# ---------------------------------------------------------------------------


async def test_list_permissions_returns_200(client):
    resp = await client.get("/api/v1/admin/permissions", headers={"Authorization": ADMIN})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True


async def test_list_permissions_returns_all_catalogue_entries(client):
    resp = await client.get("/api/v1/admin/permissions", headers={"Authorization": ADMIN})
    data = resp.json()["data"]
    returned_perms = {e["permission"] for e in data}
    assert returned_perms == VALID_PERMISSIONS


async def test_list_permissions_count_matches_catalogue(client):
    resp = await client.get("/api/v1/admin/permissions", headers={"Authorization": ADMIN})
    data = resp.json()["data"]
    assert len(data) == len(PERMISSION_CATALOGUE)


async def test_list_permissions_entry_shape(client):
    resp = await client.get("/api/v1/admin/permissions", headers={"Authorization": ADMIN})
    data = resp.json()["data"]
    assert len(data) > 0
    entry = data[0]
    assert "permission" in entry
    assert "module" in entry
    assert "description" in entry
    assert isinstance(entry["permission"], str)
    assert isinstance(entry["module"], str)
    assert isinstance(entry["description"], str)


async def test_list_permissions_excludes_wildcard(client):
    resp = await client.get("/api/v1/admin/permissions", headers={"Authorization": ADMIN})
    data = resp.json()["data"]
    returned_perms = {e["permission"] for e in data}
    assert "*" not in returned_perms


async def test_list_permissions_includes_admin_permissions(client):
    resp = await client.get("/api/v1/admin/permissions", headers={"Authorization": ADMIN})
    data = resp.json()["data"]
    returned_perms = {e["permission"] for e in data}
    assert "role:read" in returned_perms
    assert "role:manage" in returned_perms
    assert "user:manage" in returned_perms


async def test_list_permissions_entries_have_non_empty_fields(client):
    resp = await client.get("/api/v1/admin/permissions", headers={"Authorization": ADMIN})
    data = resp.json()["data"]
    for entry in data:
        assert entry["permission"].strip()
        assert entry["module"].strip()
        assert entry["description"].strip()


# ---------------------------------------------------------------------------
# Permission gate
# ---------------------------------------------------------------------------


async def test_list_permissions_requires_role_read(client):
    resp = await client.get("/api/v1/admin/permissions", headers={"Authorization": OPERATOR})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


async def test_list_permissions_requires_authentication(client):
    resp = await client.get("/api/v1/admin/permissions")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Catalogue validation via role create/update endpoints
# ---------------------------------------------------------------------------


async def test_create_role_with_unknown_permission_returns_422(client):
    body = {
        "name": "bad_role",
        "permissions": ["banana:explode"],
        "ad_groups": ["GRP-BAD"],
    }
    resp = await client.post(
        "/api/v1/admin/roles",
        json=body,
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 422


async def test_create_role_with_wildcard_returns_422(client):
    body = {
        "name": "wildcard_role",
        "permissions": ["*"],
        "ad_groups": ["GRP-WILD"],
    }
    resp = await client.post(
        "/api/v1/admin/roles",
        json=body,
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 422


async def test_create_role_with_valid_catalogue_permission_succeeds(client):
    body = {
        "name": "valid_role",
        "permissions": ["user:read", "role:read"],
        "ad_groups": ["GRP-VALID"],
    }
    resp = await client.post(
        "/api/v1/admin/roles",
        json=body,
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data["permissions"]) == {"user:read", "role:read"}
