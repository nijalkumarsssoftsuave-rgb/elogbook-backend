"""Unit tests for ES-362: permission catalogue and schema validation.

Covers:
- Catalogue completeness (all required permissions present, no duplicates)
- VALID_PERMISSIONS set consistency
- Wildcard exclusion
- CreateRoleRequest / UpdateRoleRequest reject unknown permissions
- CreateRoleRequest / UpdateRoleRequest accept all catalogue permissions
"""

import pytest

from src.domain.users_roles.permissions import (
    PERMISSION_CATALOGUE,
    VALID_PERMISSIONS,
    PermissionEntry,
)

# ---------------------------------------------------------------------------
# Catalogue structure
# ---------------------------------------------------------------------------

EXPECTED_PERMISSIONS = {
    "shift:read",
    "summary:read",
    "summary:comment",
    "assistant:query",
    "action:read",
    "action:write",
    "action:confirm",
    "action:assign",
    "report:read",
    "analytics:read",
    "dashboard:configure",
    "widget:assign",
    "metric:control",
    "access:control",
    "user:read",
    "user:manage",
    "role:read",
    "role:manage",
}


def test_catalogue_contains_all_expected_permissions():
    catalogue_perms = {e.permission for e in PERMISSION_CATALOGUE}
    assert EXPECTED_PERMISSIONS == catalogue_perms


def test_catalogue_has_no_duplicates():
    perms = [e.permission for e in PERMISSION_CATALOGUE]
    assert len(perms) == len(set(perms))


def test_wildcard_not_in_catalogue():
    assert "*" not in {e.permission for e in PERMISSION_CATALOGUE}


def test_wildcard_not_in_valid_permissions():
    assert "*" not in VALID_PERMISSIONS


def test_valid_permissions_matches_catalogue():
    assert VALID_PERMISSIONS == {e.permission for e in PERMISSION_CATALOGUE}


def test_every_entry_has_non_empty_module_and_description():
    for entry in PERMISSION_CATALOGUE:
        assert isinstance(entry, PermissionEntry)
        assert entry.module.strip(), f"Empty module for {entry.permission}"
        assert entry.description.strip(), f"Empty description for {entry.permission}"


def test_admin_permissions_in_catalogue():
    """role:read, role:manage, user:manage are used in require_permission but in no base role."""
    assert "role:read" in VALID_PERMISSIONS
    assert "role:manage" in VALID_PERMISSIONS
    assert "user:manage" in VALID_PERMISSIONS


# ---------------------------------------------------------------------------
# CreateRoleRequest validation
# ---------------------------------------------------------------------------


def test_create_role_rejects_unknown_permission():
    from pydantic import ValidationError

    from src.api.schemas.role import CreateRoleRequest

    with pytest.raises(ValidationError) as exc_info:
        CreateRoleRequest(
            name="bad_role",
            permissions=["banana:explode"],
            ad_groups=["GRP-BAD"],
        )
    assert "not a recognised permission" in str(exc_info.value)


def test_create_role_rejects_wildcard():
    from pydantic import ValidationError

    from src.api.schemas.role import CreateRoleRequest

    with pytest.raises(ValidationError) as exc_info:
        CreateRoleRequest(
            name="wildcard_role",
            permissions=["*"],
            ad_groups=["GRP-WILD"],
        )
    assert "not a recognised permission" in str(exc_info.value)


def test_create_role_accepts_valid_catalogue_permission():
    from src.api.schemas.role import CreateRoleRequest

    req = CreateRoleRequest(
        name="valid_role",
        permissions=["user:read", "role:read"],
        ad_groups=["GRP-VALID"],
    )
    assert req.permissions == ["user:read", "role:read"]


def test_create_role_accepts_all_catalogue_permissions():
    from src.api.schemas.role import CreateRoleRequest

    req = CreateRoleRequest(
        name="all_perms_role",
        permissions=list(VALID_PERMISSIONS),
        ad_groups=["GRP-ALL"],
    )
    assert set(req.permissions) == VALID_PERMISSIONS


# ---------------------------------------------------------------------------
# UpdateRoleRequest validation
# ---------------------------------------------------------------------------


def test_update_role_rejects_unknown_permission():
    from pydantic import ValidationError

    from src.api.schemas.role import UpdateRoleRequest

    with pytest.raises(ValidationError) as exc_info:
        UpdateRoleRequest(permissions=["totally:fake"])
    assert "not a recognised permission" in str(exc_info.value)


def test_update_role_rejects_wildcard():
    from pydantic import ValidationError

    from src.api.schemas.role import UpdateRoleRequest

    with pytest.raises(ValidationError) as exc_info:
        UpdateRoleRequest(permissions=["*"])
    assert "not a recognised permission" in str(exc_info.value)


def test_update_role_accepts_valid_catalogue_permission():
    from src.api.schemas.role import UpdateRoleRequest

    req = UpdateRoleRequest(permissions=["action:write", "shift:read"])
    assert req.permissions == ["action:write", "shift:read"]


def test_update_role_none_permissions_skips_validation():
    from src.api.schemas.role import UpdateRoleRequest

    req = UpdateRoleRequest(permissions=None)
    assert req.permissions is None
