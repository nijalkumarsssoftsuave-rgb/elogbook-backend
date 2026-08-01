"""Domain and application exceptions.

Each maps to a specific HTTP status via the handlers in ``handlers.py`` — Engineering
Code Standards, discipline 6: every error class maps to the correct status code and a
consistent, handled response.
"""


class AppError(Exception):
    """Base application error. Carries a stable machine-readable code."""

    status_code: int = 500
    code: str = "internal_error"
    message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None, details: object | None = None) -> None:
        super().__init__(message or self.message)
        self.message = message or self.message
        self.details = details


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    message = "The requested resource was not found."


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"
    message = "The request payload failed validation."


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"
    message = "Authentication is required or the token is invalid."


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"
    message = "You do not have permission to perform this action."


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    message = "The request conflicts with the current state."
