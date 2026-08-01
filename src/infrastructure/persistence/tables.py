"""SQLAlchemy table definitions — the single, portable schema.

Core ``Table`` objects (not the ORM) keep the mapping explicit and dialect-portable:
the same definitions run on **MS SQL** (``mssql+aioodbc``) in the deployed environments
and on **SQLite** (``sqlite+aiosqlite``) for local/CI runs. ``String``/``Text`` render as
``NVARCHAR`` on MS SQL and ``VARCHAR``/``TEXT`` on SQLite automatically.

MS SQL-specific hardening — Read-Committed Snapshot Isolation and the append-only
**Ledger** guarantee on ``audit_log`` — lives in the T-SQL migration
(``migrations/0001_init.sql``), which is the source of truth for the production schema.
This metadata mirrors it so a developer can bootstrap the same tables locally with
``create_all`` (``ELOG_DB_CREATE_ALL=true``); production always applies the migrations.
"""

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)

metadata = MetaData()

# --- roles (base + admin-defined custom) -------------------------------------------
# permissions / ad_groups / area_scope are stored as canonical JSON text — a handful of
# rows, read in full on every token validation, so no join table or SQL-side JSON
# querying is needed; the repository does the filtering in Python.
roles = Table(
    "roles",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("name", String(64), nullable=False, unique=True),
    Column("is_custom", Boolean, nullable=False),
    Column("permissions", Text, nullable=False),  # JSON array of permission strings
    Column("ad_groups", Text, nullable=False),  # JSON array of AD group names
    Column("area_scope", Text, nullable=True),  # JSON array, or NULL = full plant
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

# --- users (admin-managed; optional role override) ---------------------------------
users = Table(
    "users",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("username", String(128), nullable=False, unique=True),  # AD sAMAccountName, lowercase
    Column("display_name", String(256), nullable=False),
    Column("email", String(256), nullable=False),
    Column("is_active", Boolean, nullable=False),
    Column("role_id", String(32), ForeignKey("roles.id"), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

# --- pending actions (BRD FR-PA-03) -----------------------------------------------
pending_actions = Table(
    "pending_actions",
    metadata,
    Column("id", String(32), primary_key=True),  # uuid4 hex
    Column("issue", Text, nullable=False),
    Column("priority", String(10), nullable=False),
    Column("status", String(20), nullable=False, index=True),
    Column("source", String(10), nullable=False),
    Column("area", String(128), nullable=True, index=True),
    Column("equipment", String(128), nullable=True, index=True),
    Column("owner", String(128), nullable=True, index=True),
    Column("due_date", Date, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

# --- hash-chained audit trail -----------------------------------------------------
# Append-only and tamper-evident: each row carries the SHA-256 of (previous hash +
# canonical row content), so any later edit breaks the chain. In production this table
# is additionally an MS SQL append-only Ledger table (see the migration) — defence in
# depth on top of the application-computed chain.
audit_log = Table(
    "audit_log",
    metadata,
    Column("seq", Integer, primary_key=True, autoincrement=True),  # chain order
    Column("event_id", String(32), nullable=False, unique=True),  # uuid4 hex
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("actor", String(128), nullable=False),  # username
    Column("action", String(64), nullable=False),  # e.g. pending_action.create
    Column("entity_type", String(64), nullable=False),
    Column("entity_id", String(64), nullable=False, index=True),
    Column("payload", Text, nullable=False),  # canonical JSON snapshot
    Column("prev_hash", String(64), nullable=False),
    Column("entry_hash", String(64), nullable=False, unique=True),
)
