# Migrations

Versioned, **forward-only** schema changes for the `elogbook_app` database
(Engineering Code Standards, discipline 7: versioned migrations with a defined rollback
path). The SQL here is the **source of truth for the production schema**.

## Files

| File | Purpose |
|---|---|
| `NNNN_<name>.sql` | The forward migration (applied in order). |
| `NNNN_<name>.rollback.sql` | The matching rollback. |

`0001_init.sql` — the initial schema: `pending_actions` and the append-only, hash-chained
`audit_log`. It also documents the database-level settings (RCSI, snapshot isolation)
applied at provisioning.

`0002_roles.sql` — the `roles` table (base + admin-defined custom roles), replacing the
previously hardcoded AD-group -> role -> permission mapping with real, admin-manageable
rows. Seeds the five base roles so behaviour is unchanged until an Admin adds a custom
one via `/admin/roles`.

`0003_notifications.sql` — the `notifications` table (ES-355): one row per
(recipient, channel) alert fired, e.g. by `scripts/sweep_overdue_actions.py` alerting an
overdue action's owner in-app and by email.

## Applying

**Production / dev (MS SQL, A-04):** apply each forward migration in filename order with
`sqlcmd` (the `GO` batch separators are honoured):

```bash
sqlcmd -S <host> -d elogbook_app -U <user> -P <pw> -b -i migrations/0001_init.sql
```

Migrations run through GitOps/CI against the OLNG-managed instance — never by editing the
schema by hand. RCSI and snapshot isolation are set once at database provisioning (see the
commented `ALTER DATABASE` block in `0001_init.sql`), when no other sessions are connected.

**Local / CI without a SQL Server:** you don't need these files. Set
`ELOG_PERSISTENCE_BACKEND=sql`, point `ELOG_DATABASE_URL` at
`sqlite+aiosqlite:///./elogbook_local.db`, and set `ELOG_DB_CREATE_ALL=true` — the app
creates the same tables from the SQLAlchemy metadata on startup. The metadata mirrors
this DDL; the MS SQL-only guarantees (Ledger, RCSI) are simply not present on SQLite.

## Conventions

- One concern per migration; never edit a migration that has been applied — add the next one.
- Every forward file has a rollback file that reverses exactly it.
- Keep the metadata in `src/infrastructure/persistence/tables.py` in step with the latest
  migration so local bootstrap and production stay aligned.
