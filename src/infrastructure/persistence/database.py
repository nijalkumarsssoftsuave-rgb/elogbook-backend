"""Async database engine and session factory.

SQLAlchemy 2.0 async. The engine URL comes from configuration, so the runtime target —
MS SQL via ``aioodbc`` in the deployed environments, SQLite via ``aiosqlite`` for a
laptop/CI run — is a setting, not a code change (Outstanding Items Tracker A-04).

Engine and sessionmaker are process singletons built lazily on first use. Tests build
their own engine against an in-memory SQLite and inject its sessionmaker into the unit
of work, so nothing here needs a live server.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import settings
from src.infrastructure.persistence.tables import metadata

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker | None = None


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, creating it on first use.

    A stalled MS SQL connection (server unreachable, auth negotiation stuck) has no
    driver-level timeout by default, so a bad connection hangs the request forever
    instead of failing — and since nothing cancels the server-side task when a client
    gives up waiting, each hang permanently occupies a pool slot until every DB-backed
    endpoint is starved. ``connect_args={"timeout": ...}`` bounds the login attempt;
    ``pool_timeout`` bounds how long a request waits for a pooled connection.
    """
    global _engine
    if _engine is None:
        extra: dict = {}
        if settings.database_url.startswith("mssql"):
            # SQLite/StaticPool (local + test) don't accept pool_timeout — it's a
            # QueuePool-only option, so this is scoped to the real MS SQL dialect.
            extra = {"connect_args": {"timeout": 10}, "pool_timeout": 10}
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.db_echo,
            pool_pre_ping=True,
            future=True,
            **extra,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker:
    """Return the async session factory bound to the engine."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


async def init_models() -> None:
    """Create tables from metadata — **local/CI bootstrap only**.

    Production applies the versioned SQL migrations (``migrations/``), which additionally
    set RCSI and the append-only Ledger guarantee. This path is gated behind
    ``ELOG_DB_CREATE_ALL`` so it never runs against a managed instance.
    """
    async with get_engine().begin() as conn:
        await conn.run_sync(metadata.create_all)


async def dispose_engine() -> None:
    """Dispose the engine and reset the singletons (shutdown / test teardown)."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def healthcheck() -> bool:
    """True when the database answers ``SELECT 1``."""
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
