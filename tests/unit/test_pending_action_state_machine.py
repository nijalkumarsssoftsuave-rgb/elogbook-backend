"""Unit tests for the pending-action lifecycle — pure domain, no I/O."""

import pytest

from src.domain.pending_actions.entities import PendingAction, Priority, Source
from src.domain.pending_actions.entities import PendingActionStatus as S
from src.domain.pending_actions.state_machine import (
    IllegalTransitionError,
    allowed_targets,
    apply_transition,
    can_transition,
)


def _action(status: S = S.OPEN) -> PendingAction:
    a = PendingAction.create("Pump 3 seal leak", Priority.HIGH, Source.MANUAL)
    a.status = status
    return a


def test_new_action_starts_open():
    assert _action().status is S.OPEN


@pytest.mark.parametrize(
    "current,target,ok",
    [
        (S.OPEN, S.IN_PROGRESS, True),
        (S.OPEN, S.ON_HOLD, True),
        (S.OPEN, S.COMPLETED, False),  # cannot skip straight to completed
        (S.IN_PROGRESS, S.COMPLETED, True),
        (S.COMPLETED, S.VERIFIED, True),
        (S.ON_HOLD, S.IN_PROGRESS, True),
    ],
)
def test_forward_transitions(current, target, ok):
    assert can_transition(current, target) is ok


@pytest.mark.parametrize("current", [S.OPEN, S.IN_PROGRESS, S.ON_HOLD, S.COMPLETED])
def test_any_non_terminal_can_cancel(current):
    assert can_transition(current, S.CANCELLED)


@pytest.mark.parametrize("terminal", [S.VERIFIED, S.CANCELLED])
def test_terminal_states_have_no_targets(terminal):
    assert allowed_targets(terminal) == set()


def test_apply_transition_updates_status():
    a = _action(S.IN_PROGRESS)
    apply_transition(a, S.COMPLETED)
    assert a.status is S.COMPLETED


def test_illegal_transition_raises():
    a = _action(S.VERIFIED)
    with pytest.raises(IllegalTransitionError):
        apply_transition(a, S.IN_PROGRESS)


def test_overdue_only_when_past_due_and_not_terminal():
    from datetime import date, timedelta

    a = _action(S.OPEN)
    a.due_date = date.today() - timedelta(days=1)
    assert a.is_overdue() is True
    a.status = S.COMPLETED
    assert a.is_overdue() is False
