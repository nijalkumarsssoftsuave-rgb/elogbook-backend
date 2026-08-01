"""Unit tests for CorrelationIdMiddleware.

The contract tests already assert a correlation id is *present* on every response; this
isolates the middleware's own behavior — honouring a caller-supplied id vs. generating
one, and always echoing it back on the response header, which was never asserted
in isolation before.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.middleware.correlation import HEADER
from src.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_generates_a_correlation_id_when_none_supplied(client):
    resp = await client.get("/api/v1/health")
    assert HEADER in resp.headers
    assert len(resp.headers[HEADER]) > 0


async def test_honours_a_caller_supplied_correlation_id(client):
    resp = await client.get("/api/v1/health", headers={HEADER: "caller-supplied-id"})
    assert resp.headers[HEADER] == "caller-supplied-id"


async def test_each_request_without_a_header_gets_a_distinct_id(client):
    first = await client.get("/api/v1/health")
    second = await client.get("/api/v1/health")
    assert first.headers[HEADER] != second.headers[HEADER]
