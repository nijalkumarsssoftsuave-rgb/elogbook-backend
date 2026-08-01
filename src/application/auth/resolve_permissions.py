"""Resolve a user's roles to the permissions they grant.

Roles (and the permissions they carry) are real data now — see
``application/users_roles/repository.py`` — not a hardcoded table. The administrator
base role's wildcard (``"*"``) is seed data on that role, not a special case here.
"""

from src.domain.users_roles.entities import Role
from src.domain.users_roles.permissions import AreaScope


def permissions_for_roles(roles: list[Role]) -> list[str]:
    """Union of the permissions granted by the given roles."""
    perms: set[str] = set()
    for role in roles:
        perms.update(role.permissions)
    return sorted(perms)


def has_permission(granted: list[str], required: str) -> bool:
    """True if ``required`` is satisfied by the granted permissions."""
    return "*" in granted or required in granted


def area_scope_for_roles(roles: list[Role]) -> list[str] | None:
    """Union of areas the given roles are restricted to; ``None`` if any grants full plant."""
    if any(r.area_scope is None for r in roles):
        return None
    scope: set[str] = set()
    for role in roles:
        scope.update(role.area_scope or [])
    return sorted(scope) if scope else None


def resolve_query_scope(area_scope: list[str] | None) -> list[str] | None:
    """The areas this request is restricted to. ``None`` = unrestricted (full plant).

    ES-305: full-plant callers (the default for every base operational role) get
    ``None`` back — no restriction. A role with an area scope gets that scope back
    unchanged. Narrowing to one specific area via an explicit request (``?area=``) is
    ES-306; this is the baseline "what do I see by default" resolution.
    """
    return AreaScope.of(area_scope).as_list()
