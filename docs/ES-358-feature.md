# ES-358: User & Role CRUD

**Epic:** EP-10 — Administration & RBAC  
**Story:** US-047  
**Branch:** `feature/EP-10-ES-358-user-role-crud`

---

## Overview

Implements full CRUD for admin-managed **users** and extends the existing **role** CRUD to cover base roles. Administrators can now provision user records, optionally assigning a manual role override that takes precedence over AD-group-based role resolution.

---

## Architecture

Clean architecture pattern — changes flow inward from API to domain, never the reverse.

```
api/v1/admin.py          ← new /admin/users endpoints
api/schemas/user.py      ← CreateUserRequest, UpdateUserRequest, AdminUserResponse
api/deps.py              ← UserUoW dependency + _user_repo singleton

application/admin/manage_users.py           ← use-case functions
application/users_roles/repository.py       ← UserRepository ABC (port)

domain/users_roles/entities.py              ← User dataclass

infrastructure/persistence/
  tables.py              ← users SQLAlchemy table
  in_memory_users.py     ← InMemoryUserRepository
  sql_users.py           ← SqlUserRepository
  in_memory_uow.py       ← MemoryUserUnitOfWork
  unit_of_work.py        ← SqlUserUnitOfWork + UserUnitOfWork Protocol

migrations/
  0003_users.sql         ← T-SQL DDL (MS SQL Server)
  0003_users.rollback.sql
```

---

## Domain Entity — `User`

| Field          | Type          | Notes                                              |
|----------------|---------------|----------------------------------------------------|
| `id`           | `str`         | UUID4 hex (32 chars)                               |
| `username`     | `str`         | AD sAMAccountName, normalised to lowercase         |
| `display_name` | `str`         | Human-readable name                                |
| `email`        | `str`         | Normalised to lowercase                            |
| `is_active`    | `bool`        | Default `True`; deactivated users kept for audit   |
| `role_id`      | `str \| None` | Manual override; `None` = derive from AD groups    |
| `created_at`   | `datetime`    | UTC, set on creation                               |
| `updated_at`   | `datetime`    | UTC, bumped on every `update_user` call            |

---

## API Endpoints

Base path: `/api/v1/admin/users`

| Method   | Path               | Permission   | Description                              |
|----------|--------------------|--------------|------------------------------------------|
| `GET`    | `/admin/users`     | `user:read`  | List all provisioned users               |
| `GET`    | `/admin/users/{id}`| `user:read`  | Get a single user by ID                  |
| `POST`   | `/admin/users`     | `user:manage`| Provision a new user                     |
| `PATCH`  | `/admin/users/{id}`| `user:manage`| Update a user (partial update)           |
| `DELETE` | `/admin/users/{id}`| `user:manage`| Delete a user record                     |

### Permissions by base role

| Role            | `user:read` | `user:manage` |
|-----------------|-------------|---------------|
| `administrator` | ✓ (via `*`) | ✓ (via `*`)   |
| `super_user`    | ✓           | ✗             |
| All others      | ✗           | ✗             |

---

## Request / Response Schemas

### `POST /admin/users` — `CreateUserRequest`

```json
{
  "username": "john.doe",
  "display_name": "John Doe",
  "email": "john.doe@olng.com",
  "role_id": null
}
```

- `username` is normalised to lowercase automatically.
- `email` is normalised to lowercase automatically.
- `role_id` is optional; omit or pass `null` to use AD-group resolution.
- Duplicate `username` → **409 Conflict**.

### `PATCH /admin/users/{id}` — `UpdateUserRequest`

All fields optional; only supplied fields are updated.

```json
{
  "display_name": "John D. Updated",
  "email": "jdoe@olng.com",
  "role_id": "base-supervisor",
  "clear_role": false,
  "is_active": true
}
```

- `clear_role: true` sets `role_id` to `null`, removing the manual override.
- `role_id` without `clear_role` sets or changes the override.
- Fields not supplied are left unchanged.

### `AdminUserResponse` (all mutations + GET endpoints)

