"""Integration tests for ES-364: custom roles are resolved identically to base roles.

Covers end-to-end resolution through GET /api/v1/me — the same path the frontend uses
to gate routing and menus. Every assertion proves that custom roles travel through the
same permission-union and area-scope logic as base roles with no special-casing.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.deps import _role_repo
from src.core.config import get_settings
from src.domain.users_roles.seed import BASE_ROLES
from src.main import app
from tests.helpers import bearer

ADMIN = bearer("admin.user", ["OLNG-ELOG-ADMINS"])


@pytest.fixture(autouse=True)
def _reset_state():
    _role_repo._items = {r.id: r for r in BASE_ROLES}
    get_settings.cache_clear()
    yield
    _role_repo._items = {r.id: r for r in BASE_ROLES}
    get_settings.cache_clear()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Permission union: base role + custom role
# ---------------------------------------------------------------------------


async def test_custom_role_permissions_are_unioned_with_base_role(client):
    await client.post(
        "/api/v1/admin/roles",
        json={
            "name": "analyst",
            "permissions": ["analytics:read"],
            "ad_groups": ["ANALYTICS-GROUP"],
        },
        headers={"Authorization": ADMIN},
    )
    token = bearer("multi.user", ["OLNG-ELOG-OPERATORS", "ANALYTICS-GROUP"])
    resp = await client.get("/api/v1/me", headers={"Authorization": token})

    assert resp.status_code == 200
    profile = resp.json()["data"]
    assert set(profile["roles"]) == {"operator", "analyst"}
    assert "action:read" in profile["permissions"]   # from base operator
    assert "analytics:read" in profile["permissions"]  # from custom role


async def test_custom_role_only_permissions_are_visible(client):
    await client.post(
        "/api/v1/admin/roles",
        json={
            "name": "report_viewer",
            "permissions": ["report:read"],
            "ad_groups": ["REPORT-GROUP"],
        },
        headers={"Authorization": ADMIN},
    )
    token = bearer("reporter", ["REPORT-GROUP"])
    resp = await client.get("/api/v1/me", headers={"Authorization": token})

    assert resp.status_code == 200
    profile = resp.json()["data"]
    assert profile["roles"] == ["report_viewer"]
    assert profile["permissions"] == ["report:read"]


# ---------------------------------------------------------------------------
# Area scope resolution: base full-plant overrides custom scoped
# ---------------------------------------------------------------------------


async def test_base_full_plant_role_overrides_custom_area_scope(client):
    await client.post(
        "/api/v1/admin/roles",
        json={
            "name": "train1_op",
            "permissions": ["action:read"],
            "ad_groups": ["TRAIN1-GROUP"],
            "area_scope": ["Train 1"],
        },
        headers={"Authorization": ADMIN},
    )
    # User in BOTH base operator (full-plant) AND the scoped custom role
    token = bearer("wide.user", ["OLNG-ELOG-OPERATORS", "TRAIN1-GROUP"])
    resp = await client.get("/api/v1/me", headers={"Authorization": token})

    profile = resp.json()["data"]
    assert profile["area_scope"] is None  # full-plant wins


async def test_scoped_custom_role_without_full_plant_restricts_access(client):
    await client.post(
        "/api/v1/admin/roles",
        json={
            "name": "train1_only",
            "permissions": ["action:read"],
            "ad_groups": ["TRAIN1-ONLY-GROUP"],
            "area_scope": ["Train 1"],
        },
        headers={"Authorization": ADMIN},
    )
    token = bearer("restricted.user", ["TRAIN1-ONLY-GROUP"])
    resp = await client.get("/api/v1/me", headers={"Authorization": token})

    profile = resp.json()["data"]
    assert profile["area_scope"] == ["Train 1"]


async def test_two_scoped_custom_roles_area_scopes_are_unioned(client):
    await client.post(
        "/api/v1/admin/roles",
        json={
            "name": "zone_a_op",
            "permissions": ["action:read"],
            "ad_groups": ["ZONE-A-GROUP"],
            "area_scope": ["Zone-A"],
        },
        headers={"Authorization": ADMIN},
    )
    await client.post(
        "/api/v1/admin/roles",
        json={
            "name": "zone_b_op",
            "permissions": ["action:read"],
            "ad_groups": ["ZONE-B-GROUP"],
            "area_scope": ["Zone-B"],
        },
        headers={"Authorization": ADMIN},
    )
    token = bearer("dual.zone", ["ZONE-A-GROUP", "ZONE-B-GROUP"])
    resp = await client.get("/api/v1/me", headers={"Authorization": token})

    profile = resp.json()["data"]
    assert profile["area_scope"] == ["Zone-A", "Zone-B"]
