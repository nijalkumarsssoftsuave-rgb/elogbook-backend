"""Dev-token request/response schemas (stub-mode only — see api/v1/dev_auth.py)."""

from pydantic import BaseModel, Field


class DevTokenRequest(BaseModel):
    """Identity to mint a stand-in token for."""

    username: str = Field(min_length=1)
    groups: list[str] = Field(min_length=1, description="AD group names, e.g. OLNG-ELOG-OPERATORS")
    display_name: str | None = None


class DevTokenResponse(BaseModel):
    """Shaped like a real OAuth token response — same field names AD FS will return."""

    access_token: str
    token_type: str = "Bearer"  # noqa: S105 — OAuth token-type literal, not a secret
    expires_in: int
