"""Unit tests: ES-359 — field-level and cross-entity validation.

Covers:
- Schema-level Pydantic validators (username, display_name, email, role name, permissions, AD groups).
- Application-level role-existence check on user create / update.
- Application-level user-assignment conflict on role delete.
All tests are pure (no I/O); in-memory stubs are used where repos are needed.
"""

import pytest
from pydantic import ValidationError as PydanticValidationError

from src.api.errors.exceptions import ConflictError
from src.api.errors.exceptions import ValidationError as AppValidationError
from src.api.schemas.role import CreateRoleRequest, UpdateRoleRequest
from src.api.schemas.user import CreateUserRequest, UpdateUserRequest
from src.application.admin.manage_roles import delete_custom_role
from src.application.admin.manage_users import create_user, update_user
from src.domain.users_roles.entities import Role, User
from src.infrastructure.persistence.in_memory_roles import InMemoryRoleRepository
from src.infrastructure.persistence.in_memory_users import InMemoryUserRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _role(name: str = "custom_role", is_custom: bool = True) -> Role:
    r = Role.create_custom(name, ["user:read"], ["GRP-TEST"])
    r.is_custom = is_custom
    return r


# ---------------------------------------------------------------------------
# CreateUserRequest — username
# ---------------------------------------------------------------------------


def test_username_valid_simple():
    r = CreateUserRequest(username="alice", display_name="Alice", email="alice@example.com")
    assert r.username == "alice"


def test_username_uppercased_normalised():
    r = CreateUserRequest(username="ALICE", display_name="Alice", email="alice@example.com")
    assert r.username == "alice"


def test_username_with_dot_and_hyphen():
    r = CreateUserRequest(username="john.doe-1", display_name="John", email="j@x.com")
    assert r.username == "john.doe-1"


def test_username_empty_fails():
    with pytest.raises(PydanticValidationError):
        CreateUserRequest(username="", display_name="Alice", email="a@b.com")


def test_username_spaces_only_fails():
    with pytest.raises(PydanticValidationError):
        CreateUserRequest(username="   ", display_name="Alice", email="a@b.com")


def test_username_with_at_sign_fails():
    with pytest.raises(PydanticValidationError):
        CreateUserRequest(username="alice@domain", display_name="Alice", email="a@b.com")


def test_username_with_spaces_fails():
    with pytest.raises(PydanticValidationError):
        CreateUserRequest(username="alice smith", display_name="Alice", email="a@b.com")


def test_username_too_long_fails():
    with pytest.raises(PydanticValidationError):
        CreateUserRequest(username="a" * 129, display_name="Alice", email="a@b.com")


# ---------------------------------------------------------------------------
# CreateUserRequest — display_name
# ---------------------------------------------------------------------------


def test_display_name_valid():
    r = CreateUserRequest(username="alice", display_name="Alice Smith", email="a@b.com")
    assert r.display_name == "Alice Smith"


def test_display_name_empty_fails():
    with pytest.raises(PydanticValidationError):
        CreateUserRequest(username="alice", display_name="", email="a@b.com")


def test_display_name_whitespace_only_fails():
    with pytest.raises(PydanticValidationError):
        CreateUserRequest(username="alice", display_name="   ", email="a@b.com")


def test_display_name_too_long_fails():
    with pytest.raises(PydanticValidationError):
        CreateUserRequest(username="alice", display_name="A" * 257, email="a@b.com")


# ---------------------------------------------------------------------------
# CreateUserRequest — email
# ---------------------------------------------------------------------------


def test_email_valid():
    r = CreateUserRequest(username="alice", display_name="Alice", email="alice@example.com")
    assert r.email == "alice@example.com"


def test_email_uppercased_normalised():
    r = CreateUserRequest(username="alice", display_name="Alice", email="ALICE@EXAMPLE.COM")
    assert r.email == "alice@example.com"


def test_email_no_at_sign_fails():
    with pytest.raises(PydanticValidationError):
        CreateUserRequest(username="alice", display_name="Alice", email="notanemail")


def test_email_no_dot_after_at_fails():
    with pytest.raises(PydanticValidationError):
        CreateUserRequest(username="alice", display_name="Alice", email="alice@nodot")


