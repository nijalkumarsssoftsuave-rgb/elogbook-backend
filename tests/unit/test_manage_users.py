"""Unit tests for the manage_users application use cases.

Uses the in-memory user repository so no DB is needed. Audit is a NullAuditRecorder
(same as the memory UoW uses in tests).
"""

import pytest

from src.api.errors.exceptions import ConflictError, NotFoundError
from src.application.admin.manage_users import (
    create_user,
    delete_user,
    get_user,
    list_users,
    update_user,
)
from src.infrastructure.persistence.in_memory_users import InMemoryUserRepository


@pytest.fixture
def repo():
    return InMemoryUserRepository()


# ---------------------------------------------------------------------------
# create_user
# ---------------------------------------------------------------------------


async def test_create_user_sets_defaults(repo):
    user = await create_user(repo, username="alice", display_name="Alice", email="alice@x.com")
    assert user.username == "alice"
    assert user.email == "alice@x.com"
    assert user.is_active is True
    assert user.role_id is None
    assert len(user.id) == 32


async def test_create_user_normalises_username(repo):
    user = await create_user(repo, username="ALICE", display_name="Alice", email="alice@x.com")
    assert user.username == "alice"


async def test_create_user_normalises_email(repo):
    user = await create_user(repo, username="alice", display_name="Alice", email="Alice@X.COM")
    assert user.email == "alice@x.com"


async def test_create_user_with_role_override(repo):
    user = await create_user(
        repo, username="bob", display_name="Bob", email="bob@x.com", role_id="base-operator"
    )
    assert user.role_id == "base-operator"


async def test_create_duplicate_username_raises_conflict(repo):
    await create_user(repo, username="alice", display_name="Alice", email="alice@x.com")
    with pytest.raises(ConflictError, match="alice"):
        await create_user(repo, username="alice", display_name="Alice 2", email="a2@x.com")


async def test_create_duplicate_is_case_insensitive(repo):
    await create_user(repo, username="alice", display_name="Alice", email="alice@x.com")
    with pytest.raises(ConflictError):
        await create_user(repo, username="ALICE", display_name="Alice 2", email="a2@x.com")


# ---------------------------------------------------------------------------
# get_user / list_users
# ---------------------------------------------------------------------------


async def test_get_user_returns_correct_record(repo):
    created = await create_user(repo, username="carol", display_name="Carol", email="c@x.com")
    fetched = await get_user(repo, created.id)
    assert fetched.id == created.id


async def test_get_unknown_user_raises_not_found(repo):
    with pytest.raises(NotFoundError):
        await get_user(repo, "nonexistent-id")


async def test_list_users_returns_all_sorted(repo):
    await create_user(repo, username="zara", display_name="Zara", email="z@x.com")
    await create_user(repo, username="alice", display_name="Alice", email="a@x.com")
    users = await list_users(repo)
    assert [u.username for u in users] == ["alice", "zara"]


# ---------------------------------------------------------------------------
# update_user
# ---------------------------------------------------------------------------


async def test_update_display_name(repo):
    user = await create_user(repo, username="dave", display_name="Dave Old", email="d@x.com")
    updated = await update_user(repo, user.id, display_name="Dave New")
    assert updated.display_name == "Dave New"


async def test_update_email_normalised(repo):
    user = await create_user(repo, username="eve", display_name="Eve", email="e@x.com")
    updated = await update_user(repo, user.id, email="EVE@EXAMPLE.COM")
    assert updated.email == "eve@example.com"


async def test_deactivate_user(repo):
    user = await create_user(repo, username="frank", display_name="Frank", email="f@x.com")
    updated = await update_user(repo, user.id, is_active=False)
    assert updated.is_active is False


async def test_set_role_override(repo):
    user = await create_user(repo, username="grace", display_name="Grace", email="g@x.com")
    updated = await update_user(repo, user.id, role_id="base-supervisor")
    assert updated.role_id == "base-supervisor"


async def test_clear_role_override(repo):
    user = await create_user(
        repo, username="henry", display_name="Henry", email="h@x.com", role_id="base-operator"
    )
    updated = await update_user(repo, user.id, role_id=None)
    assert updated.role_id is None


async def test_update_without_role_kwarg_leaves_role_unchanged(repo):
    user = await create_user(
        repo, username="igor", display_name="Igor", email="i@x.com", role_id="base-operator"
    )
    updated = await update_user(repo, user.id, display_name="Igor Updated")
    assert updated.role_id == "base-operator"


async def test_update_unknown_user_raises_not_found(repo):
    with pytest.raises(NotFoundError):
        await update_user(repo, "no-such-id", display_name="X")


async def test_update_touches_updated_at(repo):
    user = await create_user(repo, username="julia", display_name="Julia", email="j@x.com")
    original_ts = user.updated_at
    updated = await update_user(repo, user.id, display_name="Julia Updated")
    assert updated.updated_at >= original_ts


# ---------------------------------------------------------------------------
# delete_user
# ---------------------------------------------------------------------------


async def test_delete_user_removes_from_store(repo):
    user = await create_user(repo, username="karen", display_name="Karen", email="k@x.com")
    await delete_user(repo, user.id)
    with pytest.raises(NotFoundError):
        await get_user(repo, user.id)


async def test_delete_unknown_user_raises_not_found(repo):
    with pytest.raises(NotFoundError):
        await delete_user(repo, "no-such-id")
