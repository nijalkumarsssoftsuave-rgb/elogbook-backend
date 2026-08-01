"""Integration tests for admin role management and area-scope enforcement."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.deps import _pending_action_repo, _role_repo
from src.core.config import get_settings
from src.domain.users_roles.seed import BASE_ROLES
from src.main import app
from tests.helpers import bearer

ADMIN = bearer("admin.user", ["OLNG-ELOG-ADMINS"])
OPERATOR = bearer("jane.operator", ["OLNG-ELOG-OPERATORS"])


@pytest.fixture(autouse=True)
def _reset_state():
    """Isolate tests: reset the in-memory role/pending-action stores."""
    _pending_action_repo._items.clear()
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


async def test_list_roles_includes_base_roles(client):
    resp = await client.get("/api/v1/admin/roles", headers={"Authorization": ADMIN})
    assert resp.status_code == 200
    names = {r["name"] for r in resp.json()["data"]}
    assert {"operator", "supervisor", "management", "administrator", "super_user"} <= names


async def test_non_admin_cannot_manage_roles(client):
    resp = await client.post(
        "/api/v1/admin/roles",
        headers={"Authorization": OPERATOR},
        json={"name": "x", "permissions": ["action:read"], "ad_groups": ["G1"]},
    )
    assert resp.status_code == 403


async def test_create_update_delete_custom_role(client):
    create = await client.post(
        "/api/v1/admin/roles",
        headers={"Authorization": ADMIN},
        json={
            "name": "train1_operator",
            "permissions": ["action:read", "action:write"],
            "ad_groups": ["OLNG-ELOG-TRAIN1"],
            "area_scope": ["Train 1"],
        },
    )
    assert create.status_code == 200
    role = create.json()["data"]
    assert role["is_custom"] is True
    assert role["area_scope"] == ["Train 1"]

    update = await client.patch(
        f"/api/v1/admin/roles/{role['id']}",
        headers={"Authorization": ADMIN},
        json={"permissions": ["action:read"]},
    )
    assert update.status_code == 200
    assert update.json()["data"]["permissions"] == ["action:read"]

    cleared = await client.patch(
        f"/api/v1/admin/roles/{role['id']}",
        headers={"Authorization": ADMIN},
        json={"clear_area_scope": True},
    )
    assert cleared.json()["data"]["area_scope"] is None

    deleted = await client.delete(
        f"/api/v1/admin/roles/{role['id']}", headers={"Authorization": ADMIN}
    )
    assert deleted.status_code == 200

    listed = await client.get("/api/v1/admin/roles", headers={"Authorization": ADMIN})
    assert role["id"] not in {r["id"] for r in listed.json()["data"]}


async def test_base_role_cannot_be_modified_or_deleted(client):
    listed = await client.get("/api/v1/admin/roles", headers={"Authorization": ADMIN})
    base = next(r for r in listed.json()["data"] if r["name"] == "operator")

    update = await client.patch(
        f"/api/v1/admin/roles/{base['id']}",
        headers={"Authorization": ADMIN},
        json={"permissions": ["*"]},
    )
    assert update.status_code == 409

    delete = await client.delete(
        f"/api/v1/admin/roles/{base['id']}", headers={"Authorization": ADMIN}
    )
    assert delete.status_code == 409


async def test_duplicate_role_name_is_conflict(client):
    resp = await client.post(
        "/api/v1/admin/roles",
        headers={"Authorization": ADMIN},
        json={"name": "operator", "permissions": ["action:read"], "ad_groups": ["G-NEW"]},
    )
    assert resp.status_code == 409


async def test_duplicate_ad_group_is_conflict(client):
    resp = await client.post(
        "/api/v1/admin/roles",
        headers={"Authorization": ADMIN},
        json={
            "name": "new_role",
            "permissions": ["action:read"],
            "ad_groups": ["OLNG-ELOG-OPERATORS"],
        },
    )
    assert resp.status_code == 409


async def test_role_mapping_endpoint_lists_group_to_role_rows(client):
    resp = await client.get("/api/v1/admin/roles/mapping", headers={"Authorization": ADMIN})
    assert resp.status_code == 200
    rows = resp.json()["data"]
    by_group = {r["ad_group"]: r["role_name"] for r in rows}
    assert by_group["OLNG-ELOG-OPERATORS"] == "operator"
    assert by_group["OLNG-ELOG-ADMINS"] == "administrator"


async def test_role_mapping_reflects_new_custom_role(client):
    await client.post(
        "/api/v1/admin/roles",
        headers={"Authorization": ADMIN},
        json={
            "name": "train1_operator",
            "permissions": ["action:read"],
            "ad_groups": ["OLNG-ELOG-TRAIN1"],
            "area_scope": ["Train 1"],
        },
    )
    resp = await client.get("/api/v1/admin/roles/mapping", headers={"Authorization": ADMIN})
    row = next(r for r in resp.json()["data"] if r["ad_group"] == "OLNG-ELOG-TRAIN1")
    assert row["role_name"] == "train1_operator"
    assert row["is_custom"] is True
    assert row["area_scope"] == ["Train 1"]


async def test_non_admin_cannot_view_role_mapping(client):
    resp = await client.get("/api/v1/admin/roles/mapping", headers={"Authorization": OPERATOR})
    assert resp.status_code == 403


async def test_role_history_is_empty_under_memory_backend(client):
    """Memory backend has no audit persistence — history reads back nothing, not an error."""
    create = await client.post(
        "/api/v1/admin/roles",
        headers={"Authorization": ADMIN},
        json={"name": "temp_role", "permissions": ["action:read"], "ad_groups": ["G-TEMP"]},
    )
    role_id = create.json()["data"]["id"]

    history = await client.get(
        f"/api/v1/admin/roles/{role_id}/history", headers={"Authorization": ADMIN}
    )
    assert history.status_code == 200
    assert history.json()["data"] == []


async def test_role_history_unknown_id_is_empty_not_error(client):
    history = await client.get(
        "/api/v1/admin/roles/does-not-exist/history", headers={"Authorization": ADMIN}
    )
    assert history.status_code == 200
    assert history.json()["data"] == []


async def test_non_admin_cannot_view_role_history(client):
    resp = await client.get(
        "/api/v1/admin/roles/whatever/history", headers={"Authorization": OPERATOR}
    )
    assert resp.status_code == 403


async def test_area_scoped_custom_role_narrows_pending_actions(client):
    await client.post(
        "/api/v1/admin/roles",
        headers={"Authorization": ADMIN},
        json={
            "name": "train1_operator",
            "permissions": ["action:read", "action:write"],
            "ad_groups": ["OLNG-ELOG-TRAIN1"],
            "area_scope": ["Train 1"],
        },
    )
    scoped_token = bearer("t1.operator", ["OLNG-ELOG-TRAIN1"])

    await client.post(
        "/api/v1/pending-actions",
        headers={"Authorization": ADMIN},
        json={"issue": "Train 1 issue", "area": "Train 1"},
    )
    await client.post(
        "/api/v1/pending-actions",
        headers={"Authorization": ADMIN},
        json={"issue": "Train 2 issue", "area": "Train 2"},
    )

    listed = await client.get("/api/v1/pending-actions", headers={"Authorization": scoped_token})
    assert listed.status_code == 200
    areas = {a["area"] for a in listed.json()["data"]}
    assert areas == {"Train 1"}

    all_listed = await client.get("/api/v1/pending-actions", headers={"Authorization": ADMIN})
    assert len(all_listed.json()["data"]) == 2
