"""Unit of work — one transaction spanning a mutation and its audit row.

The application's mutating use cases run inside a unit of work so the pending-action
write and its hash-chained audit entry commit together or not at all. Two implementations
back the same shape:

- ``SqlUnitOfWork`` (here) — a real SQLAlchemy transaction (the session is shared by the
  repository and the audit writer, so ``commit`` persists both atomically).
- ``MemoryUnitOfWork`` (``in_memory_uow.py``) — the default local/test backend, kept in a
  SQLAlchemy-free module so ``memory`` mode imports without the SQL driver installed.

Selection is by configuration (``ELOG_PERSISTENCE_BACKEND``); see ``api/deps.py``.
"""

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.audit.recorder import AuditRecorder
from src.application.pending_actions.repository import PendingActionRepository
from src.application.shifts.repository import ShiftConfigRepository
from src.application.users_roles.repository import RoleRepository
from src.infrastructure.audit.audit_writer import SqlAuditWriter
from src.infrastructure.persistence.sql_pending_actions import SqlPendingActionRepository
from src.infrastructure.persistence.sql_roles import SqlRoleRepository
from src.infrastructure.persistence.sql_shift_config import SqlShiftConfigRepository


class PendingActionUnitOfWork(Protocol):
    """The transaction boundary the pending-action use cases run within."""

    actions: PendingActionRepository
    audit: AuditRecorder

    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
    async def close(self) -> None: ...


class SqlUnitOfWork:
    """A single async transaction; repository and audit writer share its session."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self.actions: PendingActionRepository
        self.audit: AuditRecorder

    async def __aenter__(self) -> "SqlUnitOfWork":
        self._session = self._session_factory()  # transaction autobegins on first execute
        self.actions = SqlPendingActionRepository(self._session)
        self.audit = SqlAuditWriter(self._session)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is not None:
                await self.rollback()
            else:
                await self.commit()
        finally:
            await self.close()

    async def commit(self) -> None:
        if self._session is not None:
            await self._session.commit()

    async def rollback(self) -> None:
        if self._session is not None:
            await self._session.rollback()

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None


class ShiftConfigUnitOfWork(Protocol):
    """The transaction boundary the shift-configuration use cases run within (ES-308)."""

    shift_configs: ShiftConfigRepository
    audit: AuditRecorder

    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
    async def close(self) -> None: ...


class SqlShiftConfigUnitOfWork:
    """A single async transaction; repository and audit writer share its session."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self.shift_configs: ShiftConfigRepository
        self.audit: AuditRecorder

    async def __aenter__(self) -> "SqlShiftConfigUnitOfWork":
        self._session = self._session_factory()
        self.shift_configs = SqlShiftConfigRepository(self._session)
        self.audit = SqlAuditWriter(self._session)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is not None:
                await self.rollback()
            else:
                await self.commit()
        finally:
            await self.close()

    async def commit(self) -> None:
        if self._session is not None:
            await self._session.commit()

    async def rollback(self) -> None:
        if self._session is not None:
            await self._session.rollback()

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None


class RoleUnitOfWork(Protocol):
    """The transaction boundary the role-management use cases run within."""

    roles: RoleRepository
    audit: AuditRecorder

    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
    async def close(self) -> None: ...


class SqlRoleUnitOfWork:
    """A single async transaction; repository and audit writer share its session."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self.roles: RoleRepository
        self.audit: AuditRecorder

    async def __aenter__(self) -> "SqlRoleUnitOfWork":
        self._session = self._session_factory()
        self.roles = SqlRoleRepository(self._session)
        self.audit = SqlAuditWriter(self._session)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is not None:
                await self.rollback()
            else:
                await self.commit()
        finally:
            await self.close()

    async def commit(self) -> None:
        if self._session is not None:
            await self._session.commit()

    async def rollback(self) -> None:
        if self._session is not None:
            await self._session.rollback()

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
