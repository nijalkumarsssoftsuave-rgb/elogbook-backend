"""Overdue sweep — detect pending actions past their due date (ES-353).

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

Detection only — this logs what it finds (WARNING level, so it's visible by default
logging config) and exits 0 whether or not anything is overdue; finding overdue actions
is the expected, useful outcome of a sweep, not a script failure. It does not send
notifications — the notifications feature (src/infrastructure/notifications/) isn't
built yet; wiring this sweep to it is a follow-up, not part of "detect."
"""

import asyncio

from src.application.pending_actions.overdue_sweep import find_overdue_actions
from src.core.config import settings
from src.core.logging import configure_logging, get_logger

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
    from src.infrastructure.persistence.sql_pending_actions import SqlPendingActionRepository

    async with get_sessionmaker()() as session:
        overdue = await find_overdue_actions(SqlPendingActionRepository(session))
    await dispose_engine()

    if not overdue:
        logger.info("Overdue sweep: no overdue actions found.")
        return

    for action in overdue:
        logger.warning(
            f"Overdue: {action.id} '{action.issue}' due {action.due_date} "
            f"(status={action.status.value}, owner={action.owner or 'unassigned'}, "
            f"area={action.area or 'n/a'})"
        )
    logger.info(f"Overdue sweep: {len(overdue)} action(s) past due date.")


if __name__ == "__main__":
    asyncio.run(main())
