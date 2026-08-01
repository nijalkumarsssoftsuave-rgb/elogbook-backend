"""Smoke test: write and read a pending action through the app's real SQL path.

Run this AFTER pointing the app at a live database. It uses the exact production code —
the SQLAlchemy engine (built from ELOG_DATABASE_URL), the unit of work, the pending-action
repository and the hash-chained audit writer — so a green run proves the whole persistence
+ audit stack works against whatever database ELOG_DATABASE_URL points at (MS SQL here).

Usage (PowerShell, from d:\elogbook\elogbook-backend):

    $env:ELOG_PERSISTENCE_BACKEND = "sql"
    # ELOG_DATABASE_URL defaults to the local MS SQL container; override if needed.
    .\.venv\Scripts\python.exe scripts\smoke_mssql.py

It does NOT create tables — apply migrations/0001_init.sql first (or set
ELOG_DB_CREATE_ALL=true to bootstrap from metadata).
"""
import asyncio

from src.application.pending_actions.create_action import capture_action
from src.application.pending_actions.list_actions import get_action
from src.core.config import settings
from src.domain.pending_actions.entities import Priority, Source
from src.infrastructure.audit.audit_writer import verify_chain
from src.infrastructure.persistence.database import dispose_engine, get_sessionmaker, healthcheck
from src.infrastructure.persistence.tables import audit_log, pending_actions
from src.infrastructure.persistence.unit_of_work import SqlUnitOfWork


async def main() -> None:
    print(f"backend   : {settings.persistence_backend}")
    print(f"database  : {settings.database_url.split('://', 1)[0]}://... (host in URL)")

    if not await healthcheck():
        print("\nFAIL: database is not reachable (SELECT 1 failed).")
        print("Is the server up and the URL correct?")
        return
    print("reachable : yes (SELECT 1 ok)\n")

    sm = get_sessionmaker()

    # 1) write a row + its audit entry, in one transaction
    async with SqlUnitOfWork(sm) as uow:
        created = await capture_action(
            uow.actions,
            issue="SMOKE TEST — inspect PSV on V-101",
            priority=Priority.HIGH,
            source=Source.MANUAL,
            audit=uow.audit,
            actor="smoke.test",
        )
    print(f"wrote     : pending action {created.id} ({created.status.value})")

    # 2) read it back from a fresh transaction (proves it was really committed)
    async with SqlUnitOfWork(sm) as uow:
        fetched = await get_action(uow.actions, created.id)
    print(f"read back : {'OK — ' + fetched.issue if fetched else 'FAIL — not found'}")

    # 3) count rows + verify the audit chain is intact
    async with sm() as s:
        pa = (await s.execute(pending_actions.select())).all()
        al = (await s.execute(audit_log.select())).all()
        chain_ok = await verify_chain(s)
    print(f"rows      : pending_actions={len(pa)}  audit_log={len(al)}")
    print(f"audit     : chain intact = {chain_ok}")

    await dispose_engine()
    if fetched and chain_ok:
        print("\nPASS — the app read and wrote real rows through the SQL backend.")
    else:
        print("\nFAIL — see above.")


if __name__ == "__main__":
    asyncio.run(main())
