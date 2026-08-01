"""Resolve a user's roles to the permissions they grant.

Roles (and the permissions they carry) are real data now — see
``application/users_roles/repository.py`` — not a hardcoded table. The administrator
base role's wildcard (``"*"``) is seed data on that role, not a special case here.
"""

from src.api.errors.exceptions import ForbiddenError
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


def resolve_query_scope(
    area_scope: list[str] | None, requested_area: str | None = None
) -> list[str] | None:
    """The areas this request is restricted to. ``None`` = unrestricted (full plant).

    ES-305: with no ``requested_area``, a full-plant caller gets ``None`` back and a
    scoped caller gets their own scope back — the baseline "what do I see by default".
    ES-306: an explicit ``requested_area`` narrows further — a full-plant caller may
    narrow to any area; a scoped caller may narrow within their own scope. Raises
    ``ForbiddenError`` (403) if ``requested_area`` falls outside the caller's scope —
    an out-of-scope request is refused, not silently ignored or silently widened.
    """
    scope = AreaScope.of(area_scope)
    if requested_area is None:
        return scope.as_list()
    narrowed = scope.narrowed_to(requested_area)
    if narrowed is None:
        raise ForbiddenError(f"Your role's data scope does not include area '{requested_area}'.")
    return narrowed.as_list()


def sole_area(scope: list[str] | None) -> str | None:
    """The one area a resolved scope pins to; ``None`` when plant-wide or spanning several.

    ES-307: a custom role restricted to exactly one area should see that area's OWN
    shift configuration by default, not the plant-wide one — this is what selects it.
    Used whether the caller narrowed via an explicit ``?area=`` or a single-area role's
    own scope resolved to one area implicitly. A role spanning multiple areas (or full
    plant) has no single area to prefer, so the plant-wide configuration applies.

    ``scope`` is expected to already be the fully-resolved, cross-role union (see
    ``Principal.area_scope``, built by ``area_scope_for_roles`` at token-validation
    time) — this function never itself disambiguates between a user's several roles; a
    user with two single-area roles for different areas correctly lands here with a
    two-element ``scope`` and gets the plant-wide fallback, same as one role with a
    two-element ``area_scope``.
    """
    return scope[0] if scope is not None and len(scope) == 1 else None
