# ES-358: Test Cases — User & Role CRUD

**Epic:** EP-10 — Administration & RBAC  
**Story:** US-047

---

## Test Suite Summary

| Suite                                          | File                                           | Tests |
|------------------------------------------------|------------------------------------------------|-------|
| Use-case unit tests                            | `tests/unit/test_manage_users.py`              | 20    |
| API integration tests (memory backend)         | `tests/integration/test_users_api.py`          | 20    |
| **Total**                                      |                                                | **40**|

All tests run with `ELOG_PERSISTENCE_BACKEND=memory` and `ELOG_AUTH_STUB_ENABLED=true` (enforced by `tests/conftest.py`).

---

## Unit Tests — `test_manage_users.py`

These tests exercise the application use-case functions directly against the `InMemoryUserRepository`. No HTTP layer, no auth, no database.

### Create User

| ID    | Test Name                                  | What is verified                                      |
|-------|--------------------------------------------|-------------------------------------------------------|
| U-01  | `test_create_user_sets_defaults`           | Created user has `is_active=True`, `role_id=None`, 32-char hex ID |
| U-02  | `test_create_user_normalises_username`     | `ALICE` → stored as `alice`                           |
| U-03  | `test_create_user_normalises_email`        | `Alice@X.COM` → stored as `alice@x.com`               |
| U-04  | `test_create_user_with_role_override`      | `role_id` stored correctly when provided              |
| U-05  | `test_create_duplicate_username_raises_conflict` | Second create with same username raises `ConflictError` |
| U-06  | `test_create_duplicate_is_case_insensitive` | `ALICE` conflicts with existing `alice`               |

### Read User

| ID    | Test Name                                  | What is verified                                      |
|-------|--------------------------------------------|-------------------------------------------------------|
| U-07  | `test_get_user_returns_correct_record`     | `get_user` returns the correct entity by ID           |
| U-08  | `test_get_unknown_user_raises_not_found`   | Non-existent ID raises `NotFoundError`                |
| U-09  | `test_list_users_returns_all_sorted`       | `list_users` returns all users sorted by `username`   |

### Update User

| ID    | Test Name                                  | What is verified                                      |
|-------|--------------------------------------------|-------------------------------------------------------|
| U-10  | `test_update_display_name`                 | `display_name` updated correctly                      |
| U-11  | `test_update_email_normalised`             | `email` normalised to lowercase on update             |
| U-12  | `test_deactivate_user`                     | `is_active=False` persisted correctly                 |
| U-13  | `test_set_role_override`                   | `role_id` set when explicit value provided            |
| U-14  | `test_clear_role_override`                 | `role_id=None` explicitly clears the override         |
| U-15  | `test_update_without_role_kwarg_leaves_role_unchanged` | Omitting `role_id` kwarg does not clear existing override |
| U-16  | `test_update_unknown_user_raises_not_found` | Non-existent ID raises `NotFoundError`               |
| U-17  | `test_update_touches_updated_at`           | `updated_at` timestamp advances on every update       |

### Delete User

| ID    | Test Name                                  | What is verified                                      |
|-------|--------------------------------------------|-------------------------------------------------------|
| U-18  | `test_delete_user_removes_from_store`      | After delete, `get_user` raises `NotFoundError`       |
| U-19  | `test_delete_unknown_user_raises_not_found` | Non-existent ID raises `NotFoundError`               |

---

## Integration Tests — `test_users_api.py`

These tests exercise the full HTTP stack (ASGI) using `AsyncClient` with the in-memory backend. Auth tokens are minted via the dev stub issuer.

Personas used:

| Token       | Group                    | Role            | Relevant permissions         |
|-------------|--------------------------|-----------------|------------------------------|
| `ADMIN`     | `OLNG-ELOG-ADMINS`       | `administrator` | `*` (includes `user:manage`) |
| `SUPER_USER`| `OLNG-ELOG-SUPERUSERS`   | `super_user`    | `user:read`                  |
| `OPERATOR`  | `OLNG-ELOG-OPERATORS`    | `operator`      | no user permissions          |

