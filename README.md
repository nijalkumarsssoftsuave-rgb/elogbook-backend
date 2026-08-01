# E-Logbook — Backend Service

The **system-of-record** service for the OLNG E-Logbook platform: authentication and
RBAC, all business logic and persistence (summaries, pending actions, notifications,
admin/config), and the immutable audit chain. It is the API the frontend calls, and it
calls the separate **`elogbook-ai`** service for anything requiring inference.

Built to the **Engineering Code Standards** — clean architecture, SOLID, DDD,
repository pattern with dependency injection, one unified response envelope, and the
CI quality gates (lint, scan, ≥ 80% coverage).

## Layout

```
src/
├── domain/          business entities & rules — no framework/IO imports
├── application/     use cases; ports the domain needs
├── infrastructure/  adapters: MS SQL, Valkey, ai-service client, auth, audit
├── api/             FastAPI delivery — routers, schemas, middleware, error handlers
└── core/            config, logging, the response envelope
```

Dependencies point **inward**: `api` → `application` → `domain`. Adapters in
`infrastructure` implement ports and are injected in `api/deps.py`. Business logic never
lives in the API layer.

## Running locally

```bash
python -m venv .venv && . .venv/Scripts/activate   # Windows; use bin/activate on POSIX
pip install -e ".[dev]"
cp .env.example .env
uvicorn src.main:app --reload
```

Open **http://localhost:8000/docs** for the generated OpenAPI/Swagger UI.

Auth uses a **local dev token issuer** until AD FS is wired (Tracker A-01). It mints a
real signed JWT (RS256) with the same claim shape AD FS will send — issuer, audience,
expiry, AD groups — so the validation code (`src/infrastructure/auth/token_validator.py`)
doesn't change when A-01 lands; only the key source and issuer config do. Mint one via
`POST /dev/token` (disabled automatically once `ELOG_AUTH_STUB_ENABLED=false`):

```bash
curl localhost:8000/api/v1/health

# mint a token for a role, then use it like any bearer token
TOKEN=$(curl -s -X POST -H "Content-Type: application/json" \
  -d '{"username":"jane.operator","groups":["OLNG-ELOG-OPERATORS"]}' \
  localhost:8000/api/v1/dev/token | python -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")

curl -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/me
curl -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/shifts/current
```

In Swagger (`/docs`): call `POST /dev/token` with a `username` and one or more of the
groups below, copy the returned `access_token`, then paste `Bearer <token>` into the
**Authorize** button. Valid groups → role: `OLNG-ELOG-OPERATORS` (operator),
`OLNG-ELOG-SUPERVISORS` (supervisor), `OLNG-ELOG-SUPERINTENDENTS` (management),
`OLNG-ELOG-ADMINS` (administrator, all permissions), `OLNG-ELOG-SUPERUSERS` (super user).

**Roles, permissions and AD-group mapping are real data**, not a hardcoded table — see
"Roles & RBAC" below. `/dev/token` validates the `groups` you pass against whatever is
actually in the `roles` table, so a custom role's AD group works here too.

**A validly-signed token whose AD groups match no role is refused (401), not admitted
with no permissions.** There is no local-credential fallback anywhere in this path — a
bearer token verified against the configured issuer is the only way in. `/dev/token`
itself still rejects unknown groups at mint time (422); this is the second, independent
check that also protects the live AD FS path once A-01 lands.

**Every sign-in attempt is written to the audit trail** — success and every denial
(missing/malformed header, invalid token, unmapped groups) — through the same
hash-chained audit mechanism used for pending-action and role mutations. Under
`ELOG_PERSISTENCE_BACKEND=memory` this is a no-op recorder (nothing to persist to);
under `sql` it's a real `auth.signin.success` / `auth.signin.denied` row in `audit_log`.

## Implemented so far

| Endpoint | Status |
|---|---|
| `GET /api/v1/health`, `/ready` | ✅ working |
| `POST /api/v1/dev/token` | ✅ working (stub-mode only — mints a signed dev JWT) |
| `GET /api/v1/me` | ✅ working (real JWT validation, roles/permissions/area-scope from `roles` table) |
| `GET /api/v1/shifts/current` | ✅ working |
| `GET /api/v1/shifts/{id}` | stub — persistence TODO |
| `GET /api/v1/pending-actions` (list + filters) | ✅ working (in-memory or SQL, area-scope filtered) |
| `GET /api/v1/pending-actions/{id}` | ✅ working (area-scope filtered) |
| `POST /api/v1/pending-actions` (capture) | ✅ working (audited) |
| `PATCH /api/v1/pending-actions/{id}/transition` | ✅ working (lifecycle, workflow-gated, audited) |
| `GET/POST/PATCH/DELETE /api/v1/admin/roles` | ✅ working (custom roles, audited, admin-only) |
| `GET /api/v1/admin/config/shift`, `/shift/versions` | ✅ working (ES-308, admin-only) |
| `POST /api/v1/admin/config/shift` | ✅ working (append-only, effective-dated, optimistic concurrency — ES-308) |
| `GET /api/v1/admin/config/shift/history` | ✅ working (audit trail of config changes — ES-311, admin-only) |
| summaries · notifications · super-user | scaffolded, endpoints TODO |

