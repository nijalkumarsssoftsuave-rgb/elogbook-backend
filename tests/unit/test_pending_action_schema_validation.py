"""Unit tests for pending-action request validation (ES-347).

Tests the schemas directly — faster and more precise than going through the HTTP layer
for pinning down exactly which value is rejected and why.
"""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from src.api.schemas.pending_action import ConfirmInclusionRequest, CreateActionRequest

_TODAY = datetime.now(UTC).date()


def test_blank_issue_is_rejected():
    with pytest.raises(ValidationError):
        CreateActionRequest(issue="   ")


def test_issue_over_max_length_is_rejected():
    with pytest.raises(ValidationError):
        CreateActionRequest(issue="x" * 1001)


def test_invalid_priority_value_is_rejected():
    with pytest.raises(ValidationError):
        CreateActionRequest(issue="Check alarm", priority="Urgent")


@pytest.mark.parametrize("field", ["area", "equipment", "owner"])
def test_blank_optional_field_is_rejected(field):
    with pytest.raises(ValidationError):
        CreateActionRequest(issue="Check alarm", **{field: "   "})


@pytest.mark.parametrize("field", ["area", "equipment", "owner"])
def test_optional_field_over_max_length_is_rejected(field):
    with pytest.raises(ValidationError):
        CreateActionRequest(issue="Check alarm", **{field: "x" * 129})


def test_optional_fields_at_max_length_are_accepted():
    request = CreateActionRequest(issue="Check alarm", area="x" * 128)
    assert len(request.area) == 128


@pytest.mark.parametrize("field", ["area", "equipment", "owner"])
def test_optional_field_strips_incidental_whitespace(field):
    """Stored stripped so exact-match filtering (?owner=John) still finds it."""
    request = CreateActionRequest(issue="Check alarm", **{field: "  John  "})
    assert getattr(request, field) == "John"


def test_issue_strips_incidental_whitespace():
    request = CreateActionRequest(issue="  Check alarm  ")
    assert request.issue == "Check alarm"


def test_due_date_in_the_past_is_rejected():
    with pytest.raises(ValidationError):
        CreateActionRequest(issue="Check alarm", due_date=_TODAY - timedelta(days=1))


def test_due_date_today_or_future_is_accepted():
    request = CreateActionRequest(issue="Check alarm", due_date=_TODAY)
    assert request.due_date == _TODAY


def test_omitted_optional_fields_default_to_none():
    request = CreateActionRequest(issue="Check alarm")
    assert request.area is None
    assert request.equipment is None
    assert request.owner is None
    assert request.due_date is None


def test_confirm_inclusion_request_shares_the_same_field_validation():
    with pytest.raises(ValidationError):
        ConfirmInclusionRequest(issue="Inspect PSV", area="   ")
    with pytest.raises(ValidationError):
        ConfirmInclusionRequest(issue="Inspect PSV", equipment="x" * 129)
