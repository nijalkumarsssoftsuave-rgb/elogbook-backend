/* ============================================================================
 * Migration 0003 — users (admin-managed, optional role override)
 * Engine: Microsoft SQL Server (target: OLNG-managed instance, A-04)
 * Forward-only. Rollback: 0003_users.rollback.sql
 *
 * ES-358: An Administrator can provision user records and optionally assign a
 * manual role override (role_id). When role_id IS NULL the user's role is
 * derived from their AD groups at token validation time as normal; a non-NULL
 * role_id takes precedence over AD-group-based resolution.
 *
 * The SQLAlchemy metadata in src/infrastructure/persistence/tables.py mirrors
 * this table for local/CI bootstrap (ELOG_DB_CREATE_ALL).
 * ============================================================================ */

CREATE TABLE dbo.users (
    id           NVARCHAR(32)      NOT NULL CONSTRAINT PK_users PRIMARY KEY,
    username     NVARCHAR(128)     NOT NULL CONSTRAINT UQ_users_username UNIQUE,
    display_name NVARCHAR(256)     NOT NULL,
    email        NVARCHAR(256)     NOT NULL,
    is_active    BIT               NOT NULL CONSTRAINT DF_users_is_active DEFAULT 1,
    role_id      NVARCHAR(32)      NULL
                     CONSTRAINT FK_users_role FOREIGN KEY REFERENCES dbo.roles(id),
    created_at   DATETIMEOFFSET(7) NOT NULL,
    updated_at   DATETIMEOFFSET(7) NOT NULL
);
GO

/* Optional performance index for username lookups (used by get_by_username). */
CREATE INDEX IX_users_username ON dbo.users (username);
GO
