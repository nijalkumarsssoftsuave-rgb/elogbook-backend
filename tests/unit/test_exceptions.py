"""Unit tests for the AppError hierarchy (Engineering Code Standards, discipline 6):
every error class must map to the correct status code and a stable machine-readable code.

Previously each of these was only ever hit indirectly through a specific HTTP scenario;
this pins the status/code/message contract directly and independently of any endpoint.
"""
import pytest

from src.api.errors.exceptions import (
    AppError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)


@pytest.mark.parametrize(
    "exc_cls,status_code,code",
    [
        (NotFoundError, 404, "not_found"),
        (ValidationError, 422, "validation_error"),
        (UnauthorizedError, 401, "unauthorized"),
        (ForbiddenError, 403, "forbidden"),
        (ConflictError, 409, "conflict"),
    ],
)
def test_status_code_and_code_are_fixed_per_class(exc_cls, status_code, code):
    exc = exc_cls()
    assert exc.status_code == status_code
    assert exc.code == code
    assert isinstance(exc, AppError)


def test_default_message_used_when_none_given():
    exc = NotFoundError()
    assert exc.message == "The requested resource was not found."
    assert str(exc) == exc.message


def test_custom_message_overrides_default():
    exc = NotFoundError("Pending action abc123 was not found.")
    assert exc.message == "Pending action abc123 was not found."
    assert str(exc) == exc.message


def test_details_default_to_none():
    assert NotFoundError().details is None


def test_details_are_carried():
    exc = ValidationError("bad payload", details={"field": "priority"})
    assert exc.details == {"field": "priority"}


def test_base_apperror_defaults_to_internal_error():
    exc = AppError()
    assert exc.status_code == 500
    assert exc.code == "internal_error"
