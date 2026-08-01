/* ============================================================================
 * Migration 0003 — shift configurations (US-008, EP-04, ES-308/309/310/311)
 * Engine: Microsoft SQL Server (target: OLNG-managed instance, A-04)
 * Forward-only. Rollback: 0003_shift_configurations.rollback.sql
 *
 * Append-only and effective-dated: a shift-configuration change INSERTs a new version
 * row, it never UPDATEs one in place — correct historical resolution "for free" plus an
 * immutable, audit-friendly change history. area is nullable: NULL = plant-wide; an
 * area-specific row overrides the plant-wide row for that area when resolving (see
 * src/domain/shifts/entities.py: ShiftConfiguration.effective_for). The SQLAlchemy
 * metadata in src/infrastructure/persistence/tables.py mirrors this for local/CI
 * bootstrap (ELOG_DB_CREATE_ALL).
 * ============================================================================ */

-- Required by SQL Server for filtered indexes (used below for the two partial unique
-- indexes) — must be ON for the session that creates them.
SET QUOTED_IDENTIFIER ON;
GO

CREATE TABLE dbo.shift_configurations (
    id              NVARCHAR(32)      NOT NULL CONSTRAINT PK_shift_configurations PRIMARY KEY,
    area            NVARCHAR(128)     NULL,       -- NULL = plant-wide
    start_hour      INT               NOT NULL,
    hours           INT               NOT NULL,
    overlap_minutes INT               NOT NULL,
    effective_from  DATETIMEOFFSET(7) NOT NULL,
    version         INT               NOT NULL,
    created_by      NVARCHAR(128)     NOT NULL,
    created_at      DATETIMEOFFSET(7) NOT NULL,
    updated_at      DATETIMEOFFSET(7) NOT NULL
);
GO

CREATE INDEX IX_shift_configurations_area_effective ON dbo.shift_configurations (area, effective_from);
GO

/* Backs the optimistic-concurrency check in create_shift_configuration() with real DB
 * constraints (see src/infrastructure/persistence/tables.py for the full rationale: a
 * plain composite UNIQUE(area, version) does not reliably catch two racing inserts on a
 * nullable area column, verified empirically to let duplicates through on SQLite). Two
 * filtered unique indexes instead: area-specific rows unique per (area, version);
 * plant-wide rows (area IS NULL) unique per version alone.
 */
CREATE UNIQUE INDEX UQ_shift_configurations_area_version
    ON dbo.shift_configurations (area, version)
    WHERE area IS NOT NULL;
GO

CREATE UNIQUE INDEX UQ_shift_configurations_plant_version
    ON dbo.shift_configurations (version)
    WHERE area IS NULL;
GO

/* --- Seed: one plant-wide configuration, effective since the epoch ---------------
 * Mirrors src/infrastructure/persistence/in_memory_shift_config.py's bootstrap seed and
 * the Settings defaults (shift_start_hour=6, shift_hours=12, shift_overlap_minutes=15).
 * effective_from is pinned to 1900-01-01 so this row is always the fallback until an
 * Administrator posts a real change.
 */
INSERT INTO dbo.shift_configurations (id, area, start_hour, hours, overlap_minutes, effective_from, version, created_by, created_at, updated_at)
VALUES
    ('3cf0a4602d1f49f8b79d20c995062aa2', NULL, 6, 12, 15, '1900-01-01T00:00:00+00:00', 1, 'system', SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET());
GO
