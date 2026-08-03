"""Unit tests for the real ai-service HTTP adapter (ES-341), against a mock transport.

No real network call and no new test dependency: ``httpx.MockTransport`` intercepts the
request in-process, so this exercises the adapter's request/response handling exactly as
it would run against a real ai-service, without needing one reachable.
"""

import httpx
import pytest

from src.api.errors.exceptions import ExternalServiceError
from src.application.ai_extraction.extractor import ExtractionRequest
from src.domain.pending_actions.entities import Priority
from src.infrastructure.ai_client.client import HttpActionExtractor


def _mock_client(monkeypatch, handler) -> None:
    """Route every ``httpx.AsyncClient(...)`` the adapter creates through ``handler``."""
    real_async_client = httpx.AsyncClient

    def fake_client(**kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_async_client(**kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)


async def test_parses_candidates_from_a_well_formed_response(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/extract"
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"issue": "Inspect PSV", "priority": "High", "confidence": 0.92},
                    {"issue": "Replace gasket", "area": "Train 1"},
                ]
            },
        )

    _mock_client(monkeypatch, handler)
    extractor = HttpActionExtractor("http://ai-service.local")
    result = await extractor.extract_candidates(ExtractionRequest(text="entry text"))

    assert [c.issue for c in result] == ["Inspect PSV", "Replace gasket"]
    assert result[0].confidence == 0.92
    assert result[1].area == "Train 1"


async def test_http_error_raises_external_service_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    _mock_client(monkeypatch, handler)
    extractor = HttpActionExtractor("http://ai-service.local")
    with pytest.raises(ExternalServiceError):
        await extractor.extract_candidates(ExtractionRequest(text="entry text"))


async def test_malformed_response_shape_raises_external_service_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    _mock_client(monkeypatch, handler)
    extractor = HttpActionExtractor("http://ai-service.local")
    with pytest.raises(ExternalServiceError):
        await extractor.extract_candidates(ExtractionRequest(text="entry text"))


async def test_priority_casing_from_ai_service_is_normalized(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"candidates": [{"issue": "Inspect PSV", "priority": "high"}]}
        )

    _mock_client(monkeypatch, handler)
    extractor = HttpActionExtractor("http://ai-service.local")
    result = await extractor.extract_candidates(ExtractionRequest(text="entry text"))

    assert result[0].priority == Priority.HIGH


async def test_missing_area_and_equipment_fall_back_to_request_context(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"candidates": [{"issue": "Inspect PSV"}]})

    _mock_client(monkeypatch, handler)
    extractor = HttpActionExtractor("http://ai-service.local")
    result = await extractor.extract_candidates(
        ExtractionRequest(text="entry text", area="Train 1", equipment="V-101")
    )

    assert result[0].area == "Train 1"
    assert result[0].equipment == "V-101"


async def test_one_malformed_candidate_is_skipped_not_the_whole_batch(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"issue": "Inspect PSV", "priority": "High"},
                    {"issue": "Replace gasket", "priority": "urgent"},  # not a real Priority
                ]
            },
        )

    _mock_client(monkeypatch, handler)
    extractor = HttpActionExtractor("http://ai-service.local")
    result = await extractor.extract_candidates(ExtractionRequest(text="entry text"))

    assert [c.issue for c in result] == ["Inspect PSV"]