### List / Get

| ID    | Test Name                                     | What is verified                                    |
|-------|-----------------------------------------------|-----------------------------------------------------|
| I-01  | `test_list_users_initially_empty`             | Fresh store returns empty list; admin can access    |
| I-02  | `test_super_user_can_list_users`              | `user:read` is enough for listing                   |
| I-03  | `test_operator_cannot_list_users`             | Missing `user:read` → 403                           |
| I-04  | `test_unauthenticated_cannot_list_users`      | No token → 401                                      |

### Create

| ID    | Test Name                                         | What is verified                                       |
|-------|---------------------------------------------------|--------------------------------------------------------|
| I-05  | `test_create_user_returns_user_record`            | 200; response contains all expected fields             |
| I-06  | `test_create_user_normalises_username_to_lowercase`| `JOHN.DOE` → stored as `john.doe`                    |
| I-07  | `test_create_user_with_role_override`             | `role_id` round-trips correctly                        |
| I-08  | `test_operator_cannot_create_user`                | Missing `user:manage` → 403                            |
| I-09  | `test_duplicate_username_is_conflict`             | Second POST with same username → 409                   |

### Get Single

| ID    | Test Name                                  | What is verified                                      |
|-------|--------------------------------------------|-------------------------------------------------------|
| I-10  | `test_get_user_returns_correct_record`     | GET by ID returns correct user                        |
| I-11  | `test_get_unknown_user_is_404`             | Non-existent ID → 404                                 |

### Update

| ID    | Test Name                                  | What is verified                                      |
|-------|--------------------------------------------|-------------------------------------------------------|
| I-12  | `test_update_user_display_name`            | PATCH `display_name` updates the record               |
| I-13  | `test_deactivate_user`                     | PATCH `is_active: false` deactivates the user         |
| I-14  | `test_assign_role_override`                | PATCH `role_id` sets manual role override             |
| I-15  | `test_clear_role_override`                 | PATCH `clear_role: true` removes role override        |
| I-16  | `test_update_unknown_user_is_404`          | PATCH on non-existent user → 404                      |
| I-17  | `test_operator_cannot_update_user`         | Missing `user:manage` → 403                           |

### Delete

| ID    | Test Name                                  | What is verified                                      |
|-------|--------------------------------------------|-------------------------------------------------------|
| I-18  | `test_delete_user_removes_record`          | DELETE removes user; subsequent list does not include it |
| I-19  | `test_delete_unknown_user_is_404`          | DELETE on non-existent user → 404                     |
| I-20  | `test_operator_cannot_delete_user`         | Missing `user:manage` → 403                           |

### End-to-End

| ID    | Test Name                                  | What is verified                                                     |
|-------|--------------------------------------------|----------------------------------------------------------------------|
| I-21  | `test_full_create_read_update_delete_flow` | Create → list → get single → update → delete → verify 404 on get   |

---

## How to Run

```bash
# All tests (160 total)
.venv/Scripts/python.exe -m pytest tests/ -q

# Only ES-358 tests
.venv/Scripts/python.exe -m pytest tests/unit/test_manage_users.py tests/integration/test_users_api.py -v

# With verbose output
.venv/Scripts/python.exe -m pytest tests/integration/test_users_api.py -v
```

---

## Coverage Notes

- **Auth** scenarios covered: valid admin, `user:read`-only, no permission, unauthenticated.
- **Persistence** tested: in-memory backend; SQL backend verified by running migration 0003 against local MS SQL and confirming the server starts cleanly.
- **Audit** rows: not verified in integration tests (memory backend uses `NullAuditRecorder`); audit payload structure is verified implicitly by the use-case unit tests whenever `audit` is not `None`.
- **Not yet covered** (out of ES-358 scope): SQL-backend integration tests, audit history endpoint for users, role-override resolution at token validation time.
