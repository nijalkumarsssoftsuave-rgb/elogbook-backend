"""OAuth/JWT token validation.

Real signature/issuer/audience/expiry verification, run against a **locally issued dev
token** until the AD FS registration and per-role test accounts are provided
(Outstanding Items Tracker A-01). The claim shape is identical in both modes; only the
key source (local RSA key vs. AD FS's JWKS) and the issuer/audience config differ, so
switching to the real issuer is a config change, not a rewrite of this module.

Once the token's claims are verified, the caller's AD groups are resolved to roles (and
those roles' permissions and area scope) through the **role repository** — real rows in
MS SQL, not a hardcoded table (see ``application/users_roles/repository.py``). A
validly-signed token whose AD groups match no role is **refused**, not admitted with an
empty permission set (BE-US001-5) — there is no local-credential fallback anywhere in
this path; a bearer token verified against the configured issuer is the only way in.

Every sign-in attempt — success or denial — is written to the audit trail
(BE-US001-6) through the injected **audit recorder**, the same hash-chained mechanism
already used for pending-action and role mutations (see
``application/audit/recorder.py``). A denial is recorded for every way a request can
fail to authenticate: no/malformed bearer header, an invalid token (bad signature,
wrong issuer/audience, expired), and a validly-signed token whose groups map to no role.
"""

from dataclasses import dataclass, field

import jwt

from src.api.errors.exceptions import UnauthorizedError
from src.application.audit.recorder import AuditEntry, AuditRecorder, NullAuditRecorder
from src.application.auth.resolve_permissions import area_scope_for_roles, permissions_for_roles
from src.application.users_roles.repository import RoleRepository
from src.core.config import Settings, get_settings
from src.infrastructure.auth.dev_issuer import ALGORITHM, get_verification_key


@dataclass
class Principal:
    """The authenticated user, fully resolved: identity, roles, permissions, data scope."""

    subject: str
    username: str
    display_name: str
    roles: list[str] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    area_scope: list[str] | None = None  # None = full plant


def _verify(token: str, settings: Settings) -> dict:
    """Verify signature, issuer, audience and expiry; return the decoded claims."""
    if settings.auth_stub_enabled:
        key = get_verification_key(settings)
        try:
            return jwt.decode(
                token,
                key,
                algorithms=[ALGORITHM],
                issuer=settings.auth_issuer,
                audience=settings.auth_audience,
            )
        except jwt.InvalidTokenError as exc:
            raise UnauthorizedError(f"Invalid token: {exc}") from exc

    # TODO(A-01): fetch AD FS's JWKS (issuer/.well-known/openid-configuration ->
    # jwks_uri), select the key by the token's `kid`, and decode with the same
    # jwt.decode(...) shape above. Nothing else in this module changes.
    raise UnauthorizedError("Live AD FS validation not yet configured.")


async def _deny(audit: AuditRecorder, actor: str, reason: str, **extra: object) -> None:
    """Record a sign-in denial, then let the caller raise the matching ``UnauthorizedError``."""
    await audit.record(
        AuditEntry(
            actor=actor,
            action="auth.signin.denied",
            entity_type="principal",
            entity_id=actor,
            payload={"reason": reason, **extra},
        )
    )


async def validate_token(
    authorization: str | None,
    role_repo: RoleRepository,
    audit: AuditRecorder | None = None,
) -> Principal:
    """Validate a bearer token, resolve the principal, and audit the sign-in attempt."""
    audit = audit or NullAuditRecorder()

    if not authorization or not authorization.lower().startswith("bearer "):
        await _deny(audit, "unknown", "missing_or_malformed_authorization_header")
        raise UnauthorizedError("Missing or malformed Authorization header.")

    token = authorization.split(" ", 1)[1].strip()

    try:
        claims = _verify(token, get_settings())
    except UnauthorizedError as exc:
        await _deny(audit, "unknown", "invalid_token", detail=str(exc))
        raise

    groups = claims.get("groups", [])
    username = claims.get("preferred_username", claims["sub"])
    roles = await role_repo.get_for_groups(groups)

    if not roles:
        await _deny(audit, username, "no_role_mapped_for_groups", groups=groups)
        raise UnauthorizedError(
            "Access denied: your AD account is not mapped to any platform role. "
            "Contact an administrator to request access."
        )

    principal = Principal(
        subject=claims["sub"],
        username=username,
        display_name=claims.get("name", username),
        groups=groups,
        roles=sorted({r.name for r in roles}),
        permissions=permissions_for_roles(roles),
        area_scope=area_scope_for_roles(roles),
    )

    await audit.record(
        AuditEntry(
            actor=username,
            action="auth.signin.success",
            entity_type="principal",
            entity_id=username,
            payload={"roles": principal.roles, "groups": groups},
        )
    )

    return principal
