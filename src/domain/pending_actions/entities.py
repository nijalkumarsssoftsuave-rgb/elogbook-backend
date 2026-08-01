"""Pending-action domain entity — pure business data and rules, no framework or I/O.

A follow-up action captured manually or extracted by the AI, tracked through its
lifecycle (see ``state_machine``). Fields follow BRD FR-PA-03.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum


class PendingActionStatus(StrEnum):
    """The lifecycle states (BRD pending-action lifecycle)."""

    OPEN = "Open"
    IN_PROGRESS = "In Progress"
    ON_HOLD = "On Hold"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"
    VERIFIED = "Verified"


class Priority(StrEnum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class Source(StrEnum):
    MANUAL = "manual"  # tagged by a user
    AI_EXTRACTED = "ai"  # suggested by ai-service, confirmed by a supervisor


@dataclass
class PendingAction:
    """A single pending action aggregate."""

    id: str
    issue: str
    priority: Priority
    status: PendingActionStatus
    source: Source
    area: str | None = None
    equipment: str | None = None
    owner: str | None = None
    due_date: date | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @staticmethod
    def create(
        issue: str,
        priority: Priority,
        source: Source,
        area: str | None = None,
        equipment: str | None = None,
        owner: str | None = None,
        due_date: date | None = None,
    ) -> "PendingAction":
        """Capture a new action. New actions always start in ``OPEN``."""
        return PendingAction(
            id=uuid.uuid4().hex,
            issue=issue,
            priority=priority,
            status=PendingActionStatus.OPEN,
            source=source,
            area=area,
            equipment=equipment,
            owner=owner,
            due_date=due_date,
        )

    def touch(self) -> None:
        """Stamp the update time."""
        self.updated_at = datetime.now(UTC)

    def is_overdue(self, today: date | None = None) -> bool:
        """True when past due and not in a terminal state."""
        if self.due_date is None:
            return False
        today = today or datetime.now(UTC).date()
        terminal = {
            PendingActionStatus.COMPLETED,
            PendingActionStatus.CANCELLED,
            PendingActionStatus.VERIFIED,
        }
        return self.due_date < today and self.status not in terminal
