"""Local dev token issuer — stands in for AD FS until A-01 lands.

Mints RS256 JWTs shaped exactly like the claims AD FS will issue (subject, username,
display name, AD groups, issuer, audience, expiry). ``token_validator`` verifies stub
tokens the same way it will verify real ones — signature, issuer, audience, expiry —
so swapping in the real AD FS issuer later is a config change (issuer/audience/key
source), not a rewrite of the validation logic.

The signing key is a local RSA keypair generated on first use and cached on disk
(``ELOG_AUTH_DEV_KEYS_DIR``, gitignored) so a token minted in one process run can be
verified in another (e.g. minted via the API, used against a separately running server).
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.core.config import Settings

DEV_KEY_ID = "dev-local-1"
ALGORITHM = "RS256"


def _keypair_paths(settings: Settings) -> tuple[Path, Path]:
    key_dir = Path(settings.auth_dev_keys_dir)
    return key_dir / "private.pem", key_dir / "public.pem"


def _ensure_keypair(settings: Settings) -> tuple[bytes, bytes]:
    """Load the local signing keypair, generating it on first use."""
    private_path, public_path = _keypair_paths(settings)
    if private_path.exists() and public_path.exists():
        return private_path.read_bytes(), public_path.read_bytes()

    private_path.parent.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    private_path.write_bytes(private_pem)
    public_path.write_bytes(public_pem)
    return private_pem, public_pem


def get_verification_key(settings: Settings) -> bytes:
    """The public key ``token_validator`` verifies stub tokens against."""
    _, public_pem = _ensure_keypair(settings)
    return public_pem


def mint_token(
    settings: Settings,
    *,
    username: str,
    groups: list[str],
    display_name: str | None = None,
) -> tuple[str, int]:
    """Mint a signed dev token carrying the given identity and AD groups.

    Returns ``(token, expires_in_seconds)``.
    """
    private_pem, _ = _ensure_keypair(settings)
    now = datetime.now(UTC)
    ttl = timedelta(minutes=settings.token_ttl_minutes)
    claims = {
        "sub": f"dev|{username}",
        "preferred_username": username,
        "name": display_name or username.replace(".", " ").title(),
        "groups": groups,
        "iss": settings.auth_issuer,
        "aud": settings.auth_audience,
        "iat": now,
        "exp": now + ttl,
    }
    token = jwt.encode(claims, private_pem, algorithm=ALGORITHM, headers={"kid": DEV_KEY_ID})
    return token, int(ttl.total_seconds())
