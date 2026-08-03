"""Integration tests for the pending-actions API, through the real app + in-memory repo."""

from datetime import date, timedelta

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
    """Isolate tests: clear the in-memory store and reset the workflow toggle."""
    _pending_action_repo._items.clear()
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_capture_and_list(client):
    create = await client.post(
        "/api/v1/pending-actions",
        headers={"Authorization": OPERATOR},
        json={"issue": "Inspect PSV on V-101", "priority": "High"},
    )
    assert create.status_code == 200
    body = create.json()["data"]
    assert body["status"] == "Open"
    assert body["source"] == "manual"

    listed = await client.get("/api/v1/pending-actions", headers={"Authorization": OPERATOR})
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 1


async def test_list_filters_by_source(client):
    await client.post(
        "/api/v1/pending-actions",
        headers={"Authorization": OPERATOR},
        json={"issue": "Manual entry"},
    )
    await client.post(
        "/api/v1/pending-actions/extract-candidates",
        headers={"Authorization": OPERATOR},
        json={"text": "AI entry."},
    )
    await client.post(
        "/api/v1/pending-actions/confirm-inclusion",
        headers={"Authorization": SUPERVISOR},
        json={"issue": "AI entry"},
    )

    manual_only = await client.get(
        "/api/v1/pending-actions", params={"source": "manual"}, headers={"Authorization": OPERATOR}
    )
    ai_only = await client.get(
        "/api/v1/pending-actions", params={"source": "ai"}, headers={"Authorization": OPERATOR}
    )
    assert [a["issue"] for a in manual_only.json()["data"]] == ["Manual entry"]
    assert [a["issue"] for a in ai_only.json()["data"]] == ["AI entry"]


async def test_list_filters_by_created_date_range(client):
    created = await client.post(
        "/api/v1/pending-actions",
        headers={"Authorization": OPERATOR},
        json={"issue": "Check alarm"},
    )
    action_id = created.json()["data"]["id"]
    created_at = created.json()["data"]["created_at"]

    inside = await client.get(
        "/api/v1/pending-actions",
        params={"created_from": "2020-01-01T00:00:00Z", "created_to": "2099-01-01T00:00:00Z"},
        headers={"Authorization": OPERATOR},
    )
    outside = await client.get(
        "/api/v1/pending-actions",
        params={"created_from": "2099-01-01T00:00:00Z"},
        headers={"Authorization": OPERATOR},
    )
    assert action_id in [a["id"] for a in inside.json()["data"]]
    assert action_id not in [a["id"] for a in outside.json()["data"]]
    assert created_at is not None  # sanity: capture actually stamped a real timestamp


async def test_timezone_naive_created_from_does_not_crash(client):
    """Regression: a naive ISO datetime (no UTC offset) used to 500 the in-memory backend.

    It raised "can't compare offset-naive and offset-aware datetimes" — ActionFilter now
    normalises a naive value to UTC instead of comparing it raw.
    """
    created = await client.post(
        "/api/v1/pending-actions",
        headers={"Authorization": OPERATOR},
        json={"issue": "Check alarm"},
    )
    action_id = created.json()["data"]["id"]

    resp = await client.get(
        "/api/v1/pending-actions",
        params={"created_from": "2020-01-01T00:00:00"},  # deliberately no "Z"/offset
        headers={"Authorization": OPERATOR},
    )
    assert resp.status_code == 200
    assert action_id in [a["id"] for a in resp.json()["data"]]


async def test_assignment_blocked_when_workflow_disabled(client):
    resp = await client.post(
        "/api/v1/pending-actions",
        headers={"Authorization": SUPERVISOR},
        json={
            "issue": "Replace gasket",
            "owner": "op.ahmed",
            "due_date": (date.today() + timedelta(days=1)).isoformat(),
        },
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


async def test_transition_blocked_when_workflow_disabled(client, monkeypatch):
    created = await client.post(
        "/api/v1/pending-actions",
        headers={"Authorization": SUPERVISOR},
        json={"issue": "Check alarm"},
    )
    action_id = created.json()["data"]["id"]
    resp = await client.patch(
        f"/api/v1/pending-actions/{action_id}/transition",
        headers={"Authorization": SUPERVISOR},
        json={"target": "In Progress"},
    )
    assert resp.status_code == 403


async def test_full_lifecycle_when_workflow_enabled(client, monkeypatch):
    monkeypatch.setenv("ELOG_ACTION_WORKFLOW_ENABLED", "true")
    get_settings.cache_clear()

    created = await client.post(
        "/api/v1/pending-actions",
        headers={"Authorization": SUPERVISOR},
        json={"issue": "Calibrate transmitter"},
    )
    action_id = created.json()["data"]["id"]

    for target, expected in [("In Progress", 200), ("Completed", 200), ("Verified", 200)]:
        r = await client.patch(
            f"/api/v1/pending-actions/{action_id}/transition",
            headers={"Authorization": SUPERVISOR},
            json={"target": target},
        )
        assert r.status_code == expected, target
        if expected == 200:
            assert r.json()["data"]["status"] == target


async def test_illegal_transition_returns_409(client, monkeypatch):
    monkeypatch.setenv("ELOG_ACTION_WORKFLOW_ENABLED", "true")
    get_settings.cache_clear()

    created = await client.post(
        "/api/v1/pending-actions",
        headers={"Authorization": SUPERVISOR},
        json={"issue": "Tighten flange"},
    )
    action_id = created.json()["data"]["id"]
    # Open -> Completed is not allowed
    r = await client.patch(
        f"/api/v1/pending-actions/{action_id}/transition",
        headers={"Authorization": SUPERVISOR},
        json={"target": "Completed"},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"


async def test_operator_cannot_be_missing_permission(client):
    # management role lacks action:write -> creating is forbidden
    mgmt = bearer("mo.super", ["OLNG-ELOG-SUPERINTENDENTS"])
    resp = await client.post(
        "/api/v1/pending-actions",
        headers={"Authorization": mgmt},
        json={"issue": "x"},
    )
    assert resp.status_code == 403
