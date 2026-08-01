"""Integration tests for area-based data scope on GET /shifts/current
(US-007 ES-305/306/307).

Touches both the role store (custom scoped roles) and the shift-config store (US-008),
so the reset fixture below clears both — mirrors ``test_admin_roles_api.py``'s role
reset and ``test_shift_config_api.py``'s shift-config reset combined.
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
# super_user holds no shift:read permission at all (see BASE_ROLES) -> used to prove the
# permission gate fires before the scope logic ever runs.
NO_SHIFT_PERMISSION = bearer("sam.super", ["OLNG-ELOG-SUPERUSERS"])


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


async def test_full_plant_operator_narrows_with_area_param(client):
    resp = await client.get(
        "/api/v1/shifts/current",
        headers={"Authorization": OPERATOR},
        params={"area": "Train 1"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["scope"] == ["Train 1"]


async def test_empty_area_param_is_unprocessable(client):
    resp = await client.get(
        "/api/v1/shifts/current", headers={"Authorization": OPERATOR}, params={"area": ""}
    )
    assert resp.status_code == 422


# --- ES-307: custom-role scoped narrow/reject, end-to-end -----------------------------


async def test_scoped_role_matching_area_param_succeeds(client):
    await _create_scoped_role(client, "train1_operator", "OLNG-ELOG-TRAIN1", ["Train 1"])
    scoped_token = bearer("t1.operator", ["OLNG-ELOG-TRAIN1"])

    resp = await client.get(
        "/api/v1/shifts/current",
        headers={"Authorization": scoped_token},
        params={"area": "Train 1"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["scope"] == ["Train 1"]


async def test_scoped_role_out_of_scope_area_param_is_forbidden(client):
    await _create_scoped_role(client, "train1_operator", "OLNG-ELOG-TRAIN1", ["Train 1"])
    scoped_token = bearer("t1.operator", ["OLNG-ELOG-TRAIN1"])

    resp = await client.get(
        "/api/v1/shifts/current",
        headers={"Authorization": scoped_token},
        params={"area": "Train 2"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


async def test_role_scoped_to_two_areas_no_param_falls_back_to_plant_wide(client):
    """Ambiguous (which of the two areas?) -> falls back to the plant-wide shift
    configuration rather than guessing; the scope itself still reports both areas.
    """
    await _create_scoped_role(
        client, "train12b_operator", "OLNG-ELOG-TRAIN12B", ["Train 1", "Train 2"]
    )
    scoped_token = bearer("t12b.operator", ["OLNG-ELOG-TRAIN12B"])

    resp = await client.get("/api/v1/shifts/current", headers={"Authorization": scoped_token})
    assert resp.status_code == 200
    assert resp.json()["data"]["area"] is None


async def test_permission_check_happens_before_scope_check(client):
    """A caller without shift:read at all gets 403 for the permission reason, even with
    ?area= set -- the router-level permission gate must run before the scope logic in
    the endpoint body ever executes.
    """
    resp = await client.get(
        "/api/v1/shifts/current",
        headers={"Authorization": NO_SHIFT_PERMISSION},
        params={"area": "Train 1"},
    )
    assert resp.status_code == 403
    body = resp.json()
    assert body["error"]["code"] == "forbidden"
    assert "permission" in body["error"]["message"].lower()


async def test_no_area_specific_config_yet_falls_back_to_plant_wide_and_reports_it(client):
    """Neither an explicit ?area= nor a single-area role's own scope should claim credit
    for a shift window that was actually resolved from the plant-wide configuration —
    the response's ``area`` must honestly report the fallback (``None``), not the
    requested/scoped area, when that area has no configuration of its own yet.
    """
    await _create_scoped_role(client, "train1_operator", "OLNG-ELOG-TRAIN1", ["Train 1"])
    scoped_token = bearer("t1.operator", ["OLNG-ELOG-TRAIN1"])

    no_param = await client.get("/api/v1/shifts/current", headers={"Authorization": scoped_token})
    assert no_param.json()["data"]["area"] is None
    assert int(no_param.json()["data"]["starts_at"][11:13]) in (6, 18)

    with_param = await client.get(
        "/api/v1/shifts/current",
        headers={"Authorization": OPERATOR},
        params={"area": "Train 1"},
    )
    assert with_param.json()["data"]["area"] is None
    assert int(with_param.json()["data"]["starts_at"][11:13]) in (6, 18)


async def test_area_specific_shift_config_is_actually_used(client):
    """End-to-end wiring proof: a Train-1-scoped caller sees the Train-1 configuration
    while a full-plant caller does not. Uses the disjoint-hours trick: the default seed
    windows begin at 06:00/18:00, the posted Train-1 config at 08:00/20:00 -- a disjoint
    set of hours, so seeing the new set proves the area->config wiring, not just that
    the ``area`` field gets echoed back.
    """
    await _create_scoped_role(client, "train1_operator", "OLNG-ELOG-TRAIN1", ["Train 1"])
    scoped_token = bearer("t1.operator", ["OLNG-ELOG-TRAIN1"])

    post = await client.post(
        "/api/v1/admin/config/shift",
        headers={"Authorization": ADMIN},
        json={
            "area": "Train 1",
            "start_hour": 8,
            "hours": 12,
            "overlap_minutes": 15,
            "effective_from": "1950-01-01T00:00:00+00:00",
            "expected_version": 0,
        },
    )
    assert post.status_code == 200, post.text

    scoped_resp = await client.get(
        "/api/v1/shifts/current", headers={"Authorization": scoped_token}
    )
    assert scoped_resp.status_code == 200
    scoped_data = scoped_resp.json()["data"]
    scoped_hour = int(scoped_data["starts_at"][11:13])
    assert scoped_hour in (8, 20)
    assert scoped_data["area"] == "Train 1"
    assert scoped_data["shift_id"]
    assert scoped_data["label"] in {"Day", "Night"}
    assert scoped_data["ends_at"]
    assert scoped_data["overlap_minutes"] == 15

    plant_resp = await client.get("/api/v1/shifts/current", headers={"Authorization": OPERATOR})
    assert plant_resp.status_code == 200
    plant_hour = int(plant_resp.json()["data"]["starts_at"][11:13])
    assert plant_hour in (6, 18)
    assert plant_hour != scoped_hour


async def test_area_specific_config_with_explicit_area_param_response_well_formed(client):
    """Same wiring proof, but hitting the endpoint with an explicit ``?area=`` this time."""
    await _create_scoped_role(client, "train1_operator", "OLNG-ELOG-TRAIN1", ["Train 1"])
    scoped_token = bearer("t1.operator", ["OLNG-ELOG-TRAIN1"])

    await client.post(
        "/api/v1/admin/config/shift",
        headers={"Authorization": ADMIN},
        json={
            "area": "Train 1",
            "start_hour": 8,
            "hours": 12,
            "overlap_minutes": 15,
            "effective_from": "1950-01-01T00:00:00+00:00",
            "expected_version": 0,
        },
    )

    resp = await client.get(
        "/api/v1/shifts/current",
        headers={"Authorization": scoped_token},
        params={"area": "Train 1"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["shift_id"]
    assert data["label"] in {"Day", "Night"}
    assert data["starts_at"]
    assert data["ends_at"]
    assert data["overlap_minutes"] == 15
    assert data["area"] == "Train 1"
    assert data["scope"] == ["Train 1"]


async def test_two_separate_single_area_roles_union_to_full_plant(client):
    """The genuine multi-role case (ES-307): two DISTINCT custom roles/AD-groups, each
    scoped to its own single, non-overlapping area, held by the same user at once —
    not one role with a two-element ``area_scope`` (that's ``test_role_scoped_to_two_
    areas_no_param_falls_back_to_plant_wide`` above, a different code path since it
    never touches ``area_scope_for_roles``' cross-role union). ``sole_area`` only ever
    sees the already-unioned list, so this must degrade the same way: full-plant, not an
    error and not an arbitrary pick of either area.
    """
    await _create_scoped_role(client, "train1_operator", "OLNG-ELOG-TRAIN1B", ["Train 1"])
    await _create_scoped_role(client, "train2_operator", "OLNG-ELOG-TRAIN2B", ["Train 2"])
    both_groups_token = bearer("dual.operator", ["OLNG-ELOG-TRAIN1B", "OLNG-ELOG-TRAIN2B"])

    resp = await client.get("/api/v1/shifts/current", headers={"Authorization": both_groups_token})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert sorted(data["scope"]) == ["Train 1", "Train 2"]
    assert data["area"] is None  # sole_area is ambiguous across two roles -> plant-wide
