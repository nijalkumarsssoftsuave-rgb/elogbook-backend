"""Integration tests for ES-363: GET /admin/areas endpoint.

Covers:
- 200 with empty list when no scoped roles exist
- Areas populated from existing scoped roles
- Deduplication across multiple roles
- Alphabetical sort
- Role deletion removes its areas from the list
- Permission gate: requires role:read (403 for operator)
- Authentication required (401)
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.deps import _role_repo
from src.core.config import get_settings
from src.domain.users_roles.seed import BASE_ROLES
from src.main import app
from tests.helpers import bearer

ADMIN = bearer("admin.user", ["OLNG-ELOG-ADMINS"])
OPERATOR = bearer("jane.operator", ["OLNG-ELOG-OPERATORS"])


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
# Happy path
# ---------------------------------------------------------------------------


async def test_list_areas_returns_200(client):
    resp = await client.get("/api/v1/admin/areas", headers={"Authorization": ADMIN})
    assert resp.status_code == 200
    assert resp.json()["success"] is True


async def test_list_areas_empty_when_no_scoped_roles(client):
    resp = await client.get("/api/v1/admin/areas", headers={"Authorization": ADMIN})
    assert resp.json()["data"] == []


async def test_list_areas_returns_areas_from_scoped_role(client):
    await client.post(
        "/api/v1/admin/roles",
        json={
            "name": "train_op",
            "permissions": ["action:read"],
            "ad_groups": ["GRP-TRAIN"],
            "area_scope": ["Train 1", "Train 2"],
        },
        headers={"Authorization": ADMIN},
    )
    resp = await client.get("/api/v1/admin/areas", headers={"Authorization": ADMIN})
    assert set(resp.json()["data"]) == {"Train 1", "Train 2"}


async def test_list_areas_deduplicates_across_roles(client):
    await client.post(
        "/api/v1/admin/roles",
        json={
            "name": "role_a",
            "permissions": ["action:read"],
            "ad_groups": ["GRP-A"],
            "area_scope": ["Area-A", "Area-B"],
        },
        headers={"Authorization": ADMIN},
    )
    await client.post(
        "/api/v1/admin/roles",
        json={
            "name": "role_b",
            "permissions": ["action:read"],
            "ad_groups": ["GRP-B"],
            "area_scope": ["Area-B", "Area-C"],
        },
        headers={"Authorization": ADMIN},
    )
    resp = await client.get("/api/v1/admin/areas", headers={"Authorization": ADMIN})
    assert resp.json()["data"] == ["Area-A", "Area-B", "Area-C"]


async def test_list_areas_sorted_alphabetically(client):
    await client.post(
        "/api/v1/admin/roles",
        json={
            "name": "scoped",
            "permissions": ["action:read"],
            "ad_groups": ["GRP-S"],
            "area_scope": ["Zone-C", "Zone-A", "Zone-B"],
        },
        headers={"Authorization": ADMIN},
    )
    resp = await client.get("/api/v1/admin/areas", headers={"Authorization": ADMIN})
    assert resp.json()["data"] == ["Zone-A", "Zone-B", "Zone-C"]


async def test_list_areas_excludes_full_plant_roles(client):
    await client.post(
        "/api/v1/admin/roles",
        json={
            "name": "full_plant",
            "permissions": ["action:read"],
            "ad_groups": ["GRP-FP"],
        },
        headers={"Authorization": ADMIN},
    )
    resp = await client.get("/api/v1/admin/areas", headers={"Authorization": ADMIN})
    assert resp.json()["data"] == []


async def test_list_areas_updates_after_role_deleted(client):
    create = await client.post(
        "/api/v1/admin/roles",
        json={
            "name": "temp_scoped",
            "permissions": ["action:read"],
            "ad_groups": ["GRP-TEMP"],
            "area_scope": ["Area-X"],
        },
        headers={"Authorization": ADMIN},
    )
    role_id = create.json()["data"]["id"]

    before = await client.get("/api/v1/admin/areas", headers={"Authorization": ADMIN})
    assert "Area-X" in before.json()["data"]

    await client.delete(f"/api/v1/admin/roles/{role_id}", headers={"Authorization": ADMIN})

    after = await client.get("/api/v1/admin/areas", headers={"Authorization": ADMIN})
    assert "Area-X" not in after.json()["data"]


async def test_list_areas_updates_after_area_scope_cleared(client):
    create = await client.post(
        "/api/v1/admin/roles",
        json={
            "name": "scoped_role",
            "permissions": ["action:read"],
            "ad_groups": ["GRP-SC"],
            "area_scope": ["Area-Y"],
        },
        headers={"Authorization": ADMIN},
    )
    role_id = create.json()["data"]["id"]

    await client.patch(
        f"/api/v1/admin/roles/{role_id}",
        json={"clear_area_scope": True},
        headers={"Authorization": ADMIN},
    )

    resp = await client.get("/api/v1/admin/areas", headers={"Authorization": ADMIN})
    assert "Area-Y" not in resp.json()["data"]


# ---------------------------------------------------------------------------
# Permission gate
# ---------------------------------------------------------------------------


async def test_list_areas_requires_role_read(client):
    resp = await client.get("/api/v1/admin/areas", headers={"Authorization": OPERATOR})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


async def test_list_areas_requires_authentication(client):
    resp = await client.get("/api/v1/admin/areas")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# area_scope field validation via role endpoints
# ---------------------------------------------------------------------------


async def test_create_role_area_scope_empty_string_returns_422(client):
    resp = await client.post(
        "/api/v1/admin/roles",
        json={
            "name": "bad_scope",
            "permissions": ["action:read"],
            "ad_groups": ["GRP-BAD"],
            "area_scope": [""],
        },
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 422


async def test_create_role_area_scope_whitespace_returns_422(client):
    resp = await client.post(
        "/api/v1/admin/roles",
        json={
            "name": "bad_scope",
            "permissions": ["action:read"],
            "ad_groups": ["GRP-BAD"],
            "area_scope": ["   "],
        },
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 422


async def test_create_role_area_scope_null_accepted(client):
    resp = await client.post(
        "/api/v1/admin/roles",
        json={
            "name": "full_plant_role",
            "permissions": ["action:read"],
            "ad_groups": ["GRP-FP"],
            "area_scope": None,
        },
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["area_scope"] is None
