/* ============================================================================
 * Rollback for migration 0001 — drop the initial E-Logbook schema.
 * Note: dropping an append-only Ledger table removes it and its ledger history; only
 * run this against a non-production database.
 * ============================================================================ */
IF OBJECT_ID('dbo.audit_log', 'U')       IS NOT NULL DROP TABLE dbo.audit_log;
GO
IF OBJECT_ID('dbo.pending_actions', 'U') IS NOT NULL DROP TABLE dbo.pending_actions;
GO
