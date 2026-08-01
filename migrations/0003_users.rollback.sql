/* ============================================================================
 * Rollback for migration 0003 — users
 * ============================================================================ */

DROP INDEX IF EXISTS IX_users_username ON dbo.users;
GO

DROP TABLE IF EXISTS dbo.users;
GO
