"""Integration tests for the dev token-issuance endpoint (stub auth mode only)."""

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from src.core.config import get_settings
from src.infrastructure.auth.dev_issuer import get_verification_key
from src.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_issue_token_returns_usable_bearer_token(client):
    resp = await client.post(
        "/api/v1/dev/token",
        json={"username": "jane.operator", "groups": ["OLNG-ELOG-OPERATORS"]},
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["token_type"] == "Bearer"  # noqa: S105 — OAuth token-type literal, not a secret
    assert body["expires_in"] > 0

    me = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["data"]["roles"] == ["operator"]


async def test_issue_token_carries_expected_claims(client):
    resp = await client.post(
        "/api/v1/dev/token",
        json={
            "username": "jane.operator",
            "groups": ["OLNG-ELOG-OPERATORS"],
            "display_name": "Jane O",
        },
    )
    token = resp.json()["data"]["access_token"]
    settings = get_settings()
    claims = jwt.decode(
        token,
        get_verification_key(settings),
        algorithms=["RS256"],
        issuer=settings.auth_issuer,
        audience=settings.auth_audience,
    )
    assert claims["preferred_username"] == "jane.operator"
    assert claims["name"] == "Jane O"
    assert claims["groups"] == ["OLNG-ELOG-OPERATORS"]


async def test_unknown_group_is_rejected(client):
    resp = await client.post(
        "/api/v1/dev/token", json={"username": "x", "groups": ["NOT-A-REAL-GROUP"]}
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


async def test_disabled_outside_stub_mode(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "auth_stub_enabled", False)
    resp = await client.post(
        "/api/v1/dev/token", json={"username": "jane.operator", "groups": ["OLNG-ELOG-OPERATORS"]}
    )
    assert resp.status_code == 404
