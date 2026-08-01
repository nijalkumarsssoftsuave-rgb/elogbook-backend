/* ============================================================================
 * Migration 0001 — initial E-Logbook schema (elogbook_app)
 * Engine: Microsoft SQL Server (target: OLNG-managed instance, A-04)
 * Forward-only. Rollback: 0001_init.rollback.sql
 *
 * This is the source of truth for the PRODUCTION schema. The SQLAlchemy metadata in
 * src/infrastructure/persistence/tables.py mirrors these tables for local/CI bootstrap
 * (ELOG_DB_CREATE_ALL) but does NOT set the two MS SQL-specific guarantees below —
 * Read-Committed Snapshot Isolation and the append-only Ledger — which are applied here.
 * ============================================================================ */

/* --- Read-Committed Snapshot Isolation -------------------------------------------
 * Non-blocking reads under the high-concurrency write path (risk FN-03). Applied at
 * database provisioning, when no other sessions are connected; kept here for the record.
 * Run separately from the table DDL below.
 *
 *   ALTER DATABASE elogbook_app SET READ_COMMITTED_SNAPSHOT ON WITH ROLLBACK IMMEDIATE;
 *   ALTER DATABASE elogbook_app SET ALLOW_SNAPSHOT_ISOLATION ON;
 */

/* --- Pending actions (BRD FR-PA-03) --------------------------------------------- */
CREATE TABLE dbo.pending_actions (
    id          CHAR(32)          NOT NULL CONSTRAINT PK_pending_actions PRIMARY KEY,
    issue       NVARCHAR(MAX)     NOT NULL,
    priority    NVARCHAR(10)      NOT NULL,
    status      NVARCHAR(20)      NOT NULL,
    source      NVARCHAR(10)      NOT NULL,
    area        NVARCHAR(128)     NULL,
    equipment   NVARCHAR(128)     NULL,
    [owner]     NVARCHAR(128)     NULL,
    due_date    DATE              NULL,
    created_at  DATETIMEOFFSET(7) NOT NULL,
    updated_at  DATETIMEOFFSET(7) NOT NULL
);
GO

CREATE INDEX IX_pending_actions_status    ON dbo.pending_actions (status);
CREATE INDEX IX_pending_actions_owner     ON dbo.pending_actions ([owner]);
CREATE INDEX IX_pending_actions_area      ON dbo.pending_actions (area);
CREATE INDEX IX_pending_actions_equipment ON dbo.pending_actions (equipment);
GO

/* --- Hash-chained audit trail ----------------------------------------------------
 * Append-only Ledger: the engine itself forbids UPDATE/DELETE and cryptographically
 * seals the table's history — a second guarantee on top of the application-computed
 * SHA-256 chain (prev_hash -> entry_hash). Written in the same transaction as the
 * mutation it records.
 */
CREATE TABLE dbo.audit_log (
    seq          BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_audit_log PRIMARY KEY,
    event_id     CHAR(32)          NOT NULL CONSTRAINT UQ_audit_log_event UNIQUE,
    occurred_at  DATETIMEOFFSET(7) NOT NULL,
    actor        NVARCHAR(128)     NOT NULL,
    [action]     NVARCHAR(64)      NOT NULL,
    entity_type  NVARCHAR(64)      NOT NULL,
    entity_id    NVARCHAR(64)      NOT NULL,
    payload      NVARCHAR(MAX)     NOT NULL,
    prev_hash    CHAR(64)          NOT NULL,
    entry_hash   CHAR(64)          NOT NULL CONSTRAINT UQ_audit_log_hash UNIQUE
)
WITH (LEDGER = ON (APPEND_ONLY = ON));
GO

CREATE INDEX IX_audit_log_entity ON dbo.audit_log (entity_id);
GO
