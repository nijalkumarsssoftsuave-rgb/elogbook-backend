"""Unit tests for the structured JSON log formatter.

Regression coverage for a bug found reviewing ES-353: the formatter used to embed
%(message)s directly inside a hand-built '"message":"..."' literal with no escaping —
a message containing a quote, backslash, or newline corrupted the line into invalid
JSON. Free-text content (e.g. a pending action's issue, logged by the overdue sweep)
makes this a real, reachable case, not a theoretical one.
"""

import json
import logging

from src.core.logging import _JsonFormatter


def _format(message: str) -> str:
    record = logging.LogRecord(
        name="test.logger",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )
    record.correlation_id = "test-cid"
    return _JsonFormatter().format(record)


def test_message_with_double_quotes_produces_valid_json():
    line = _format('Valve reads 12" low')
    parsed = json.loads(line)
    assert parsed["message"] == 'Valve reads 12" low'


def test_message_with_backslash_and_newline_produces_valid_json():
    line = _format("Path C:\\logs\\a.txt\nsecond line")
    parsed = json.loads(line)
    assert parsed["message"] == "Path C:\\logs\\a.txt\nsecond line"


def test_all_expected_fields_present():
    line = _format("plain message")
    parsed = json.loads(line)
    assert parsed["level"] == "WARNING"
    assert parsed["logger"] == "test.logger"
    assert parsed["correlation_id"] == "test-cid"
    assert parsed["message"] == "plain message"
    assert "ts" in parsed
