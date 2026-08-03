"""Integration tests for AI action-extraction and its confirm flow (ES-341)."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.deps import _pending_action_repo
from src.core.config import get_settings
from src.main import app
from tests.helpers import bearer

OPERATOR = bearer("jane.operator", ["OLNG-ELOG-OPERATORS"])


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


async def test_extract_candidates_returns_suggestions_without_persisting(client):
    resp = await client.post(
        "/api/v1/pending-actions/extract-candidates",
        headers={"Authorization": OPERATOR},
        json={"text": "Inspect PSV on V-101. Replace worn gasket.", "area": "Train 1"},
    )
    assert resp.status_code == 200
    candidates = resp.json()["data"]
    assert [c["issue"] for c in candidates] == ["Inspect PSV on V-101", "Replace worn gasket"]
    assert all(c["area"] == "Train 1" for c in candidates)

    # nothing was persisted — extraction is a read, not a mutation
    listed = await client.get("/api/v1/pending-actions", headers={"Authorization": OPERATOR})
    assert listed.json()["data"] == []


async def test_blank_text_is_rejected(client):
    resp = await client.post(
        "/api/v1/pending-actions/extract-candidates",
        headers={"Authorization": OPERATOR},
        json={"text": "   "},
    )
    assert resp.status_code == 422


async def test_confirming_a_candidate_reuses_the_existing_capture_endpoint(client):
    extracted = await client.post(
        "/api/v1/pending-actions/extract-candidates",
        headers={"Authorization": OPERATOR},
        json={"text": "Inspect PSV on V-101."},
    )
    candidate = extracted.json()["data"][0]

    confirmed = await client.post(
        "/api/v1/pending-actions",
        headers={"Authorization": OPERATOR},
        json={
            "issue": candidate["issue"],
            "priority": candidate["priority"],
            "source": "ai",
            "area": candidate["area"],
            "equipment": candidate["equipment"],
        },
    )
    assert confirmed.status_code == 200
    body = confirmed.json()["data"]
    assert body["source"] == "ai"
    assert body["status"] == "Open"
