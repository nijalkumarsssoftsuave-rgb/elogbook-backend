"""Exception handlers that render every error through the unified envelope."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.api.errors.exceptions import AppError
from src.core.logging import correlation_id_ctx, get_logger
from src.core.response import fail
from src.domain.pending_actions.state_machine import IllegalTransitionError

logger = get_logger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    """Attach handlers so no error ever escapes the standard shape."""

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        cid = correlation_id_ctx.get()
        logger.warning(f"{exc.code}: {exc.message}")
        return JSONResponse(
            status_code=exc.status_code,
            content=fail(exc.code, exc.message, exc.details, correlation_id=cid),
        )

    @app.exception_handler(IllegalTransitionError)
    async def _illegal_transition(_: Request, exc: IllegalTransitionError) -> JSONResponse:
        # a domain rule violation maps to 409 Conflict in the standard shape
        cid = correlation_id_ctx.get()
        return JSONResponse(
            status_code=409,
            content=fail("conflict", str(exc), correlation_id=cid),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        cid = correlation_id_ctx.get()
        # Pydantic v2 @field_validator errors store the raw exception in ctx["error"],
        # which is not JSON-serialisable — convert every ctx value to a string.
        errors = [
            {**e, "ctx": {k: str(v) for k, v in e["ctx"].items()}} if "ctx" in e else e
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=fail(
                "validation_error",
                "The request payload failed validation.",
                details=errors,
                correlation_id=cid,
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        cid = correlation_id_ctx.get()
        logger.exception(f"unhandled error: {exc}")
        return JSONResponse(
            status_code=500,
            content=fail("internal_error", "An unexpected error occurred.", correlation_id=cid),
        )
