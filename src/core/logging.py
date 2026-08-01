"""Structured logging with correlation IDs.

Engineering Code Standards, discipline 8 (observability): logs are structured and
carry a correlation ID so events can be filtered and joined across a request.
"""

import logging
import sys
from contextvars import ContextVar

# request-scoped correlation id, set by the correlation-id middleware
correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="-")


class CorrelationIdFilter(logging.Filter):
    """Inject the current correlation id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_ctx.get()
        return True


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging once, at startup."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            '{"ts":"%(asctime)s","level":"%(levelname)s",'
            '"logger":"%(name)s","correlation_id":"%(correlation_id)s",'
            '"message":"%(message)s"}'
        )
    )
    handler.addFilter(CorrelationIdFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""
    return logging.getLogger(name)
