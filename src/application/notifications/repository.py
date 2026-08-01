"""Notification repository port.

Defined in the application layer, implemented in infrastructure and injected — the
clean-architecture dependency rule, same pattern as ``pending_actions/repository.py``.
"""

from abc import ABC, abstractmethod

from src.domain.notifications.entities import Notification


class NotificationRepository(ABC):
    """Persistence contract for notifications."""

    @abstractmethod
    async def add(self, notification: Notification) -> Notification: ...

    @abstractmethod
    async def list_for_recipient(self, recipient: str) -> list[Notification]:
        """Every notification for one recipient, most recent first."""
        ...

    @abstractmethod
    async def exists_for_entity(self, related_entity_type: str, related_entity_id: str) -> bool:
        """True if any notification already references this entity.

        Backs ``alert_owner()``'s idempotency check (ES-355 code review) — without
        this, a sweep re-run (hourly cron, while an action stays overdue) would
        re-alert the same owner every single tick.
        """
        ...
