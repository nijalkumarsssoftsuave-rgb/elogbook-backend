"""Unit tests for the action-extractor DI wiring (ES-341) — singleton caching."""

import src.api.deps as deps
from src.core.config import get_settings
from src.infrastructure.ai_client.client import HttpActionExtractor, StubActionExtractor


def _reset():
    deps._http_action_extractor = None
    get_settings.cache_clear()


async def test_stub_is_returned_when_ai_service_stub_enabled(monkeypatch):
    _reset()
    monkeypatch.setenv("ELOG_AI_SERVICE_STUB_ENABLED", "true")
    get_settings.cache_clear()

    extractor = deps.get_action_extractor()

    assert isinstance(extractor, StubActionExtractor)
    _reset()


async def test_http_extractor_is_cached_as_a_singleton(monkeypatch):
    _reset()
    monkeypatch.setenv("ELOG_AI_SERVICE_STUB_ENABLED", "false")
    get_settings.cache_clear()

    first = deps.get_action_extractor()
    second = deps.get_action_extractor()

    assert isinstance(first, HttpActionExtractor)
    assert first is second  # same pooled httpx client reused, not rebuilt per call
    _reset()
