"""Dev-only token issuance — stands in for the AD FS login redirect until A-01 lands.

Mints a signed token via the local dev issuer so the rest of the stack (Swagger, the
frontend, tests) can authenticate exactly as it will against real AD FS: a bearer token
in the Authorization header. Disabled whenever ``auth_stub_enabled`` is off (i.e. once
real AD FS is wired in), so this route never exists outside local/dev.
"""

from fastapi import APIRouter

from src.api.deps import Config, RoleRepositoryDep
from src.api.errors.exceptions import NotFoundError, ValidationError
from src.api.schemas.dev_auth import DevTokenRequest, DevTokenResponse
from src.core.logging import correlation_id_ctx
from src.core.response import ok
from src.infrastructure.auth.dev_issuer import mint_token

router = APIRouter(tags=["dev-auth"])


@router.post("/dev/token")
async def issue_dev_token(
    body: DevTokenRequest, config: Config, role_repo: RoleRepositoryDep
) -> dict:
    """Mint a stand-in bearer token carrying the given username and AD groups.

    Paste the returned ``access_token`` into Swagger's Authorize dialog (or an
    ``Authorization: Bearer <token>`` header) exactly as a real AD FS token would be
    used once A-01 lands. Groups are validated against the real ``roles`` table, so an
    Admin-created custom role's AD group(s) are valid here too.
    """
    if not config.auth_stub_enabled:
        raise NotFoundError("Dev token issuance is disabled outside stub auth mode.")

    known_groups = {g for role in await role_repo.list_all() for g in role.ad_groups}
    unknown = [g for g in body.groups if g not in known_groups]
    if unknown:
        raise ValidationError(
            f"Unknown AD group(s): {', '.join(unknown)}. Valid groups: "
            f"{', '.join(sorted(known_groups))}"
        )

    token, expires_in = mint_token(
        config, username=body.username, groups=body.groups, display_name=body.display_name
    )
    payload = DevTokenResponse(access_token=token, expires_in=expires_in)
    return ok(payload.model_dump(), correlation_id=correlation_id_ctx.get())
