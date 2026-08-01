"""Unit tests for ES-363: data-scope model — list_known_areas use case and
area_scope field validation.

All tests are pure (no I/O); in-memory stubs used throughout.
"""

import pytest
from pydantic import ValidationError as PydanticValidationError

from src.api.schemas.role import CreateRoleRequest, UpdateRoleRequest
from src.application.admin.manage_roles import create_custom_role, list_known_areas
from src.domain.users_roles.seed import BASE_ROLES
from src.infrastructure.persistence.in_memory_roles import InMemoryRoleRepository


@pytest.fixture
def repo():
    r = InMemoryRoleRepository()
    r._items = {role.id: role for role in BASE_ROLES}
    return r


# ---------------------------------------------------------------------------
# list_known_areas use case
# ---------------------------------------------------------------------------


async def test_list_known_areas_no_scoped_roles_returns_empty(repo):
    areas = await list_known_areas(repo)
    assert areas == []


async def test_list_known_areas_base_roles_only_returns_empty(repo):
    # All base roles have area_scope=None (full plant)
    areas = await list_known_areas(repo)
    assert areas == []


async def test_list_known_areas_single_scoped_role(repo):
    await create_custom_role(
        repo,
        name="train1_op",
        permissions=["action:read"],
        ad_groups=["GRP-T1"],
        area_scope=["Train 1", "Train 2"],
    )
    areas = await list_known_areas(repo)
    assert areas == ["Train 1", "Train 2"]


async def test_list_known_areas_multiple_roles_deduplicates(repo):
    await create_custom_role(
        repo,
        name="role_a",
        permissions=["action:read"],
        ad_groups=["GRP-A"],
        area_scope=["Area-A", "Area-B"],
    )
    await create_custom_role(
        repo,
        name="role_b",
        permissions=["action:read"],
        ad_groups=["GRP-B"],
        area_scope=["Area-B", "Area-C"],
    )
    areas = await list_known_areas(repo)
    assert areas == ["Area-A", "Area-B", "Area-C"]


async def test_list_known_areas_sorted_alphabetically(repo):
    await create_custom_role(
        repo,
        name="scoped",
        permissions=["action:read"],
        ad_groups=["GRP-S"],
        area_scope=["Zone-C", "Zone-A", "Zone-B"],
    )
    areas = await list_known_areas(repo)
    assert areas == ["Zone-A", "Zone-B", "Zone-C"]


async def test_list_known_areas_full_plant_roles_excluded(repo):
    await create_custom_role(
        repo,
        name="full_plant",
        permissions=["action:read"],
        ad_groups=["GRP-FP"],
        area_scope=None,
    )
    areas = await list_known_areas(repo)
    assert areas == []


async def test_list_known_areas_mixed_scoped_and_full_plant(repo):
    await create_custom_role(
        repo,
        name="scoped_role",
        permissions=["action:read"],
        ad_groups=["GRP-SC"],
        area_scope=["Area-X"],
    )
    await create_custom_role(
        repo,
        name="full_plant_role",
        permissions=["action:read"],
        ad_groups=["GRP-FP"],
        area_scope=None,
    )
    areas = await list_known_areas(repo)
    assert areas == ["Area-X"]


# ---------------------------------------------------------------------------
# CreateRoleRequest — area_scope validation
# ---------------------------------------------------------------------------


def test_create_role_area_scope_none_allowed():
    req = CreateRoleRequest(
        name="full_plant",
        permissions=["action:read"],
        ad_groups=["GRP"],
        area_scope=None,
    )
    assert req.area_scope is None


def test_create_role_area_scope_omitted_defaults_to_none():
    req = CreateRoleRequest(name="full_plant", permissions=["action:read"], ad_groups=["GRP"])
    assert req.area_scope is None


def test_create_role_area_scope_valid_strings():
    req = CreateRoleRequest(
        name="scoped",
        permissions=["action:read"],
        ad_groups=["GRP"],
        area_scope=["Train 1", "Train 2"],
    )
    assert req.area_scope == ["Train 1", "Train 2"]


def test_create_role_area_scope_empty_string_fails():
    with pytest.raises(PydanticValidationError):
        CreateRoleRequest(
            name="bad",
            permissions=["action:read"],
            ad_groups=["GRP"],
            area_scope=[""],
        )


def test_create_role_area_scope_whitespace_only_fails():
    with pytest.raises(PydanticValidationError):
        CreateRoleRequest(
            name="bad",
            permissions=["action:read"],
            ad_groups=["GRP"],
            area_scope=["   "],
        )


# ---------------------------------------------------------------------------
# UpdateRoleRequest — area_scope validation
# ---------------------------------------------------------------------------


def test_update_role_area_scope_none_allowed():
    req = UpdateRoleRequest(area_scope=None)
    assert req.area_scope is None


def test_update_role_area_scope_valid_strings():
    req = UpdateRoleRequest(area_scope=["Area-A", "Area-B"])
    assert req.area_scope == ["Area-A", "Area-B"]


def test_update_role_area_scope_empty_string_fails():
    with pytest.raises(PydanticValidationError):
        UpdateRoleRequest(area_scope=[""])


def test_update_role_area_scope_whitespace_only_fails():
    with pytest.raises(PydanticValidationError):
        UpdateRoleRequest(area_scope=["  "])
