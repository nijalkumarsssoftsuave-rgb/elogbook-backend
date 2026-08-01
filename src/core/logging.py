"""Structured logging with correlation IDs.

Engineering Code Standards, discipline 8 (observability): logs are structured and
carry a correlation ID so events can be filtered and joined across a request.
"""

import json
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


class _JsonFormatter(logging.Formatter):
    """Builds each line with ``json.dumps``, not hand-built string interpolation.

    The previous format string embedded ``%(message)s`` directly inside a literal
    ``"message":"..."`` with no escaping — a message containing a quote, backslash, or
    newline (e.g. a pending action's free-text ``issue``, logged by the overdue sweep,
    ES-353) corrupted the line into invalid JSON, breaking any log pipeline that parses
    these as JSON.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "correlation_id": getattr(record, "correlation_id", "-"),
            "message": record.getMessage(),
        }
        # logger.exception()/logger.error(exc_info=True) — without this, the traceback
        # is silently dropped (found live: the overdue sweep's per-action failure
        # handler logged "failed to alert owner" with no way to see why).
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging once, at startup."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    handler.addFilter(CorrelationIdFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""
    return logging.getLogger(name)
