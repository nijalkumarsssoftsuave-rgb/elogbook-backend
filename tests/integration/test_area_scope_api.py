"""Integration tests for area-based data scope on GET /shifts/current (US-007 ES-305).

Touches both the role store (custom scoped roles) and the shift-config store (US-008),
so the reset fixture below clears both — mirrors ``test_admin_roles_api.py``'s role
reset and ``test_shift_config_api.py``'s shift-config reset combined. Narrowing via
``?area=`` is ES-306 and is tested there once the endpoint supports it.
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


@pytest.fixture(autouse=True)
def _reset_state():
    """Isolate tests: reset both the role store and the shift-config store."""

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


async def _create_scoped_role(client, name, ad_group, area_scope):
    resp = await client.post(
        "/api/v1/admin/roles",
        headers={"Authorization": ADMIN},
        json={
            # must include shift:read or a scope test misdiagnoses a permission 403 as a
            # scope failure.
            "name": name,
            "permissions": ["shift:read"],
            "ad_groups": [ad_group],
            "area_scope": area_scope,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def test_full_plant_operator_scope_is_null(client):
    resp = await client.get("/api/v1/shifts/current", headers={"Authorization": OPERATOR})
    assert resp.status_code == 200
    assert resp.json()["data"]["scope"] is None


async def test_scoped_role_sees_its_own_scope_by_default(client):
    await _create_scoped_role(client, "train1_operator", "OLNG-ELOG-TRAIN1", ["Train 1"])
    scoped_token = bearer("t1.operator", ["OLNG-ELOG-TRAIN1"])

    resp = await client.get("/api/v1/shifts/current", headers={"Authorization": scoped_token})
    assert resp.status_code == 200
    assert resp.json()["data"]["scope"] == ["Train 1"]


async def test_role_scoped_to_two_areas_shows_both(client):
    await _create_scoped_role(
        client, "train12_operator", "OLNG-ELOG-TRAIN12", ["Train 1", "Train 2"]
    )
    scoped_token = bearer("t12.operator", ["OLNG-ELOG-TRAIN12"])

    resp = await client.get("/api/v1/shifts/current", headers={"Authorization": scoped_token})
    assert resp.status_code == 200
    assert set(resp.json()["data"]["scope"]) == {"Train 1", "Train 2"}
