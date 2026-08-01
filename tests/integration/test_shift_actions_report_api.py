"""Integration tests for the shift-actions report endpoint (ES-344)."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.deps import _pending_action_repo
from src.core.config import get_settings
from src.main import app
from tests.helpers import bearer

OPERATOR = bearer("jane.operator", ["OLNG-ELOG-OPERATORS"])
SCOPED = bearer("t1.operator", ["OLNG-ELOG-TRAIN1"])


@pytest.fixture(autouse=True)
def _reset_state():
    _pending_action_repo._items.clear()
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _current_shift_id(client) -> str:
    resp = await client.get("/api/v1/shifts/current", headers={"Authorization": OPERATOR})
    return resp.json()["data"]["shift_id"]


async def test_confirmed_actions_appear_in_the_shift_report(client):
    await client.post(
        "/api/v1/pending-actions",
        headers={"Authorization": OPERATOR},
        json={"issue": "Inspect PSV on V-101"},
    )
    shift_id = await _current_shift_id(client)

    resp = await client.get(
        f"/api/v1/shifts/{shift_id}/actions", headers={"Authorization": OPERATOR}
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["shift_id"] == shift_id
    assert [a["issue"] for a in body["actions"]] == ["Inspect PSV on V-101"]


async def test_malformed_shift_id_is_a_validation_error(client):
    resp = await client.get(
        "/api/v1/shifts/not-a-real-id/actions", headers={"Authorization": OPERATOR}
    )
    assert resp.status_code == 422


async def test_report_respects_area_scope(client):
    await client.post(
        "/api/v1/admin/roles",
        headers={"Authorization": bearer("admin.user", ["OLNG-ELOG-ADMINS"])},
        json={
            "name": "train1_operator",
            "permissions": ["action:read", "action:write", "shift:read"],
            "ad_groups": ["OLNG-ELOG-TRAIN1"],
            "area_scope": ["Train 1"],
        },
    )
    await client.post(
        "/api/v1/pending-actions",
        headers={"Authorization": OPERATOR},
        json={"issue": "Train 1 issue", "area": "Train 1"},
    )
    await client.post(
        "/api/v1/pending-actions",
        headers={"Authorization": OPERATOR},
        json={"issue": "Train 2 issue", "area": "Train 2"},
    )
    shift_id = await _current_shift_id(client)

    scoped_resp = await client.get(
        f"/api/v1/shifts/{shift_id}/actions", headers={"Authorization": SCOPED}
    )
    assert [a["area"] for a in scoped_resp.json()["data"]["actions"]] == ["Train 1"]

    full_resp = await client.get(
        f"/api/v1/shifts/{shift_id}/actions", headers={"Authorization": OPERATOR}
    )
    assert len(full_resp.json()["data"]["actions"]) == 2
