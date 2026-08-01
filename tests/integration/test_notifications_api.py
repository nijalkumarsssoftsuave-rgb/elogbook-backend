"""Integration tests for the notifications endpoint (ES-355)."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.deps import _notification_repo
from src.core.config import get_settings
from src.domain.notifications.entities import Notification, NotificationChannel
from src.main import app
from tests.helpers import bearer

OPERATOR = bearer("jane.operator", ["OLNG-ELOG-OPERATORS"])
SUPERVISOR = bearer("sam.super", ["OLNG-ELOG-SUPERVISORS"])


@pytest.fixture(autouse=True)
def _reset_state():
    _notification_repo._items.clear()
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_lists_only_the_callers_own_notifications(client):
    await _notification_repo.add(
        Notification.create("jane.operator", NotificationChannel.IN_APP, "Overdue: x", "msg")
    )
    await _notification_repo.add(
        Notification.create("sam.super", NotificationChannel.IN_APP, "Overdue: y", "msg")
    )

    resp = await client.get("/api/v1/notifications", headers={"Authorization": OPERATOR})
    assert resp.status_code == 200
    assert [n["subject"] for n in resp.json()["data"]] == ["Overdue: x"]

    other = await client.get("/api/v1/notifications", headers={"Authorization": SUPERVISOR})
    assert [n["subject"] for n in other.json()["data"]] == ["Overdue: y"]


async def test_empty_list_when_no_notifications(client):
    resp = await client.get("/api/v1/notifications", headers={"Authorization": OPERATOR})
    assert resp.status_code == 200
    assert resp.json()["data"] == []


async def test_response_shape_includes_channel_and_related_entity(client):
    await _notification_repo.add(
        Notification.create(
            "jane.operator",
            NotificationChannel.IN_APP,
            "Overdue: Inspect PSV",
            "It's overdue.",
            related_entity_type="pending_action",
            related_entity_id="abc123",
        )
    )
    resp = await client.get("/api/v1/notifications", headers={"Authorization": OPERATOR})
    entry = resp.json()["data"][0]
    assert entry["channel"] == "in_app"
    assert entry["related_entity_type"] == "pending_action"
    assert entry["related_entity_id"] == "abc123"
    assert entry["read"] is False


async def test_email_only_rows_are_excluded_from_the_list(client):
    """Email is a delivery-audit fact ("this email was sent"), not a user-facing

    alert to read — including it would double-count against any future unread badge.
    """
    await _notification_repo.add(
        Notification.create("jane.operator", NotificationChannel.EMAIL, "Overdue: x", "msg")
    )
    resp = await client.get("/api/v1/notifications", headers={"Authorization": OPERATOR})
    assert resp.json()["data"] == []
