"""In-memory notification repository — the default local/test backend."""

from src.application.notifications.repository import NotificationRepository
from src.domain.notifications.entities import Notification


class InMemoryNotificationRepository(NotificationRepository):
    """Process-local store. Not for production — replaced by the MS SQL adapter."""

    def __init__(self) -> None:
        self._items: list[Notification] = []

    async def add(self, notification: Notification) -> Notification:
        self._items.append(notification)
        return notification

    async def list_for_recipient(self, recipient: str) -> list[Notification]:
        # (created_at, id) — a secondary tie-break so two rows added in the same
        # instant (e.g. alert_owner's in-app + email pair) sort deterministically,
        # matching SqlNotificationRepository's ORDER BY.
        return sorted(
            (n for n in self._items if n.recipient == recipient),
            key=lambda n: (n.created_at, n.id),
            reverse=True,
        )

    async def exists_for_entity(self, related_entity_type: str, related_entity_id: str) -> bool:
        return any(
            n.related_entity_type == related_entity_type
            and n.related_entity_id == related_entity_id
            for n in self._items
        )
