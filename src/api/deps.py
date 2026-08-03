"""FastAPI dependencies — the composition point for dependency injection.

Engineering Code Standards, discipline 5: dependencies are injected, not hard-wired.
Routers depend on these; swapping an implementation (e.g. stub auth -> AD FS, or
in-memory -> MS SQL) happens here, not in the endpoints.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.api.errors.exceptions import ForbiddenError
from src.application.ai_extraction.extractor import ActionExtractor
from src.application.audit.reader import AuditReader, NullAuditReader
from src.application.audit.recorder import AuditRecorder, NullAuditRecorder
from src.application.auth.resolve_permissions import has_permission
from src.application.pending_actions.repository import PendingActionRepository
from src.application.users_roles.repository import RoleRepository
from src.core.config import Settings, get_settings
from src.infrastructure.ai_client.client import HttpActionExtractor, StubActionExtractor
from src.infrastructure.auth.token_validator import Principal, validate_token
from src.infrastructure.persistence.in_memory_pending_actions import (
    InMemoryPendingActionRepository,
)
from src.infrastructure.persistence.in_memory_roles import InMemoryRoleRepository
from src.infrastructure.persistence.in_memory_uow import MemoryRoleUnitOfWork, MemoryUnitOfWork


def get_config() -> Settings:
    """Inject application settings."""
    return get_settings()


# single process-local repository instances (used by the in-memory backend)
_pending_action_repo = InMemoryPendingActionRepository()
_role_repo = InMemoryRoleRepository()


def get_pending_action_repository() -> PendingActionRepository:
    """Inject the pending-action repository (in-memory backend)."""
    return _pending_action_repo


async def get_pending_action_uow() -> AsyncIterator[MemoryUnitOfWork]:
    """Inject a pending-action unit of work for the configured backend.

    Yields an open transaction boundary; commits on a clean return and rolls back if the
    endpoint raises (FastAPI re-throws the exception into this generator at the ``yield``,
    so ``__aexit__`` rolls back). SQLAlchemy is imported only for the ``sql`` backend.
    """
    cfg = get_settings()
    if cfg.persistence_backend == "sql":
        from src.infrastructure.persistence.database import get_sessionmaker
        from src.infrastructure.persistence.unit_of_work import SqlUnitOfWork

        uow = SqlUnitOfWork(get_sessionmaker())
    else:
        uow = MemoryUnitOfWork(_pending_action_repo)

    async with uow:
        yield uow


async def get_role_repository() -> AsyncIterator[RoleRepository]:
    """Inject a read-only role repository for the configured backend.

    Used on every authenticated request (resolving a user's AD groups to roles), so this
    is a plain read, not a transaction — mutations go through ``get_role_uow`` instead.
    """
    cfg = get_settings()
    if cfg.persistence_backend == "sql":
        from src.infrastructure.persistence.database import get_sessionmaker
        from src.infrastructure.persistence.sql_roles import SqlRoleRepository

        async with get_sessionmaker()() as session:
            yield SqlRoleRepository(session)
    else:
        yield _role_repo


async def get_audit_recorder() -> AsyncIterator[AuditRecorder]:
    """Inject the recorder that audits every sign-in attempt (BE-US001-6).

    Not a shared unit of work — a sign-in isn't a business mutation, so this opens its
    own short-lived session for the ``sql`` backend. The ``finally`` commits even when
    ``get_current_user`` raises (a denial), since the whole point is to persist the
    denial audit row that was already staged before the exception was raised.
    """
    cfg = get_settings()
    if cfg.persistence_backend == "sql":
        from src.infrastructure.audit.audit_writer import SqlAuditWriter
        from src.infrastructure.persistence.database import get_sessionmaker

        session = get_sessionmaker()()
        try:
            yield SqlAuditWriter(session)
        finally:
            await session.commit()
            await session.close()
    else:
        yield NullAuditRecorder()


async def get_audit_reader() -> AsyncIterator[AuditReader]:
    """Inject the reader behind admin audit-history views (BE-US002-1 role history).

    A plain read, same shape as ``get_role_repository`` — its own short-lived session
    for the ``sql`` backend, ``NullAuditReader`` under ``memory`` since nothing was
    ever persisted to read back.
    """
    cfg = get_settings()
    if cfg.persistence_backend == "sql":
        from src.infrastructure.audit.audit_reader import SqlAuditReader
        from src.infrastructure.persistence.database import get_sessionmaker

        async with get_sessionmaker()() as session:
            yield SqlAuditReader(session)
    else:
        yield NullAuditReader()


async def get_role_uow() -> AsyncIterator[MemoryRoleUnitOfWork]:
    """Inject a role unit of work for the configured backend (admin role mutations)."""
    cfg = get_settings()
    if cfg.persistence_backend == "sql":
        from src.infrastructure.persistence.database import get_sessionmaker
        from src.infrastructure.persistence.unit_of_work import SqlRoleUnitOfWork

        uow = SqlRoleUnitOfWork(get_sessionmaker())
    else:
        uow = MemoryRoleUnitOfWork(_role_repo)

    async with uow:
        yield uow


_http_action_extractor: HttpActionExtractor | None = None


def get_action_extractor() -> ActionExtractor:
    """Inject the AI action-extractor (ES-341).

    The real ai-service client, or a local stub while ``ai_service_stub_enabled``
    (default locally, same switch as AD FS/SMTP). ``HttpActionExtractor`` is cached as a
    process-local singleton, same pattern as ``_role_repo``/``_pending_action_repo``
    above — it owns a pooled ``httpx.AsyncClient``, so it must outlive a single request
    to actually reuse connections to ai-service instead of paying a fresh handshake
    every call. ``StubActionExtractor`` holds no such resource, so it's cheap to build
    fresh each time.
    """
    cfg = get_settings()
    if cfg.ai_service_stub_enabled:
        return StubActionExtractor()
    global _http_action_extractor
    if _http_action_extractor is None:
        _http_action_extractor = HttpActionExtractor(cfg.ai_service_url)
    return _http_action_extractor


# Registers a real OpenAPI security scheme so Swagger shows the "Authorize" button
# (top-right) instead of a per-endpoint header box; auto_error=False so a missing token
# still reaches validate_token(None) and gets our standard UnauthorizedError envelope.
bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Token from POST /dev/token (stub mode) — swap for the real AD FS token "
    "once A-01 lands.",
)


async def get_current_user(
    role_repo: Annotated[RoleRepository, Depends(get_role_repository)],
    audit: Annotated[AuditRecorder, Depends(get_audit_recorder)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> Principal:
    """Validate the bearer token and resolve the authenticated principal's roles."""
    authorization = f"Bearer {credentials.credentials}" if credentials else None
    return await validate_token(authorization, role_repo, audit)


CurrentUser = Annotated[Principal, Depends(get_current_user)]
Config = Annotated[Settings, Depends(get_config)]
PendingActions = Annotated[PendingActionRepository, Depends(get_pending_action_repository)]
PendingActionUoW = Annotated[MemoryUnitOfWork, Depends(get_pending_action_uow)]
RoleRepositoryDep = Annotated[RoleRepository, Depends(get_role_repository)]
RoleUoW = Annotated[MemoryRoleUnitOfWork, Depends(get_role_uow)]
AuditReaderDep = Annotated[AuditReader, Depends(get_audit_reader)]
ActionExtractorDep = Annotated[ActionExtractor, Depends(get_action_extractor)]


def require_permission(permission: str):
    """Dependency factory enforcing a permission at the API layer (RBAC)."""

    def _checker(user: CurrentUser) -> Principal:
        if not has_permission(user.permissions, permission):
            raise ForbiddenError(f"Missing required permission: {permission}")
        return user

    return _checker
