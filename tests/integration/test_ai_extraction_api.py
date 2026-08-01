"""Integration tests for AI action-extraction and its confirm flow (ES-341)."""

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


async def test_generic_capture_ignores_source_and_is_always_manual(client):
    """ES-343 — the generic endpoint can't be used to sneak in an unconfirmed 'ai' source."""
    resp = await client.post(
        "/api/v1/pending-actions",
        headers={"Authorization": OPERATOR},
        json={"issue": "Check alarm", "source": "ai"},  # source is not a field anymore
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["source"] == "manual"


async def test_supervisor_confirms_extracted_candidate_via_confirm_inclusion(client):
    extracted = await client.post(
        "/api/v1/pending-actions/extract-candidates",
        headers={"Authorization": OPERATOR},
        json={"text": "Inspect PSV on V-101.", "area": "Train 1"},
    )
    candidate = extracted.json()["data"][0]

    confirmed = await client.post(
        "/api/v1/pending-actions/confirm-inclusion",
        headers={"Authorization": SUPERVISOR},
        json={
            "issue": candidate["issue"],
            "priority": candidate["priority"],
            "area": candidate["area"],
            "equipment": candidate["equipment"],
        },
    )
    assert confirmed.status_code == 200
    body = confirmed.json()["data"]
    assert body["source"] == "ai"
    assert body["status"] == "Open"
    assert body["area"] == "Train 1"


async def test_operator_cannot_confirm_inclusion(client):
    """Only a Supervisor+ (action:confirm) may record an inclusion decision."""
    resp = await client.post(
        "/api/v1/pending-actions/confirm-inclusion",
        headers={"Authorization": OPERATOR},
        json={"issue": "Inspect PSV on V-101"},
    )
    assert resp.status_code == 403
