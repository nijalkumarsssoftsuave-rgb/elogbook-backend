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