```json
{
  "id": "a3f2b1c4d5e6...",
  "username": "john.doe",
  "display_name": "John Doe",
  "email": "john.doe@olng.com",
  "is_active": true,
  "role_id": null,
  "created_at": "2026-08-01T12:00:00Z",
  "updated_at": "2026-08-01T12:00:00Z"
}
```

All responses use the project-standard envelope:

```json
{
  "ok": true,
  "correlation_id": "...",
  "data": { ... }
}
```

---

## Audit Trail

Every mutation writes a hash-chained audit row (same mechanism as roles and pending actions).

| Action         | `entity_type` | Payload fields                                           |
|----------------|---------------|----------------------------------------------------------|
| `user.create`  | `user`        | `username, display_name, email, role_id`                 |
| `user.update`  | `user`        | `username, display_name, email, role_id, is_active`      |
| `user.delete`  | `user`        | `username`                                               |

Under the `memory` backend (default in tests), audit rows are no-ops (`NullAuditRecorder`). Under `sql`, they are committed atomically with the mutation in the same transaction.

---

## Persistence Backend

The implementation supports both backends via the `ELOG_PERSISTENCE_BACKEND` env var:

| Backend  | User repository           | Unit of work            |
|----------|--------------------------|-------------------------|
| `memory` | `InMemoryUserRepository` | `MemoryUserUnitOfWork`  |
| `sql`    | `SqlUserRepository`      | `SqlUserUnitOfWork`     |

### SQL Schema (MS SQL Server)

```sql
CREATE TABLE dbo.users (
    id           NVARCHAR(32)      NOT NULL CONSTRAINT PK_users PRIMARY KEY,
    username     NVARCHAR(128)     NOT NULL CONSTRAINT UQ_users_username UNIQUE,
    display_name NVARCHAR(256)     NOT NULL,
    email        NVARCHAR(256)     NOT NULL,
    is_active    BIT               NOT NULL CONSTRAINT DF_users_is_active DEFAULT 1,
    role_id      NVARCHAR(32)      NULL CONSTRAINT FK_users_role FOREIGN KEY REFERENCES dbo.roles(id),
    created_at   DATETIMEOFFSET(7) NOT NULL,
    updated_at   DATETIMEOFFSET(7) NOT NULL
);
CREATE INDEX IX_users_username ON dbo.users (username);
```

Migration applied via `migrations/0003_users.sql`. Rollback via `migrations/0003_users.rollback.sql`.

---

## Files Changed

### New files

| File                                                        | Purpose                            |
|-------------------------------------------------------------|------------------------------------|
| `migrations/0003_users.sql`                                 | T-SQL DDL for `users` table        |
| `migrations/0003_users.rollback.sql`                        | Rollback script                    |
| `src/infrastructure/persistence/in_memory_users.py`         | In-memory user repo (tests/local)  |
| `src/infrastructure/persistence/sql_users.py`               | MS SQL user repo                   |
| `tests/unit/test_manage_users.py`                           | Use-case unit tests (26 tests)     |
| `tests/integration/test_users_api.py`                       | API integration tests (20 tests)   |
| `docs/ES-358-feature.md`                                    | This document                      |
| `docs/ES-358-test-cases.md`                                 | Test case documentation            |

### Modified files

| File                                                     | Change                                           |
|----------------------------------------------------------|--------------------------------------------------|
| `src/domain/users_roles/entities.py`                     | Added `User` dataclass                           |
| `src/application/users_roles/repository.py`              | Added `UserRepository` ABC                       |
| `src/application/admin/manage_users.py`                  | Implemented use cases (was TODO stub)            |
| `src/infrastructure/persistence/tables.py`               | Added `users` SQLAlchemy table                   |
| `src/infrastructure/persistence/in_memory_uow.py`        | Added `MemoryUserUnitOfWork`                     |
| `src/infrastructure/persistence/unit_of_work.py`         | Added `SqlUserUnitOfWork` + `UserUnitOfWork` Protocol |
| `src/api/schemas/user.py`                                | Added `CreateUserRequest`, `UpdateUserRequest`, `AdminUserResponse` |
| `src/api/v1/admin.py`                                    | Added 5 `/admin/users` endpoints                 |
| `src/api/deps.py`                                        | Added `get_user_uow`, `UserUoW`, `_user_repo`    |
