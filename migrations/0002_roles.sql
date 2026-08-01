/* ============================================================================
 * Migration 0002 — roles (base + admin-defined custom)
 * Engine: Microsoft SQL Server (target: OLNG-managed instance, A-04)
 * Forward-only. Rollback: 0002_roles.rollback.sql
 *
 * Replaces the previously hardcoded AD-group -> role -> permission mapping with real
 * rows an Administrator can manage via /admin/roles. permissions / ad_groups /
 * area_scope are stored as JSON text — the table holds a handful of rows (read in full
 * on every token validation), so no join table or SQL-side JSON querying is needed.
 * The SQLAlchemy metadata in src/infrastructure/persistence/tables.py mirrors this for
 * local/CI bootstrap (ELOG_DB_CREATE_ALL).
 * ============================================================================ */

CREATE TABLE dbo.roles (
    id          NVARCHAR(32)      NOT NULL CONSTRAINT PK_roles PRIMARY KEY,
    name        NVARCHAR(64)      NOT NULL CONSTRAINT UQ_roles_name UNIQUE,
    is_custom   BIT               NOT NULL,
    permissions NVARCHAR(MAX)     NOT NULL,   -- JSON array of permission strings
    ad_groups   NVARCHAR(MAX)     NOT NULL,   -- JSON array of AD group names
    area_scope  NVARCHAR(MAX)     NULL,       -- JSON array, or NULL = full plant
    created_at  DATETIMEOFFSET(7) NOT NULL,
    updated_at  DATETIMEOFFSET(7) NOT NULL
);
GO

/* --- Seed: the five base (system) roles ------------------------------------------
 * Mirrors src/domain/users_roles/seed.py. Fixed platform data — the admin API refuses
 * to edit or delete rows where is_custom = 0.
 */
INSERT INTO dbo.roles (id, name, is_custom, permissions, ad_groups, area_scope, created_at, updated_at)
VALUES
    ('base-operator', 'operator', 0,
     '["shift:read","summary:read","assistant:query","action:read","action:write"]',
     '["OLNG-ELOG-OPERATORS"]', NULL, SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET()),
    ('base-supervisor', 'supervisor', 0,
     '["shift:read","summary:read","summary:comment","assistant:query","action:read","action:write","action:confirm","action:assign","report:read"]',
     '["OLNG-ELOG-SUPERVISORS"]', NULL, SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET()),
    ('base-management', 'management', 0,
     '["shift:read","summary:read","assistant:query","action:read","report:read","analytics:read"]',
     '["OLNG-ELOG-SUPERINTENDENTS"]', NULL, SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET()),
    ('base-administrator', 'administrator', 0,
     '["*"]',
     '["OLNG-ELOG-ADMINS"]', NULL, SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET()),
    ('base-super_user', 'super_user', 0,
     '["dashboard:configure","widget:assign","metric:control","access:control","user:read"]',
     '["OLNG-ELOG-SUPERUSERS"]', NULL, SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET());
GO
