"""Unit tests for RBAC resolution — pure application logic, no I/O.

Previously only exercised incidentally through auth/admin integration tests; this
isolates the union/wildcard/area-scope rules directly, including edge cases (mixed
area scopes, a role with no permissions) that weren't pinned down anywhere.
"""

from src.application.auth.resolve_permissions import (
    area_scope_for_roles,
    has_permission,
    permissions_for_roles,
)
from src.domain.users_roles.entities import Role


def _role(name="r", permissions=None, area_scope=None) -> Role:
    return Role.create_custom(name, permissions or [], ad_groups=["G"], area_scope=area_scope)


def _base_role(name, permissions, area_scope=None) -> Role:
    return Role(
        id=f"base-{name}",
        name=name,
        is_custom=False,
        permissions=permissions,
        ad_groups=[f"OLNG-ELOG-{name.upper()}S"],
        area_scope=area_scope,
    )


def test_permissions_for_roles_unions_and_sorts():
    roles = [_role(permissions=["action:read"]), _role(permissions=["action:write", "action:read"])]
    assert permissions_for_roles(roles) == ["action:read", "action:write"]


def test_permissions_for_roles_empty_list_is_empty():
    assert permissions_for_roles([]) == []


def test_has_permission_exact_match():
    assert has_permission(["action:read"], "action:read") is True
    assert has_permission(["action:read"], "action:write") is False


def test_has_permission_wildcard_grants_everything():
    assert has_permission(["*"], "anything:at_all") is True


def test_area_scope_for_roles_unions_multiple_scopes():
    roles = [_role(area_scope=["Train 1"]), _role(area_scope=["Train 2"])]
    assert area_scope_for_roles(roles) == ["Train 1", "Train 2"]


def test_area_scope_for_roles_full_plant_role_overrides_any_scoped_role():
    roles = [_role(area_scope=["Train 1"]), _role(area_scope=None)]
    assert area_scope_for_roles(roles) is None


def test_area_scope_for_roles_all_full_plant_is_none():
    roles = [_role(area_scope=None), _role(area_scope=None)]
    assert area_scope_for_roles(roles) is None


def test_area_scope_for_roles_empty_list_is_none():
    assert area_scope_for_roles([]) is None


# ---------------------------------------------------------------------------
# ES-364: custom roles are resolved identically to base roles
# ---------------------------------------------------------------------------


def test_base_and_custom_role_permissions_are_unioned():
    base = _base_role("operator", ["shift:read", "action:read"])
    custom = _role("analyst", permissions=["analytics:read"])
    assert permissions_for_roles([base, custom]) == ["action:read", "analytics:read", "shift:read"]


def test_is_custom_flag_has_no_effect_on_permission_resolution():
    custom = _role("r", permissions=["action:read"])
    base = _base_role("r", ["action:read"])
    assert permissions_for_roles([custom]) == permissions_for_roles([base])


def test_administrator_wildcard_from_base_role_grants_everything():
    admin_base = _base_role("administrator", ["*"])
    assert has_permission(permissions_for_roles([admin_base]), "any:permission") is True


def test_base_full_plant_role_overrides_custom_area_scope():
    scoped_custom = _role("restricted", area_scope=["Train 1"])
    full_plant_base = _base_role("operator", ["shift:read"], area_scope=None)
    assert area_scope_for_roles([scoped_custom, full_plant_base]) is None


def test_two_scoped_roles_base_and_custom_area_scopes_are_unioned():
    scoped_base = _base_role("area_base", ["shift:read"], area_scope=["Zone-A"])
    scoped_custom = _role("area_custom", area_scope=["Zone-B"])
    assert area_scope_for_roles([scoped_base, scoped_custom]) == ["Zone-A", "Zone-B"]
