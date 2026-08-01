"""Overdue sweep — detect overdue actions and alert their owners (ES-353, ES-355).

Meant to be run on a schedule by something OUTSIDE this process — an OS-level cron job,
Windows Task Scheduler, or a Kubernetes CronJob — not an in-process timer. Deliberately:
an in-process scheduler runs once per API replica, so scaling the API to more than one
instance would fire the sweep multiple times per tick and there's no coordination here
to prevent that. A standalone script invoked externally keeps "one sweep per schedule
tick" true regardless of how many API replicas are running.

Usage (PowerShell):

    .\\.venv\\Scripts\\python.exe scripts\\sweep_overdue_actions.py

Example cron entry (Linux, hourly):

    0 * * * *  cd /path/to/elogbook-backend && .venv/bin/python scripts/sweep_overdue_actions.py

For every overdue action found: logs it (WARNING level, so it's visible by default
logging config), and — if it has an owner — alerts them in-app and by email (ES-355;
see ``application/notifications/alert_owner.py``). ``alert_owner`` is idempotent (a
sweep re-run while the same action stays overdue does not re-alert), so this script is
safe to re-run on every schedule tick indefinitely, same as the original detect-only
version was.

Each action's alert commits in its own transaction, independently of every other
action in the same run (found in code review: a single shared transaction meant one
failure silently rolled back every already-processed owner's alert in the same batch).
A failure alerting one action is logged and the sweep moves on to the rest — it always
exits 0; an alerting failure is not a sweep failure.
"""

import asyncio

from src.application.notifications.alert_owner import alert_owner
from src.application.pending_actions.overdue_sweep import find_overdue_actions
from src.core.config import settings
from src.core.logging import configure_logging, get_logger
from src.infrastructure.notifications.email import get_email_sender

logger = get_logger(__name__)


async def main() -> None:
    configure_logging("INFO")

    if settings.persistence_backend != "sql":
        logger.info(
            "Overdue sweep: persistence_backend is 'memory' — nothing persists across "
            "process runs, so there is nothing meaningful to sweep. Set "
            "ELOG_PERSISTENCE_BACKEND=sql to run this for real."
        )
        return

    from src.infrastructure.persistence.database import dispose_engine, get_sessionmaker
    from src.infrastructure.persistence.sql_notifications import SqlNotificationRepository
    from src.infrastructure.persistence.sql_pending_actions import SqlPendingActionRepository

    email_sender = get_email_sender(settings)
    sessionmaker = get_sessionmaker()

    async with sessionmaker() as session:
        overdue = await find_overdue_actions(SqlPendingActionRepository(session))

    if not overdue:
        logger.info("Overdue sweep: no overdue actions found.")
        await dispose_engine()
        return

    owners_alerted: set[str] = set()
    for action in overdue:
        logger.warning(
            f"Overdue: {action.id} '{action.issue}' due {action.due_date} "
            f"(status={action.status.value}, owner={action.owner or 'unassigned'}, "
            f"area={action.area or 'n/a'})"
        )
        if not action.owner:
            continue
        try:
            async with sessionmaker() as session:
                sent = await alert_owner(action, SqlNotificationRepository(session), email_sender)
                await session.commit()
            if sent:
                owners_alerted.add(action.owner)
        except Exception:
            logger.exception(f"Overdue sweep: failed to alert owner for action {action.id}")

    await dispose_engine()
    logger.info(
        f"Overdue sweep: {len(overdue)} action(s) past due date, "
        f"{len(owners_alerted)} distinct owner(s) alerted."
    )


if __name__ == "__main__":
    asyncio.run(main())
