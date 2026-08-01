"""API response-contract tests.

Engineering Code Standards, discipline 3: assert that both successful and failed
responses match the agreed envelope, so the contract cannot silently drift.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from tests.helpers import bearer

OPERATOR = bearer("jane.operator", ["OLNG-ELOG-OPERATORS"])


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health_success_envelope(client):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["status"] == "ok"
    assert "meta" in body and "timestamp" in body["meta"]
    assert "X-Correlation-ID" in resp.headers


async def test_me_returns_roles_and_permissions(client):
    resp = await client.get("/api/v1/me", headers={"Authorization": OPERATOR})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["roles"] == ["operator"]
    assert "assistant:query" in data["permissions"]


async def test_missing_token_is_unauthorized_envelope(client):
    resp = await client.get("/api/v1/me")
    assert resp.status_code == 401
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "unauthorized"


async def test_permission_enforced_on_shift_endpoint(client):
    # super_user lacks shift:read -> forbidden, still in the standard error shape
    su = bearer("sam.super", ["OLNG-ELOG-SUPERUSERS"])
    resp = await client.get("/api/v1/shifts/current", headers={"Authorization": su})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


async def test_current_shift_for_operator(client):
    resp = await client.get("/api/v1/shifts/current", headers={"Authorization": OPERATOR})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["label"] in {"Day", "Night"}
    assert data["overlap_minutes"] == 15
