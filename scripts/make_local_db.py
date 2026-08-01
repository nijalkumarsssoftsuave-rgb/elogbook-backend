"""Build a local SQLite database with the E-Logbook tables + sample data, for viewing in DBeaver.

Self-contained: it points the app at a local SQLite FILE and writes through the exact
production code path (same tables, repository, unit of work and hash-chained audit writer
as MS SQL uses). No database server needed — SQLite is a single file DBeaver opens directly.

Run (from d:\elogbook\elogbook-backend):
    .\.venv\Scripts\python.exe scripts\make_local_db.py

Re-running recreates the sample rows in the same file.
"""
import asyncio
import os
from pathlib import Path

# Point the app at a local SQLite file BEFORE importing app config (settings read env at import).
DB_PATH = Path(__file__).resolve().parent.parent / "local_data" / "elogbook_demo.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
os.environ["ELOG_PERSISTENCE_BACKEND"] = "sql"
os.environ["ELOG_DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"

from src.application.pending_actions.create_action import capture_action  # noqa: E402
from src.application.pending_actions.transition_action import transition_action  # noqa: E402
from src.domain.pending_actions.entities import (  # noqa: E402
    PendingActionStatus,
    Priority,
    Source,
)
from src.infrastructure.audit.audit_writer import verify_chain  # noqa: E402
from src.infrastructure.persistence.database import (  # noqa: E402
    dispose_engine,
    get_sessionmaker,
    init_models,
)
from src.infrastructure.persistence.tables import audit_log, pending_actions  # noqa: E402
from src.infrastructure.persistence.unit_of_work import SqlUnitOfWork  # noqa: E402

SAMPLES = [
    ("Inspect PSV on V-101 before startup", Priority.HIGH, "Train 1", "V-101", "jane.operator"),
    ("Replace worn gasket on P-204 seal", Priority.MEDIUM, "Utilities", "P-204", "sam.super"),
    ("Calibration due for TT-330", Priority.LOW, "Storage & Loading", "TT-330", "mo.super"),
]


async def main() -> None:
    await init_models()  # create pending_actions + audit_log from metadata
    sm = get_sessionmaker()

    ids = []
    for issue, prio, area, equip, actor in SAMPLES:
        async with SqlUnitOfWork(sm) as uow:
            a = await capture_action(
                uow.actions, issue=issue, priority=prio, source=Source.MANUAL,
                area=area, equipment=equip, audit=uow.audit, actor=actor,
            )
            ids.append(a.id)

    # progress one action so the audit trail also shows a lifecycle transition
    async with SqlUnitOfWork(sm) as uow:
        await transition_action(
            uow.actions, ids[0], PendingActionStatus.IN_PROGRESS,
            audit=uow.audit, actor="jane.operator",
        )

    async with sm() as s:
        pa = (await s.execute(pending_actions.select())).all()
        al = (await s.execute(audit_log.select())).all()
        chain_ok = await verify_chain(s)

    await dispose_engine()

    print(f"database : {DB_PATH}")
    print(f"tables   : pending_actions ({len(pa)} rows), audit_log ({len(al)} rows)")
    print(f"audit    : chain intact = {chain_ok}")
    print("\nOpen this file in DBeaver as a SQLite connection to browse the tables.")


if __name__ == "__main__":
    asyncio.run(main())
