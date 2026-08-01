"""Proves no outbound work-order/CMMS call is made (ES-357, companion to ES-356).

Intercepts the real network transport (``httpx.AsyncHTTPTransport``) — not the test
client's own transport, which is ``ASGITransport`` (an in-process call into the app,
never touching a real socket) and is a completely separate class, unaffected by this
patch. Any code path that tried to make a genuine outbound HTTP call during a pending-
action operation would hit this and fail the test loudly, by name and URL.

Deliberately excludes ``POST /pending-actions/extract-candidates``: that endpoint's
whole job is to call ai-service (ES-341), a different, intentional integration — not a
work-order/CMMS push. Everything that actually mutates a pending action (capture,
confirm-inclusion, transition) is covered here instead.
"""

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from src.api.deps import _pending_action_repo
from src.core.config import get_settings
from src.main import app
from tests.helpers import bearer

OPERATOR = bearer("jane.operator", ["OLNG-ELOG-OPERATORS"])
SUPERVISOR = bearer("sam.super", ["OLNG-ELOG-SUPERVISORS"])


@pytest.fixture(autouse=True)
def _reset_state():
    _pending_action_repo._items.clear()
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def block_real_outbound_calls(monkeypatch):
    """Any genuine network call fails the test immediately, by name and URL."""

    async def _blocked(self, request, **kwargs):
        raise AssertionError(f"Unexpected outbound network call: {request.method} {request.url}")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", _blocked)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_the_guard_itself_actually_blocks_a_real_call():
    """Proves the guard is real, not a no-op.

    If it ever stopped blocking, every other test in this file would start passing
    for the wrong reason (nothing was actually being intercepted).
    """
    with pytest.raises(AssertionError, match="Unexpected outbound network call"):
        async with httpx.AsyncClient() as real_client:
            await real_client.get("http://example.invalid/should-never-be-called")


async def test_capture_makes_no_outbound_call(client):
    resp = await client.post(
        "/api/v1/pending-actions",
        headers={"Authorization": OPERATOR},
        json={"issue": "Inspect PSV on V-101"},
    )
    assert resp.status_code == 200


async def test_confirm_inclusion_makes_no_outbound_call(client):
    resp = await client.post(
        "/api/v1/pending-actions/confirm-inclusion",
        headers={"Authorization": SUPERVISOR},
        json={"issue": "AI-suggested action"},
    )
    assert resp.status_code == 200


async def test_full_lifecycle_makes_no_outbound_call(client, monkeypatch):
    monkeypatch.setenv("ELOG_ACTION_WORKFLOW_ENABLED", "true")
    get_settings.cache_clear()

    created = await client.post(
        "/api/v1/pending-actions",
        headers={"Authorization": SUPERVISOR},
        json={"issue": "Calibrate transmitter"},
    )
    action_id = created.json()["data"]["id"]

    for target in ["In Progress", "Completed", "Verified"]:
        resp = await client.patch(
            f"/api/v1/pending-actions/{action_id}/transition",
            headers={"Authorization": SUPERVISOR},
            json={"target": target},
        )
        assert resp.status_code == 200

    listed = await client.get("/api/v1/pending-actions", headers={"Authorization": SUPERVISOR})
    assert listed.status_code == 200
    fetched = await client.get(
        f"/api/v1/pending-actions/{action_id}", headers={"Authorization": SUPERVISOR}
    )
    assert fetched.status_code == 200
