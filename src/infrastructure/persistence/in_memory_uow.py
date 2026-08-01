"""In-memory unit of work — the default local/test backend.

Deliberately free of any SQLAlchemy import so ``memory`` mode runs without the SQL
driver installed. Wraps the process-local in-memory repository with a no-op audit
recorder; ``commit``/``rollback`` are no-ops because in-memory writes are immediate.
Matches the ``PendingActionUnitOfWork`` shape structurally, so the API uses one code
path regardless of backend.
"""

from src.application.audit.recorder import AuditRecorder, NullAuditRecorder
from src.application.pending_actions.repository import PendingActionRepository
from src.application.users_roles.repository import RoleRepository


class MemoryUnitOfWork:
    """No-transaction unit of work over the shared in-memory repository."""

    def __init__(self, repository: PendingActionRepository) -> None:
        self.actions = repository
        self.audit: AuditRecorder = NullAuditRecorder()

    async def __aenter__(self) -> "MemoryUnitOfWork":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def close(self) -> None:
        return None


class MemoryRoleUnitOfWork:
    """No-transaction unit of work over the shared in-memory role repository."""

    def __init__(self, repository: RoleRepository) -> None:
        self.roles = repository
        self.audit: AuditRecorder = NullAuditRecorder()

    async def __aenter__(self) -> "MemoryRoleUnitOfWork":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def close(self) -> None:
        return None
