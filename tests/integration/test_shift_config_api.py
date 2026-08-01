"""Integration tests for the shift-configuration admin API (US-008 ES-308, memory backend)."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.deps import _shift_config_repo
from src.core.config import get_settings
from src.infrastructure.persistence.in_memory_shift_config import seed_shift_configuration
from src.main import app
from tests.helpers import bearer

ADMIN = bearer("admin.user", ["OLNG-ELOG-ADMINS"])
OPERATOR = bearer("jane.operator", ["OLNG-ELOG-OPERATORS"])
SUPERVISOR = bearer("sam.super", ["OLNG-ELOG-SUPERVISORS"])


@pytest.fixture(autouse=True)
def _reset_state():
    """Isolate tests: reset the in-memory shift-config store to a fresh seed row."""

    def _reseed():
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


async def test_get_effective_config_as_admin_returns_seeded_defaults(client):
    resp = await client.get("/api/v1/admin/config/shift", headers={"Authorization": ADMIN})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["start_hour"] == 6
    assert data["hours"] == 12
    assert data["overlap_minutes"] == 15
    assert data["area"] is None
    assert data["version"] == 1


async def test_get_effective_config_as_operator_is_forbidden(client):
    resp = await client.get("/api/v1/admin/config/shift", headers={"Authorization": OPERATOR})
    assert resp.status_code == 403


async def test_post_as_admin_succeeds_and_get_reflects_it(client):
    create = await client.post(
        "/api/v1/admin/config/shift",
        headers={"Authorization": ADMIN},
        json={
            "area": None,
            "start_hour": 7,
            "hours": 12,
            "overlap_minutes": 20,
            "effective_from": "2026-06-01T00:00:00+00:00",
            "expected_version": 1,
        },
    )
    assert create.status_code == 200
    created = create.json()["data"]
    assert created["version"] == 2
    assert created["start_hour"] == 7

    fetched = await client.get("/api/v1/admin/config/shift", headers={"Authorization": ADMIN})
    assert fetched.json()["data"]["start_hour"] == 7
    assert fetched.json()["data"]["version"] == 2


async def test_post_as_supervisor_is_forbidden(client):
    resp = await client.post(
        "/api/v1/admin/config/shift",
        headers={"Authorization": SUPERVISOR},
        json={
            "area": None,
            "start_hour": 7,
            "hours": 12,
            "overlap_minutes": 20,
            "effective_from": "2026-06-01T00:00:00+00:00",
            "expected_version": 1,
        },
    )
    assert resp.status_code == 403


async def test_post_naive_effective_from_is_unprocessable(client):
    """A naive (no UTC offset) effective_from must be rejected at the boundary (422),

    not accepted and left to fail later when compared against tz-aware rows.
    """
    resp = await client.post(
        "/api/v1/admin/config/shift",
        headers={"Authorization": ADMIN},
        json={
            "area": None,
            "start_hour": 7,
            "hours": 12,
            "overlap_minutes": 15,
            "effective_from": "2026-06-01T00:00:00",  # no offset
            "expected_version": 1,
        },
    )
    assert resp.status_code == 422


async def test_post_invalid_start_hour_is_unprocessable(client):
    resp = await client.post(
        "/api/v1/admin/config/shift",
        headers={"Authorization": ADMIN},
        json={
            "area": None,
            "start_hour": 25,
            "hours": 12,
            "overlap_minutes": 15,
            "effective_from": "2026-06-01T00:00:00+00:00",
            "expected_version": 1,
        },
    )
    assert resp.status_code == 422


async def test_post_stale_expected_version_is_conflict(client):
    resp = await client.post(
        "/api/v1/admin/config/shift",
        headers={"Authorization": ADMIN},
        json={
            "area": None,
            "start_hour": 7,
            "hours": 12,
            "overlap_minutes": 15,
            "effective_from": "2026-06-01T00:00:00+00:00",
            "expected_version": 99,
        },
    )
    assert resp.status_code == 409


async def test_post_retro_dated_effective_from_is_conflict(client):
    resp = await client.post(
        "/api/v1/admin/config/shift",
        headers={"Authorization": ADMIN},
        json={
            "area": None,
            "start_hour": 7,
            "hours": 12,
            "overlap_minutes": 15,
            "effective_from": "1899-01-01T00:00:00+00:00",
            "expected_version": 1,
        },
    )
    assert resp.status_code == 409


async def test_history_is_empty_under_memory_backend(client):
    resp = await client.get("/api/v1/admin/config/shift/history", headers={"Authorization": ADMIN})
    assert resp.status_code == 200
    assert resp.json()["data"] == []


async def test_history_as_operator_is_forbidden(client):
    resp = await client.get(
        "/api/v1/admin/config/shift/history", headers={"Authorization": OPERATOR}
    )
    assert resp.status_code == 403


async def test_versions_endpoint_lists_newest_first(client):
    await client.post(
        "/api/v1/admin/config/shift",
        headers={"Authorization": ADMIN},
        json={
            "area": None,
            "start_hour": 7,
            "hours": 12,
            "overlap_minutes": 15,
            "effective_from": "2026-06-01T00:00:00+00:00",
            "expected_version": 1,
        },
    )
    resp = await client.get("/api/v1/admin/config/shift/versions", headers={"Authorization": ADMIN})
    assert resp.status_code == 200
    versions = [v["version"] for v in resp.json()["data"]]
    assert versions == sorted(versions, reverse=True)
    assert versions[0] == 2


async def test_shifts_current_reflects_newly_posted_start_hour(client):
    """End-to-end wiring proof (ES-309): GET /shifts/current resolves via the config store.

    Doesn't assert against the wall clock directly (the endpoint always resolves "now").
    Instead: with the default config (start_hour=6, hours=12) windows begin at 06:00 or
    18:00; after posting start_hour=7 they begin at 07:00 or 19:00 — a disjoint set of
    hours — so seeing the new set proves the endpoint picked up the posted change.
    """
    await client.post(
        "/api/v1/admin/config/shift",
        headers={"Authorization": ADMIN},
        json={
            "area": None,
            "start_hour": 7,
            "hours": 12,
            "overlap_minutes": 15,
            "effective_from": "2020-01-01T00:00:00+00:00",
            "expected_version": 1,
        },
    )

    after = await client.get("/api/v1/shifts/current", headers={"Authorization": ADMIN})
    assert after.status_code == 200
    starts_at_hour = int(after.json()["data"]["starts_at"][11:13])
    assert starts_at_hour in (7, 19)
