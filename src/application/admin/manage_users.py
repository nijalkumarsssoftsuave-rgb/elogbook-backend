"""Use cases: Admin-managed users (ES-358 — User & role CRUD).

An Administrator can create, read, update and delete user records. A user record
optionally carries a ``role_id`` override that takes precedence over AD-group-based role
resolution at sign-in; omitting it means the user's role comes from their AD groups as
normal.
"""

from src.api.errors.exceptions import ConflictError, NotFoundError, ValidationError
from src.application.audit.recorder import AuditEntry, AuditRecorder
from src.application.users_roles.repository import RoleRepository, UserRepository
from src.domain.users_roles.entities import User

_UNSET = object()  # sentinel — distinguishes "not passed" from explicit None


async def _assert_role_exists(role_repo: RoleRepository, role_id: str) -> None:
    if await role_repo.get(role_id) is None:
        raise ValidationError(f"Role '{role_id}' does not exist.")


async def list_users(repo: UserRepository) -> list[User]:
    return await repo.list_all()


async def get_user(repo: UserRepository, user_id: str) -> User:
    user = await repo.get(user_id)
    if user is None:
        raise NotFoundError(f"User {user_id} was not found.")
    return user


async def create_user(
    repo: UserRepository,
    *,
    username: str,
    display_name: str,
    email: str,
    role_id: str | None = None,
    role_repo: RoleRepository | None = None,
    audit: AuditRecorder | None = None,
    actor: str = "system",
) -> User:
    if role_id is not None and role_repo is not None:
        await _assert_role_exists(role_repo, role_id)
    existing = await repo.get_by_username(username)
    if existing is not None:
        raise ConflictError(f"A user with username '{username}' already exists.")
    user = User.create(username, display_name, email, role_id)
    stored = await repo.add(user)
    if audit is not None:
        await audit.record(
            AuditEntry(
                actor=actor,
                action="user.create",
                entity_type="user",
                entity_id=stored.id,
                payload={
                    "username": stored.username,
                    "display_name": stored.display_name,
                    "email": stored.email,
                    "role_id": stored.role_id,
                },
            )
        )
    return stored


async def update_user(
    repo: UserRepository,
    user_id: str,
    *,
    display_name: str | None = None,
    email: str | None = None,
    role_id: object = _UNSET,
    is_active: bool | None = None,
    role_repo: RoleRepository | None = None,
    audit: AuditRecorder | None = None,
    actor: str = "system",
) -> User:
    """Update an existing user. Pass ``role_id=None`` to explicitly clear the override."""
    if role_id is not _UNSET and role_id is not None and role_repo is not None:
        await _assert_role_exists(role_repo, role_id)  # type: ignore[arg-type]
    user = await repo.get(user_id)
    if user is None:
        raise NotFoundError(f"User {user_id} was not found.")
    if display_name is not None:
        user.display_name = display_name
    if email is not None:
        user.email = email.lower()
    if role_id is not _UNSET:
        user.role_id = role_id  # type: ignore[assignment]
    if is_active is not None:
        user.is_active = is_active
    user.touch()
    updated = await repo.update(user)
    if audit is not None:
        await audit.record(
            AuditEntry(
                actor=actor,
                action="user.update",
                entity_type="user",
                entity_id=updated.id,
                payload={
                    "username": updated.username,
                    "display_name": updated.display_name,
                    "email": updated.email,
                    "role_id": updated.role_id,
                    "is_active": updated.is_active,
                },
            )
        )
    return updated


async def delete_user(
    repo: UserRepository,
    user_id: str,
    *,
    audit: AuditRecorder | None = None,
    actor: str = "system",
) -> None:
    user = await repo.get(user_id)
    if user is None:
        raise NotFoundError(f"User {user_id} was not found.")
    await repo.delete(user_id)
    if audit is not None:
        await audit.record(
            AuditEntry(
                actor=actor,
                action="user.delete",
                entity_type="user",
                entity_id=user_id,
                payload={"username": user.username},
            )
        )
