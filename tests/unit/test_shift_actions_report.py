"""Unit tests for the shift-actions report use case (ES-344)."""

from datetime import UTC, datetime

from src.application.pending_actions.create_action import capture_action
from src.application.shifts.shift_actions_report import get_actions_for_shift
from src.domain.pending_actions.entities import Priority, Source
from src.domain.shifts.entities import Shift
from src.infrastructure.persistence.in_memory_pending_actions import (
    InMemoryPendingActionRepository,
)


async def test_only_actions_inside_the_shift_window_are_returned():
    repo = InMemoryPendingActionRepository()
    shift = Shift(
        shift_id="20260730-D",
        label="Day",
        starts_at=datetime(2026, 7, 30, 6, 0, tzinfo=UTC),
        ends_at=datetime(2026, 7, 30, 18, 0, tzinfo=UTC),
        overlap_minutes=15,
    )

    inside = await capture_action(
        repo, issue="during shift", priority=Priority.LOW, source=Source.MANUAL
    )
    inside.created_at = datetime(2026, 7, 30, 10, 0, tzinfo=UTC)
    await repo.update(inside)

    before = await capture_action(
        repo, issue="before shift", priority=Priority.LOW, source=Source.MANUAL
    )
    before.created_at = datetime(2026, 7, 30, 5, 0, tzinfo=UTC)
    await repo.update(before)

    after = await capture_action(
        repo, issue="after shift", priority=Priority.LOW, source=Source.MANUAL
    )
    after.created_at = datetime(2026, 7, 30, 18, 0, tzinfo=UTC)  # exactly at boundary -> excluded
    await repo.update(after)

    result = await get_actions_for_shift(repo, shift)
    assert [a.issue for a in result] == ["during shift"]


async def test_includes_both_manual_and_ai_confirmed_sources():
    repo = InMemoryPendingActionRepository()
    shift = Shift(
        shift_id="20260730-D",
        label="Day",
        starts_at=datetime(2026, 7, 30, 6, 0, tzinfo=UTC),
        ends_at=datetime(2026, 7, 30, 18, 0, tzinfo=UTC),
        overlap_minutes=15,
    )
    manual = await capture_action(repo, issue="manual", priority=Priority.LOW, source=Source.MANUAL)
    manual.created_at = datetime(2026, 7, 30, 9, 0, tzinfo=UTC)
    await repo.update(manual)

    ai = await capture_action(
        repo, issue="ai-confirmed", priority=Priority.LOW, source=Source.AI_EXTRACTED
    )
    ai.created_at = datetime(2026, 7, 30, 9, 0, tzinfo=UTC)
    await repo.update(ai)

    result = await get_actions_for_shift(repo, shift)
    assert {a.issue for a in result} == {"manual", "ai-confirmed"}