Cross-cutting foundations in place: the unified response envelope, error→status mapping,
correlation-ID middleware, structured logging, token validation + RBAC dependency, and
the repository pattern with dependency injection. Adapters for Valkey, ai-service and SMTP
are scaffolded and stubbed.

**Shift resolution is a shared contract (ES-310).** `resolve_current_shift()`
(`src/application/shifts/current_shift.py`) is the one place "what shift covers this
moment" is computed — `GET /shifts/current` calls it, and it is the entry point any
future consumer (shift summaries, scheduled reports) must also call rather than
re-deriving shift windows independently, so every part of the system stays consistent
with whatever the shift configuration currently says. Don't call the similarly-named
`get_current_shift()` in the same module instead — it's a bootstrap-only fallback that
reads static `Settings` and never looks at the persisted configuration at all.

**Persistence is real.** The pending-action repository has both a **working in-memory
adapter** (default, no server) and a **SQLAlchemy 2.0 async adapter** behind the same
port — MS SQL via `aioodbc` in the deployed environments, SQLite via `aiosqlite` for
local/CI — selected by `ELOG_PERSISTENCE_BACKEND`. Every mutation runs inside a **unit of
work** that writes a **hash-chained audit entry in the same transaction** as the change,
so the action and its audit row commit atomically. The production schema is a versioned
T-SQL migration (`migrations/0001_init.sql`) with RCSI and an append-only Ledger `audit_log`;
`src/infrastructure/persistence/tables.py` mirrors it for local bootstrap.

```bash
# run the app against local async SQLite instead of the in-memory store
ELOG_PERSISTENCE_BACKEND=sql \
ELOG_DATABASE_URL=sqlite+aiosqlite:///./elogbook_local.db \
ELOG_DB_CREATE_ALL=true uvicorn src.main:app --reload
```

For the MS SQL driver, install the extra: `pip install -e ".[mssql]"` (needs ODBC Driver 18).

### Roles & RBAC

Roles — which AD group maps to which role, what permissions each grants, and an
optional area restriction — are **real rows in the `roles` table**
(`migrations/0002_roles.sql`), not a hardcoded dictionary. Five **base** roles ship as
fixed platform data (Operator, Supervisor, Management, Administrator, Super User); an
Administrator creates additional **custom** roles through the admin API. Base roles
cannot be edited or deleted through the API.

```bash
# create a custom, area-restricted role (needs an OLNG-ELOG-ADMINS token)
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
     -d '{"name":"train1_operator","permissions":["action:read","action:write"],
          "ad_groups":["OLNG-ELOG-TRAIN1"],"area_scope":["Train 1"]}' \
     localhost:8000/api/v1/admin/roles
```

A role with `area_scope` set only sees pending actions in those areas (`GET
/pending-actions` and `GET /pending-actions/{id}`); a role with `area_scope: null`
(every base role, by default) sees the full plant. Every role create/update/delete is
written to the same hash-chained audit trail as pending-actions.

Token validation resolves a user's roles, permissions and area scope from this table on
every request (`src/infrastructure/auth/token_validator.py`) — swapping the in-memory
default for MS SQL is the same `ELOG_PERSISTENCE_BACKEND=sql` switch used for
pending-actions.

### The pending-action lifecycle

`Open → In Progress → On Hold → Completed → Verified`, with `Cancelled` reachable from
any non-terminal state. The state machine is pure domain (`src/domain/pending_actions/`)
and unit-tested; an illegal transition returns **409** in the standard error shape.
Assignment and lifecycle tracking are gated behind the Admin-toggled action workflow
(`ELOG_ACTION_WORKFLOW_ENABLED`, BRD FR-PA-05).

```bash
# capture (workflow off — capture only); $TOKEN minted as shown above
curl -X POST -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"issue":"Inspect PSV on V-101","priority":"High"}' \
     localhost:8000/api/v1/pending-actions
```

## Tests

```bash
pytest --cov=src
```

- `tests/contract/` — response-envelope shape (success + error)
- `tests/unit/` — the pending-action state machine, the audit hash-chain primitives, and
  JWT token validation incl. role/permission/area-scope resolution — all pure, no I/O
- `tests/integration/` — the pending-actions API end-to-end (in-memory) incl. area-scope
  filtering, the admin roles API, the dev token-issuance endpoint, and the SQL adapters
  (pending-actions + roles) + audit chain + transaction atomicity against async SQLite

`tests/conftest.py` pins the test run to the in-memory backend regardless of a local
`.env` (a developer's `.env` may point at a real MS SQL database for manual testing —
tests must never depend on or mutate that data).

The SQLAlchemy async stack needs greenlet's compiled extension (VC++ runtime); the SQL
tests skip automatically on a box without it and run in CI.

## Dependency status

See the platform **Outstanding Items Tracker**. Nothing blocks backend development: MS
SQL, AD FS, `ai-service` and SMTP are each stubbed behind the same contract and swapped
for the real OLNG dependency without changing calling code.
