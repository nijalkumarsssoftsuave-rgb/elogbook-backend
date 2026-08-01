"""Integration tests for the async engine/session-factory singleton and healthcheck.

Requires the SQLAlchemy async stack (skips otherwise, same guard as the other SQL
integration tests). Previously 0% covered — nothing exercised ``get_engine``,
``get_sessionmaker``, ``dispose_engine`` or ``healthcheck`` directly; the SQL
integration tests build their own engine instead of going through this module.
"""
import pytest

try:
    import aiosqlite  # noqa: F401
    import greenlet  # noqa: F401
    import sqlalchemy  # noqa: F401
except ImportError as exc:  # pragma: no cover - environment-dependent
    pytest.skip(f"SQLAlchemy async stack unavailable: {exc}", allow_module_level=True)

from sqlalchemy import text  # noqa: E402

from src.core.config import settings  # noqa: E402
from src.infrastructure.persistence import database  # noqa: E402


@pytest.fixture(autouse=True)
async def _reset_engine_singleton():
    await database.dispose_engine()
    original_url = settings.database_url
    yield
    await database.dispose_engine()
    settings.database_url = original_url


async def test_get_engine_and_sessionmaker_are_process_singletons():
    settings.database_url = "sqlite+aiosqlite:///:memory:"
    assert database.get_engine() is database.get_engine()
    assert database.get_sessionmaker() is database.get_sessionmaker()


async def test_healthcheck_true_against_a_reachable_database():
    settings.database_url = "sqlite+aiosqlite:///:memory:"
    assert await database.healthcheck() is True


async def test_healthcheck_false_against_an_unreachable_database():
    settings.database_url = "sqlite+aiosqlite:///nonexistent_dir_x/db.sqlite"
    assert await database.healthcheck() is False


async def test_dispose_engine_resets_the_singleton():
    settings.database_url = "sqlite+aiosqlite:///:memory:"
    engine1 = database.get_engine()
    await database.dispose_engine()
    assert database.get_engine() is not engine1


async def test_init_models_creates_tables():
    settings.database_url = "sqlite+aiosqlite:///:memory:"
    await database.init_models()
    async with database.get_engine().connect() as conn:
        result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables = {row[0] for row in result}
    assert "audit_log" in tables
