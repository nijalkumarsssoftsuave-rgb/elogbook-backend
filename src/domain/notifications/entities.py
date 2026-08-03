"""Notification domain entity — pure business data, no framework or I/O."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class NotificationChannel(StrEnum):
    """How a notification was delivered."""

    IN_APP = "in_app"
    EMAIL = "email"


@dataclass
class Notification:
    """One alert delivered to a user through one channel.

    ES-355 ("no separate escalation tier"): a flat, single notification per
    (recipient, channel) when triggered — not a multi-stage reminder sequence that
    steps up to a supervisor after some delay.
    """

    id: str
    recipient: str  # username
    channel: NotificationChannel
    subject: str
    message: str
    related_entity_type: str | None = None
    related_entity_id: str | None = None
    read: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @staticmethod
    def create(
        recipient: str,
        channel: NotificationChannel,
        subject: str,
        message: str,
        related_entity_type: str | None = None,
        related_entity_id: str | None = None,
    ) -> "Notification":
        return Notification(
            id=uuid.uuid4().hex,
            recipient=recipient,
            channel=channel,
            subject=subject,
            message=message,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
        )
