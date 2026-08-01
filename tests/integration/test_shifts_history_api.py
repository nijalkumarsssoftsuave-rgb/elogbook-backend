"""Integration tests for the shift-history list endpoint (US-009 ES-312).

Pagination/sort response-shape tests land in ES-314; ``GET /shifts/{id}`` is ES-313.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.deps import _role_repo, _shift_config_repo
from src.core.config import get_settings
from src.domain.users_roles.seed import BASE_ROLES
from src.infrastructure.persistence.in_memory_shift_config import seed_shift_configuration
from src.main import app
from tests.helpers import bearer

ADMIN = bearer("admin.user", ["OLNG-ELOG-ADMINS"])
OPERATOR = bearer("jane.operator", ["OLNG-ELOG-OPERATORS"])
NO_SHIFT_PERMISSION = bearer("sam.super", ["OLNG-ELOG-SUPERUSERS"])


@pytest.fixture(autouse=True)
def _reset_state():
    def _reseed():
        _role_repo._items = {r.id: r for r in BASE_ROLES}
        seed = seed_shift_configuration(get_settings())
        _shift_config_repo._items = {seed.id: seed}

    _reseed()
    get_settings.cache_clear()
    yield
    _reseed()
    get_settings.cache_clear()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_valid_range_returns_the_expected_shifts(client):
    resp = await client.get(
        "/api/v1/shifts",
        headers={"Authorization": OPERATOR},
        params={"date_from": "2026-07-30", "date_to": "2026-07-30"},
    )
    assert resp.status_code == 200
    ids = [item["shift_id"] for item in resp.json()["data"]]
    assert ids == ["20260730-D", "20260730-N"]


async def test_date_from_after_date_to_is_unprocessable(client):
    resp = await client.get(
        "/api/v1/shifts",
        headers={"Authorization": OPERATOR},
        params={"date_from": "2026-07-31", "date_to": "2026-07-30"},
    )
    assert resp.status_code == 422


async def test_span_over_max_days_is_unprocessable(client):
    resp = await client.get(
        "/api/v1/shifts",
        headers={"Authorization": OPERATOR},
        params={"date_from": "2020-01-01", "date_to": "2026-12-31"},
    )
    assert resp.status_code == 422


async def test_malformed_date_from_is_unprocessable(client):
    resp = await client.get(
        "/api/v1/shifts",
        headers={"Authorization": OPERATOR},
        params={"date_from": "not-a-date", "date_to": "2026-07-30"},
    )
    assert resp.status_code == 422


async def test_missing_required_date_params_is_unprocessable(client):
    resp = await client.get("/api/v1/shifts", headers={"Authorization": OPERATOR})
    assert resp.status_code == 422


async def test_empty_area_param_is_unprocessable(client):
    resp = await client.get(
        "/api/v1/shifts",
        headers={"Authorization": OPERATOR},
        params={"date_from": "2026-07-30", "date_to": "2026-07-30", "area": ""},
    )
    assert resp.status_code == 422


async def test_scoped_role_out_of_scope_area_is_forbidden(client):
    resp = await client.post(
        "/api/v1/admin/roles",
        headers={"Authorization": ADMIN},
        json={
            "name": "train1_operator",
            "permissions": ["shift:read"],
            "ad_groups": ["OLNG-ELOG-TRAIN1"],
            "area_scope": ["Train 1"],
        },
    )
    assert resp.status_code == 200
    scoped_token = bearer("t1.operator", ["OLNG-ELOG-TRAIN1"])

    resp = await client.get(
        "/api/v1/shifts",
        headers={"Authorization": scoped_token},
        params={"date_from": "2026-07-30", "date_to": "2026-07-30", "area": "Train 2"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


async def test_no_shift_read_permission_is_forbidden(client):
    resp = await client.get(
        "/api/v1/shifts",
        headers={"Authorization": NO_SHIFT_PERMISSION},
        params={"date_from": "2026-07-30", "date_to": "2026-07-30"},
    )
    assert resp.status_code == 403


async def test_no_auth_token_is_unauthorized(client):
    resp = await client.get(
        "/api/v1/shifts", params={"date_from": "2026-07-30", "date_to": "2026-07-30"}
    )
    assert resp.status_code == 401


async def test_shifts_current_still_works_after_schema_refactor_and_route_reordering(client):
    """Guards against the FastAPI route-collision hazard: /shifts (a new static route)
    and /shifts/current must both keep matching correctly, never getting swallowed by
    a catch-all path param declared elsewhere.
    """
    resp = await client.get("/api/v1/shifts/current", headers={"Authorization": OPERATOR})
    assert resp.status_code == 200
    assert resp.json()["data"]["shift_id"]
