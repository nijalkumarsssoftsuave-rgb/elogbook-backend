"""Shared test helpers."""

from src.core.config import get_settings
from src.infrastructure.auth.dev_issuer import mint_token


def bearer(username: str, groups: list[str]) -> str:
    """Mint a dev token for ``username``/``groups`` and return an Authorization value."""
    token, _ = mint_token(get_settings(), username=username, groups=groups)
    return f"Bearer {token}"
