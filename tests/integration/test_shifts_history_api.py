"""Integration tests for the shift-history endpoints (US-009 ES-312/313/314)."""

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
    data = resp.json()["data"]
    ids = [item["shift_id"] for item in data["items"]]
    assert ids == ["20260730-N", "20260730-D"]  # default sort is starts_at:desc
    assert data["page"] == 1
    assert data["total"] == 2


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


async def test_page_size_above_max_is_unprocessable(client):
    resp = await client.get(
        "/api/v1/shifts",
        headers={"Authorization": OPERATOR},
        params={"date_from": "2026-07-28", "date_to": "2026-07-30", "page_size": 500},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


async def test_page_size_omitted_uses_default(client):
    resp = await client.get(
        "/api/v1/shifts",
        headers={"Authorization": OPERATOR},
        params={"date_from": "2026-07-28", "date_to": "2026-07-30"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["page_size"] == 20  # settings default


async def test_page_2_returns_a_disjoint_slice_from_page_1(client):
    common = {"date_from": "2026-07-28", "date_to": "2026-07-30", "page_size": 4}
    page1 = await client.get(
        "/api/v1/shifts", headers={"Authorization": OPERATOR}, params={**common, "page": 1}
    )
    page2 = await client.get(
        "/api/v1/shifts", headers={"Authorization": OPERATOR}, params={**common, "page": 2}
    )
    ids1 = {item["shift_id"] for item in page1.json()["data"]["items"]}
    ids2 = {item["shift_id"] for item in page2.json()["data"]["items"]}
    assert ids1.isdisjoint(ids2)
    assert len(ids1) == 4
    assert len(ids2) == 2


async def test_sort_asc_reverses_the_default_order(client):
    desc = await client.get(
        "/api/v1/shifts",
        headers={"Authorization": OPERATOR},
        params={"date_from": "2026-07-30", "date_to": "2026-07-30"},
    )
    asc = await client.get(
        "/api/v1/shifts",
        headers={"Authorization": OPERATOR},
        params={"date_from": "2026-07-30", "date_to": "2026-07-30", "sort": "starts_at:asc"},
    )
    assert [i["shift_id"] for i in asc.json()["data"]["items"]] == list(
        reversed([i["shift_id"] for i in desc.json()["data"]["items"]])
    )


async def test_invalid_sort_value_is_unprocessable(client):
    resp = await client.get(
        "/api/v1/shifts",
        headers={"Authorization": OPERATOR},
        params={"date_from": "2026-07-30", "date_to": "2026-07-30", "sort": "garbage"},
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


# --- GET /shifts/{shift_id} (ES-313) -----------------------------------------------------


async def test_fetch_by_id_using_an_id_taken_from_the_list_matches(client):
    listed = await client.get(
        "/api/v1/shifts",
        headers={"Authorization": OPERATOR},
        params={"date_from": "2026-07-30", "date_to": "2026-07-30"},
    )
    shift_id = listed.json()["data"]["items"][0]["shift_id"]

    resp = await client.get(f"/api/v1/shifts/{shift_id}", headers={"Authorization": OPERATOR})
    assert resp.status_code == 200
    assert resp.json()["data"]["shift_id"] == shift_id


async def test_unknown_shift_id_is_not_found(client):
    """Direct regression against the old stub, which returned HTTP 200 with
    {"detail": "not yet implemented"} for ANY id — a client couldn't distinguish that
    fake success from a real one.
    """
    resp = await client.get("/api/v1/shifts/20260730-Z999", headers={"Authorization": OPERATOR})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


async def test_malformed_shift_id_is_not_found(client):
    resp = await client.get("/api/v1/shifts/garbage", headers={"Authorization": OPERATOR})
    assert resp.status_code == 404


@pytest.mark.parametrize("shift_id", ["99991231-D", "00010101-D"])
async def test_calendar_valid_but_implausible_year_is_not_found_not_a_server_error(
    client, shift_id
):
    """Regression: an implausible-but-calendar-valid year (accepted by ``parse_shift_id``,
    since ``datetime.strptime`` allows years 1-9999) used to overflow ``datetime``'s own
    MINYEAR/MAXYEAR bounds inside the enumeration window arithmetic, raising an unhandled
    ``OverflowError`` -> 500 instead of the clean 404 a nonexistent id should produce.
    """
    resp = await client.get(f"/api/v1/shifts/{shift_id}", headers={"Authorization": OPERATOR})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


async def test_id_belonging_to_a_different_area_is_not_found_for_an_implicitly_scoped_caller(
    client,
):
    """An area-A-scoped caller who never passes ``?area=`` still must not be able to
    fetch a shift id that only exists under area B's own derivation — the lookup runs
    entirely within the caller's own effective area, so a real id from a different
    area simply isn't there (404), distinct from the explicit-``?area=`` 403 path
    already covered by ``test_out_of_scope_area_on_by_id_is_forbidden``.
    """
    await client.post(
        "/api/v1/admin/roles",
        headers={"Authorization": ADMIN},
        json={
            "name": "train1_implicit_operator",
            "permissions": ["shift:read"],
            "ad_groups": ["OLNG-ELOG-TRAIN1C"],
            "area_scope": ["Train 1"],
        },
    )
    train1_token = bearer("t1c.operator", ["OLNG-ELOG-TRAIN1C"])

    # hours=8 (not 12): a 12-hour config's id is just "-D"/"-N" for EVERY area on EVERY
    # date regardless of start_hour, so Train 1's own plant-wide-fallback derivation
    # would coincidentally produce the identical id string for its own, different Day
    # shift -- not a genuine "belongs only to Train 2" case. hours=8 -> "-S1"/"-S2"/"-S3"
    # ids, a shape Train 1's plant-wide (hours=12) fallback never produces, so a match
    # here can only mean Train 1's own scope actually contains this id.
    post = await client.post(
        "/api/v1/admin/config/shift",
        headers={"Authorization": ADMIN},
        json={
            "area": "Train 2",
            "start_hour": 10,
            "hours": 8,
            "overlap_minutes": 15,
            "effective_from": "1950-01-01T00:00:00+00:00",
            "expected_version": 0,
        },
    )
    assert post.status_code == 200, post.text

    train2_listed = await client.get(
        "/api/v1/shifts",
        headers={"Authorization": ADMIN},
        params={"date_from": "2026-07-30", "date_to": "2026-07-30", "area": "Train 2"},
    )
    train2_shift_id = train2_listed.json()["data"]["items"][0]["shift_id"]

    resp = await client.get(
        f"/api/v1/shifts/{train2_shift_id}", headers={"Authorization": train1_token}
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


async def test_out_of_scope_area_on_by_id_is_forbidden(client):
    resp = await client.post(
        "/api/v1/admin/roles",
        headers={"Authorization": ADMIN},
        json={
            "name": "train1_operator2",
            "permissions": ["shift:read"],
            "ad_groups": ["OLNG-ELOG-TRAIN1B"],
            "area_scope": ["Train 1"],
        },
    )
    scoped_token = bearer("t1b.operator", ["OLNG-ELOG-TRAIN1B"])

    resp = await client.get(
        "/api/v1/shifts/20260730-D",
        headers={"Authorization": scoped_token},
        params={"area": "Train 2"},
    )
    assert resp.status_code == 403


async def test_no_permission_at_all_is_forbidden_on_by_id(client):
    resp = await client.get(
        "/api/v1/shifts/20260730-D", headers={"Authorization": NO_SHIFT_PERMISSION}
    )
    assert resp.status_code == 403


async def test_no_auth_token_is_unauthorized_on_by_id(client):
    resp = await client.get("/api/v1/shifts/20260730-D")
    assert resp.status_code == 401
