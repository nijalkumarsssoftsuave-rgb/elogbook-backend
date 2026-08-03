"""Integration tests for the shared exception handlers.

Regression coverage for a real bug found while building ES-347: a custom Pydantic
validator raising ``ValueError`` embeds the exception object itself in the error dict's
``ctx['error']`` — passing that straight to ``JSONResponse`` (plain ``json.dumps``, no
custom encoder) turned a legitimate 422 into an unrelated 500 "internal_error". Every
future custom validator in this codebase is exposed to the same failure mode, so this is
pinned down at the handler level, not just re-tested per validator.
"""

from httpx import ASGITransport, AsyncClient

from src.main import app
from tests.helpers import bearer

OPERATOR = bearer("jane.operator", ["OLNG-ELOG-OPERATORS"])


async def test_custom_validator_error_returns_422_not_500():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/pending-actions",
            headers={"Authorization": OPERATOR},
            json={"issue": "   "},  # triggers pending_action.py's custom blank-check validator
        )

    assert resp.status_code == 422
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "validation_error"
    # the ctx.error exception object must have been stringified, not dropped or crashed on
    detail = body["error"]["details"][0]
    assert detail["ctx"]["error"] == "must not be blank"