def test_email_too_short_fails():
    with pytest.raises(PydanticValidationError):
        CreateUserRequest(username="alice", display_name="Alice", email="a@b")


# ---------------------------------------------------------------------------
# UpdateUserRequest — display_name and email (when provided)
# ---------------------------------------------------------------------------


def test_update_display_name_whitespace_only_fails():
    with pytest.raises(PydanticValidationError):
        UpdateUserRequest(display_name="   ")


def test_update_display_name_none_allowed():
    r = UpdateUserRequest(display_name=None)
    assert r.display_name is None


def test_update_email_invalid_fails():
    with pytest.raises(PydanticValidationError):
        UpdateUserRequest(email="bad-email")


def test_update_email_none_allowed():
    r = UpdateUserRequest(email=None)
    assert r.email is None


# ---------------------------------------------------------------------------
# CreateRoleRequest — name
# ---------------------------------------------------------------------------


def test_role_name_valid():
    r = CreateRoleRequest(name="custom_role_1", permissions=["user:read"], ad_groups=["GRP-TEST"])
    assert r.name == "custom_role_1"


def test_role_name_starts_with_digit_fails():
    with pytest.raises(PydanticValidationError):
        CreateRoleRequest(name="1role", permissions=["user:read"], ad_groups=["GRP"])


def test_role_name_with_space_fails():
    with pytest.raises(PydanticValidationError):
        CreateRoleRequest(name="my role", permissions=["user:read"], ad_groups=["GRP"])


def test_role_name_with_hyphen_fails():
    # hyphens are not in the allowed pattern (letters, digits, underscore only)
    with pytest.raises(PydanticValidationError):
        CreateRoleRequest(name="my-role", permissions=["user:read"], ad_groups=["GRP"])


# ---------------------------------------------------------------------------
# CreateRoleRequest — permissions
# ---------------------------------------------------------------------------


def test_permission_wildcard_valid():
    r = CreateRoleRequest(name="myrole", permissions=["*"], ad_groups=["GRP"])
    assert r.permissions == ["*"]


def test_permission_resource_action_valid():
    r = CreateRoleRequest(name="myrole", permissions=["user:read", "role:manage"], ad_groups=["GRP"])
    assert "user:read" in r.permissions


def test_permission_invalid_format_fails():
    with pytest.raises(PydanticValidationError):
        CreateRoleRequest(name="myrole", permissions=["read-only"], ad_groups=["GRP"])


def test_permission_empty_string_fails():
    with pytest.raises(PydanticValidationError):
        CreateRoleRequest(name="myrole", permissions=[""], ad_groups=["GRP"])


def test_permissions_list_empty_fails():
    with pytest.raises(PydanticValidationError):
        CreateRoleRequest(name="myrole", permissions=[], ad_groups=["GRP"])


# ---------------------------------------------------------------------------
# CreateRoleRequest — ad_groups
# ---------------------------------------------------------------------------


def test_ad_groups_valid():
    r = CreateRoleRequest(name="myrole", permissions=["*"], ad_groups=["GRP-OPS", "GRP-SUP"])
    assert len(r.ad_groups) == 2


def test_ad_groups_empty_string_member_fails():
    with pytest.raises(PydanticValidationError):
        CreateRoleRequest(name="myrole", permissions=["*"], ad_groups=[""])


def test_ad_groups_list_empty_fails():
    with pytest.raises(PydanticValidationError):
        CreateRoleRequest(name="myrole", permissions=["*"], ad_groups=[])


# ---------------------------------------------------------------------------
# UpdateRoleRequest — validators (when values are supplied)
# ---------------------------------------------------------------------------


def test_update_role_name_with_space_fails():
    with pytest.raises(PydanticValidationError):
        UpdateRoleRequest(name="bad name")


def test_update_role_name_none_allowed():
    r = UpdateRoleRequest(name=None)
    assert r.name is None


def test_update_role_permissions_invalid_format_fails():
    with pytest.raises(PydanticValidationError):
        UpdateRoleRequest(permissions=["bad-format"])


