/* ============================================================================
 * Migration 0003 — notifications (ES-355)
 * Engine: Microsoft SQL Server (target: OLNG-managed instance, A-04)
 * Forward-only. Rollback: 0003_notifications.rollback.sql
 *
 * One row per (recipient, channel) alert fired — e.g. the overdue-sweep script
 * (scripts/sweep_overdue_actions.py) writes both an "in_app" and an "email" row per
 * owner it alerts. "in_app" rows are the notification itself (no separate delivery
 * step — GET /notifications reads them back); "email" rows are a record that the
 * email was sent, not the email's own transport.
 * ============================================================================ */

CREATE TABLE dbo.notifications (
    id                  CHAR(32)          NOT NULL CONSTRAINT PK_notifications PRIMARY KEY,
    recipient           NVARCHAR(128)     NOT NULL,
    channel             NVARCHAR(10)      NOT NULL,
    subject             NVARCHAR(256)     NOT NULL,
    message             NVARCHAR(MAX)     NOT NULL,
    related_entity_type NVARCHAR(64)      NULL,
    related_entity_id   NVARCHAR(64)      NULL,
    [read]              BIT               NOT NULL,
    created_at          DATETIMEOFFSET(7) NOT NULL
);
GO

CREATE INDEX IX_notifications_recipient ON dbo.notifications (recipient);
GO

CREATE INDEX IX_notifications_related_entity ON dbo.notifications (related_entity_id);
GO
