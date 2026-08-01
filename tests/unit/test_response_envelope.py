"""Unit tests for the unified response envelope (Engineering Code Standards, discipline 6).

Previously only asserted indirectly through HTTP responses in the contract tests; this
exercises ``ok()``/``fail()`` directly.
"""

from src.core.response import fail, ok


def test_ok_wraps_data_and_defaults_error_to_absent():
    body = ok({"x": 1}, correlation_id="cid-1")
    assert body["success"] is True
    assert body["data"] == {"x": 1}
    assert "error" not in body  # exclude_none drops it
    assert body["meta"]["correlation_id"] == "cid-1"
    assert "timestamp" in body["meta"]


def test_ok_with_no_data_omits_data_key():
    body = ok()
    assert body["success"] is True
    assert "data" not in body


def test_fail_wraps_error_and_omits_data():
    body = fail("not_found", "missing", details={"id": "abc"}, correlation_id="cid-2")
    assert body["success"] is False
    assert "data" not in body
    assert body["error"] == {"code": "not_found", "message": "missing", "details": {"id": "abc"}}
    assert body["meta"]["correlation_id"] == "cid-2"


def test_fail_without_details_omits_details_key():
    body = fail("conflict", "already exists")
    assert body["error"] == {"code": "conflict", "message": "already exists"}


def test_meta_correlation_id_defaults_to_none_key_omitted():
    body = ok({"x": 1})
    assert "correlation_id" not in body["meta"]