def test_update_role_permissions_none_allowed():
    r = UpdateRoleRequest(permissions=None)
    assert r.permissions is None


def test_update_role_ad_groups_empty_string_fails():
    with pytest.raises(PydanticValidationError):
        UpdateRoleRequest(ad_groups=[""])


# ---------------------------------------------------------------------------
# Application-level: role_id existence check on create_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_user_nonexistent_role_raises_validation_error():
    user_repo = InMemoryUserRepository()
    role_repo = InMemoryRoleRepository()  # no roles beyond the base seed

    with pytest.raises(AppValidationError, match="does not exist"):
        await create_user(
            user_repo,
            username="bob",
            display_name="Bob",
            email="bob@example.com",
            role_id="nonexistent-role-id",
            role_repo=role_repo,
        )


@pytest.mark.asyncio
async def test_create_user_valid_role_id_succeeds():
    user_repo = InMemoryUserRepository()
    role_repo = InMemoryRoleRepository()
    all_roles = await role_repo.list_all()
    valid_role_id = all_roles[0].id

    user = await create_user(
        user_repo,
        username="carol",
        display_name="Carol",
        email="carol@example.com",
        role_id=valid_role_id,
        role_repo=role_repo,
    )
    assert user.role_id == valid_role_id


@pytest.mark.asyncio
async def test_create_user_no_role_repo_skips_check():
    user_repo = InMemoryUserRepository()
    # No role_repo passed — should succeed even with a bogus role_id
    user = await create_user(
        user_repo,
        username="dave",
        display_name="Dave",
        email="dave@example.com",
        role_id="fake-id",
        role_repo=None,
    )
    assert user.role_id == "fake-id"


# ---------------------------------------------------------------------------
# Application-level: role_id existence check on update_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_user_nonexistent_role_raises_validation_error():
    user_repo = InMemoryUserRepository()
    role_repo = InMemoryRoleRepository()
    user = await create_user(
        user_repo, username="eve", display_name="Eve", email="eve@x.com"
    )

    with pytest.raises(AppValidationError, match="does not exist"):
        await update_user(
            user_repo,
            user.id,
            role_id="nonexistent",
            role_repo=role_repo,
        )


@pytest.mark.asyncio
async def test_update_user_clear_role_skips_existence_check():
    user_repo = InMemoryUserRepository()
    role_repo = InMemoryRoleRepository()
    user = await create_user(
        user_repo, username="frank", display_name="Frank", email="frank@x.com"
    )

    updated = await update_user(
        user_repo,
        user.id,
        role_id=None,  # clear the role
        role_repo=role_repo,
    )
    assert updated.role_id is None


# ---------------------------------------------------------------------------
# Application-level: role-delete blocked if users assigned
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_role_with_users_assigned_raises_conflict():
    role_repo = InMemoryRoleRepository()
    user_repo = InMemoryUserRepository()

    role = _role("custom_blockme")
    await role_repo.add(role)

    # Assign a user to this role
    user = User.create("hal", "Hal", "hal@x.com", role_id=role.id)
    await user_repo.add(user)

    with pytest.raises(ConflictError, match="unassign them first"):
        await delete_custom_role(role_repo, role.id, user_repo=user_repo)


@pytest.mark.asyncio
async def test_delete_role_no_users_assigned_succeeds():
    role_repo = InMemoryRoleRepository()
    user_repo = InMemoryUserRepository()

    role = _role("custom_empty")
    await role_repo.add(role)

    await delete_custom_role(role_repo, role.id, user_repo=user_repo)
    assert await role_repo.get(role.id) is None


@pytest.mark.asyncio
async def test_delete_role_no_user_repo_skips_check():
    role_repo = InMemoryRoleRepository()
    user_repo = InMemoryUserRepository()

    role = _role("custom_norepo")
    await role_repo.add(role)
    user = User.create("ivan", "Ivan", "ivan@x.com", role_id=role.id)
    await user_repo.add(user)

    # Without user_repo the conflict check is skipped — role deletes even with a user assigned
    await delete_custom_role(role_repo, role.id, user_repo=None)
    assert await role_repo.get(role.id) is None
