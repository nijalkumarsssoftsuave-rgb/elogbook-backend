"""Integration tests for ES-365 / ES-366: API-layer enforcement and bypass resistance.

Proves that every protected endpoint independently authorises the caller — regardless
of what the UI shows or hides. An attacker who knows the endpoint URL and crafts a
direct HTTP request is denied with the correct error code.

Test matrix for each endpoint:
  - No Authorization header         → 401 unauthorized
  - Valid token, wrong permission   → 403 forbidden
  - Valid token, correct permission → 2xx (positive-control spot-checks)

Actors used:
  ADMIN      — OLNG-ELOG-ADMINS        → permissions ["*"]
  OPERATOR   — OLNG-ELOG-OPERATORS     → shift:read, action:read, action:write (no role:*)
  MANAGEMENT — OLNG-ELOG-SUPERINTENDENTS → shift:read, action:read, report:read (no action:write)
  SUPER_USER — OLNG-ELOG-SUPERUSERS    → dashboard/widget/metric/access/user (no shift/action/role)
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.deps import _pending_action_repo, _role_repo
from src.core.config import get_settings
from src.domain.users_roles.seed import BASE_ROLES
from src.main import app
from tests.helpers import bearer

ADMIN = bearer("admin.user", ["OLNG-ELOG-ADMINS"])
OPERATOR = bearer("jane.operator", ["OLNG-ELOG-OPERATORS"])
MANAGEMENT = bearer("mgmt.user", ["OLNG-ELOG-SUPERINTENDENTS"])
SUPER_USER = bearer("super.user", ["OLNG-ELOG-SUPERUSERS"])

FAKE_ID = "00000000000000000000000000000000"


@pytest.fixture(autouse=True)
def _reset_state():
    _pending_action_repo._items.clear()
    _role_repo._items = {r.id: r for r in BASE_ROLES}
    get_settings.cache_clear()
    yield
    _pending_action_repo._items.clear()
    _role_repo._items = {r.id: r for r in BASE_ROLES}
    get_settings.cache_clear()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# GET /me — authentication required (no specific permission)
# ---------------------------------------------------------------------------


async def test_me_no_token_returns_401(client):
    resp = await client.get("/api/v1/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


async def test_me_valid_token_returns_200(client):
    resp = await client.get("/api/v1/me", headers={"Authorization": OPERATOR})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /shifts/current — requires shift:read
# ---------------------------------------------------------------------------


async def test_shifts_current_no_token_returns_401(client):
    resp = await client.get("/api/v1/shifts/current")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


async def test_shifts_current_no_shift_read_returns_403(client):
    resp = await client.get("/api/v1/shifts/current", headers={"Authorization": SUPER_USER})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


async def test_shifts_current_with_shift_read_returns_200(client):
    resp = await client.get("/api/v1/shifts/current", headers={"Authorization": OPERATOR})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /shifts/{id} — requires shift:read
# ---------------------------------------------------------------------------


async def test_shifts_by_id_no_token_returns_401(client):
    resp = await client.get("/api/v1/shifts/day-1")
    assert resp.status_code == 401


async def test_shifts_by_id_no_shift_read_returns_403(client):
    resp = await client.get("/api/v1/shifts/day-1", headers={"Authorization": SUPER_USER})
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /pending-actions — requires action:read
# ---------------------------------------------------------------------------


async def test_list_actions_no_token_returns_401(client):
    resp = await client.get("/api/v1/pending-actions")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


async def test_list_actions_no_action_read_returns_403(client):
    resp = await client.get("/api/v1/pending-actions", headers={"Authorization": SUPER_USER})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


async def test_list_actions_with_action_read_returns_200(client):
    resp = await client.get("/api/v1/pending-actions", headers={"Authorization": OPERATOR})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /pending-actions/{id} — requires action:read
# ---------------------------------------------------------------------------


async def test_get_action_no_token_returns_401(client):
    resp = await client.get(f"/api/v1/pending-actions/{FAKE_ID}")
    assert resp.status_code == 401


async def test_get_action_no_action_read_returns_403(client):
    resp = await client.get(
        f"/api/v1/pending-actions/{FAKE_ID}", headers={"Authorization": SUPER_USER}
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /pending-actions — requires action:write
# ---------------------------------------------------------------------------


async def test_create_action_no_token_returns_401(client):
    resp = await client.post(
        "/api/v1/pending-actions",
        json={"issue": "Test issue"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


async def test_create_action_no_action_write_returns_403(client):
    # management has action:read but NOT action:write
    resp = await client.post(
        "/api/v1/pending-actions",
        json={"issue": "Test issue"},
        headers={"Authorization": MANAGEMENT},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


async def test_create_action_with_action_write_returns_200(client):
    resp = await client.post(
        "/api/v1/pending-actions",
        json={"issue": "Test issue"},
        headers={"Authorization": OPERATOR},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# PATCH /pending-actions/{id}/transition — requires action:write
# ---------------------------------------------------------------------------


async def test_transition_action_no_token_returns_401(client):
    resp = await client.patch(
        f"/api/v1/pending-actions/{FAKE_ID}/transition",
        json={"target": "In Progress"},
    )
    assert resp.status_code == 401


async def test_transition_action_no_action_write_returns_403(client):
    resp = await client.patch(
        f"/api/v1/pending-actions/{FAKE_ID}/transition",
        json={"target": "In Progress"},
        headers={"Authorization": MANAGEMENT},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /admin/roles — requires role:read
# ---------------------------------------------------------------------------


async def test_list_roles_no_token_returns_401(client):
    resp = await client.get("/api/v1/admin/roles")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


async def test_list_roles_no_role_read_returns_403(client):
    # operator has action:read/write and shift:read but no role:read
    resp = await client.get("/api/v1/admin/roles", headers={"Authorization": OPERATOR})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


async def test_list_roles_with_role_read_returns_200(client):
    resp = await client.get("/api/v1/admin/roles", headers={"Authorization": ADMIN})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /admin/roles/mapping — requires role:read
# ---------------------------------------------------------------------------


async def test_role_mapping_no_token_returns_401(client):
    resp = await client.get("/api/v1/admin/roles/mapping")
    assert resp.status_code == 401


async def test_role_mapping_no_role_read_returns_403(client):
    resp = await client.get("/api/v1/admin/roles/mapping", headers={"Authorization": OPERATOR})
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /admin/roles/{id}/history — requires role:read
# ---------------------------------------------------------------------------


async def test_role_history_no_token_returns_401(client):
    resp = await client.get(f"/api/v1/admin/roles/{FAKE_ID}/history")
    assert resp.status_code == 401


async def test_role_history_no_role_read_returns_403(client):
    resp = await client.get(
        f"/api/v1/admin/roles/{FAKE_ID}/history", headers={"Authorization": OPERATOR}
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /admin/roles — requires role:manage
# ---------------------------------------------------------------------------


async def test_create_role_no_token_returns_401(client):
    resp = await client.post(
        "/api/v1/admin/roles",
        json={"name": "test_role", "permissions": ["action:read"], "ad_groups": ["GRP"]},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


async def test_create_role_no_role_manage_returns_403(client):
    # operator has role:read? No — operator has NO role:* permissions at all
    resp = await client.post(
        "/api/v1/admin/roles",
        json={"name": "test_role", "permissions": ["action:read"], "ad_groups": ["GRP"]},
        headers={"Authorization": OPERATOR},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


async def test_create_role_with_role_manage_returns_200(client):
    resp = await client.post(
        "/api/v1/admin/roles",
        json={"name": "test_role", "permissions": ["action:read"], "ad_groups": ["GRP"]},
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# PATCH /admin/roles/{id} — requires role:manage
# ---------------------------------------------------------------------------


async def test_update_role_no_token_returns_401(client):
    resp = await client.patch(
        f"/api/v1/admin/roles/{FAKE_ID}",
        json={"name": "new_name"},
    )
    assert resp.status_code == 401


async def test_update_role_no_role_manage_returns_403(client):
    resp = await client.patch(
        f"/api/v1/admin/roles/{FAKE_ID}",
        json={"name": "new_name"},
        headers={"Authorization": OPERATOR},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /admin/roles/{id} — requires role:manage
# ---------------------------------------------------------------------------


async def test_delete_role_no_token_returns_401(client):
    resp = await client.delete(f"/api/v1/admin/roles/{FAKE_ID}")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


async def test_delete_role_no_role_manage_returns_403(client):
    resp = await client.delete(
        f"/api/v1/admin/roles/{FAKE_ID}", headers={"Authorization": OPERATOR}
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


# ---------------------------------------------------------------------------
# Public endpoints are reachable without any token
# ---------------------------------------------------------------------------


async def test_health_is_public(client):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200


async def test_dev_token_endpoint_is_public(client):
    resp = await client.post(
        "/api/v1/dev/token",
        json={"username": "anyone", "groups": ["OLNG-ELOG-OPERATORS"]},
    )
    assert resp.status_code == 200
