"""One-shot: create the elogbook_app database + tables + sample data on the local MS SQL.

Targets the native SQL Server 2022 named instance using Windows Authentication over the
local (shared-memory) protocol, so it works even before TCP/IP is enabled. It:
  1. creates the elogbook_app database if it does not exist (via pyodbc on master),
  2. creates the tables from the app's metadata,
  3. seeds sample pending actions through the real use cases + hash-chained audit writer,
so DBeaver has real tables and data to view.

Run (from d:/elogbook/elogbook-backend):
    .venv/Scripts/python.exe scripts/setup_mssql.py
"""
import asyncio
import urllib.parse

import pyodbc
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application.pending_actions.create_action import capture_action
from src.application.pending_actions.transition_action import transition_action
from src.domain.pending_actions.entities import PendingActionStatus, Priority, Source
from src.infrastructure.audit.audit_writer import verify_chain
from src.infrastructure.persistence.tables import audit_log, metadata, pending_actions
from src.infrastructure.persistence.unit_of_work import SqlUnitOfWork

SERVER = r"localhost\MSSQLSERVER01"
DRIVER = "ODBC Driver 18 for SQL Server"
DB = "elogbook_app"


def _odbc(database: str) -> str:
    return (
        f"DRIVER={{{DRIVER}}};SERVER={SERVER};DATABASE={database};"
        "Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes"
    )


SAMPLES = [
    ("Inspect PSV on V-101 before startup", Priority.HIGH, "Train 1", "V-101", "jane.operator"),
    ("Replace worn gasket on P-204 seal", Priority.MEDIUM, "Utilities", "P-204", "sam.super"),
    ("Calibration due for TT-330", Priority.LOW, "Storage & Loading", "TT-330", "mo.super"),
]


def create_database() -> None:
    cn = pyodbc.connect(_odbc("master"), autocommit=True)
    try:
        cn.execute(f"IF DB_ID('{DB}') IS NULL CREATE DATABASE {DB};")
        print(f"database : {DB} ready on {SERVER}")
    finally:
        cn.close()


async def build_and_seed() -> None:
    url = "mssql+aioodbc:///?odbc_connect=" + urllib.parse.quote_plus(_odbc(DB))
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
        print("tables   : pending_actions, audit_log created (or already present)")

        sm = async_sessionmaker(engine, expire_on_commit=False)

        # only seed if empty, so re-runs stay idempotent
        async with sm() as s:
            existing = (await s.execute(pending_actions.select())).all()
        if existing:
            print(f"seed     : skipped — {len(existing)} rows already present")
        else:
            ids = []
            for issue, prio, area, equip, actor in SAMPLES:
                async with SqlUnitOfWork(sm) as uow:
                    a = await capture_action(
                        uow.actions, issue=issue, priority=prio, source=Source.MANUAL,
                        area=area, equipment=equip, audit=uow.audit, actor=actor,
                    )
                    ids.append(a.id)
            async with SqlUnitOfWork(sm) as uow:
                await transition_action(
                    uow.actions, ids[0], PendingActionStatus.IN_PROGRESS,
                    audit=uow.audit, actor="jane.operator",
                )
            print(f"seed     : inserted {len(SAMPLES)} pending actions (+1 transition)")

        async with sm() as s:
            pa = (await s.execute(pending_actions.select())).all()
            al = (await s.execute(audit_log.select())).all()
            chain_ok = await verify_chain(s)
        print(f"rows     : pending_actions={len(pa)}  audit_log={len(al)}")
        print(f"audit    : chain intact = {chain_ok}")
    finally:
        await engine.dispose()


def main() -> None:
    create_database()
    asyncio.run(build_and_seed())
    print("\nDone. In DBeaver, open elogbook_app -> Tables to view pending_actions and audit_log.")


if __name__ == "__main__":
    main()
