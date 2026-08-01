"""Notification response schema (ES-355)."""

from pydantic import BaseModel

from src.domain.notifications.entities import Notification, NotificationChannel


class NotificationResponse(BaseModel):
    """A single alert, as returned to the recipient who owns it."""

    id: str
    channel: NotificationChannel
    subject: str
    message: str
    related_entity_type: str | None
    related_entity_id: str | None
    read: bool
    created_at: str

    @staticmethod
    def of(n: Notification) -> "NotificationResponse":
        return NotificationResponse(
            id=n.id,
            channel=n.channel,
            subject=n.subject,
            message=n.message,
            related_entity_type=n.related_entity_type,
            related_entity_id=n.related_entity_id,
            read=n.read,
            created_at=n.created_at.isoformat(),
        )
