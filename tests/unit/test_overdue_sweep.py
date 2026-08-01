"""Unit tests for the overdue-sweep use case (ES-353)."""

from datetime import UTC, datetime, timedelta

from src.application.pending_actions.create_action import capture_action
from src.application.pending_actions.overdue_sweep import find_overdue_actions
from src.application.pending_actions.transition_action import transition_action
from src.domain.pending_actions.entities import PendingActionStatus, Priority, Source
from src.infrastructure.persistence.in_memory_pending_actions import (
    InMemoryPendingActionRepository,
)

# UTC, matching is_overdue()'s own datetime.now(UTC).date() — a naive local
# date.today() would disagree near midnight in any positive-UTC-offset timezone.
_TODAY = datetime.now(UTC).date()
YESTERDAY = _TODAY - timedelta(days=1)
TOMORROW = _TODAY + timedelta(days=1)


async def test_finds_only_actions_past_their_due_date():
    repo = InMemoryPendingActionRepository()
    overdue = await capture_action(repo, "Overdue one", Priority.HIGH, Source.MANUAL)
    overdue.due_date = YESTERDAY
    await repo.update(overdue)

    not_yet_due = await capture_action(repo, "Not due yet", Priority.LOW, Source.MANUAL)
    not_yet_due.due_date = TOMORROW
    await repo.update(not_yet_due)

    no_due_date = await capture_action(repo, "No due date", Priority.LOW, Source.MANUAL)
    assert no_due_date.due_date is None

    result = await find_overdue_actions(repo)
    assert [a.issue for a in result] == ["Overdue one"]


async def test_completed_actions_are_never_overdue_even_past_due_date():
    repo = InMemoryPendingActionRepository()
    action = await capture_action(repo, "Finished late", Priority.LOW, Source.MANUAL)
    action.due_date = YESTERDAY
    await repo.update(action)
    await transition_action(repo, action.id, PendingActionStatus.IN_PROGRESS)
    await transition_action(repo, action.id, PendingActionStatus.COMPLETED)

    result = await find_overdue_actions(repo)
    assert result == []


async def test_no_overdue_actions_returns_empty_list():
    repo = InMemoryPendingActionRepository()
    await capture_action(repo, "Fine for now", Priority.LOW, Source.MANUAL)

    assert await find_overdue_actions(repo) == []
