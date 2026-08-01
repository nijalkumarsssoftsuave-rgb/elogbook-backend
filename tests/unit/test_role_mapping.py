"""Unit tests for the flat AD-group-to-role mapping view (BE-US002-2)."""

from src.application.admin.manage_roles import create_custom_role, get_group_role_mapping
from src.infrastructure.persistence.in_memory_roles import InMemoryRoleRepository


async def test_mapping_has_one_row_per_base_role_group():
    repo = InMemoryRoleRepository()
    mapping = await get_group_role_mapping(repo)

    groups = {m.ad_group for m in mapping}
    assert groups == {
        "OLNG-ELOG-OPERATORS",
        "OLNG-ELOG-SUPERVISORS",
        "OLNG-ELOG-SUPERINTENDENTS",
        "OLNG-ELOG-ADMINS",
        "OLNG-ELOG-SUPERUSERS",
    }
    assert all(not m.is_custom for m in mapping)


async def test_mapping_is_sorted_by_ad_group():
    repo = InMemoryRoleRepository()
    mapping = await get_group_role_mapping(repo)
    assert [m.ad_group for m in mapping] == sorted(m.ad_group for m in mapping)


async def test_role_with_multiple_groups_yields_one_row_per_group():
    repo = InMemoryRoleRepository()
    role = await create_custom_role(
        repo,
        name="dual_group_role",
        permissions=["action:read"],
        ad_groups=["GROUP-A", "GROUP-B"],
    )

    mapping = await get_group_role_mapping(repo)
    rows = [m for m in mapping if m.role_id == role.id]

    assert {r.ad_group for r in rows} == {"GROUP-A", "GROUP-B"}
    assert all(r.role_name == "dual_group_role" and r.is_custom for r in rows)


async def test_mapping_reflects_custom_role_area_scope():
    repo = InMemoryRoleRepository()
    await create_custom_role(
        repo,
        name="train1_operator",
        permissions=["action:read"],
        ad_groups=["OLNG-ELOG-TRAIN1"],
        area_scope=["Train 1"],
    )

    mapping = await get_group_role_mapping(repo)
    row = next(m for m in mapping if m.ad_group == "OLNG-ELOG-TRAIN1")
    assert row.area_scope == ["Train 1"]
