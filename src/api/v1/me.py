"""Identity endpoint — the authenticated user, their roles and resolved permissions."""

from fastapi import APIRouter

from src.api.deps import CurrentUser
from src.api.schemas.user import UserProfile
from src.core.logging import correlation_id_ctx
from src.core.response import ok

router = APIRouter(tags=["identity"])


@router.get("/me")
async def me(user: CurrentUser) -> dict:
    """Return the current user's profile, roles, permissions and data scope.

    Drives the frontend's role-based routing and menu. Works today against the stub
    token issuer; unchanged when AD FS is wired in (A-01). Roles/permissions/area scope
    are resolved from the real ``roles`` table, not hardcoded.
    """
    profile = UserProfile(
        subject=user.subject,
        username=user.username,
        display_name=user.display_name,
        roles=user.roles,
        groups=user.groups,
        permissions=user.permissions,
        area_scope=user.area_scope,
    )
    return ok(profile.model_dump(), correlation_id=correlation_id_ctx.get())
