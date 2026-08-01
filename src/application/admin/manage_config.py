"""Admin: shift configuration (US-008 — EP-04, ES-308/309/310/311).

Shift configuration is append-only and effective-dated: a change always INSERTs a new
version, never UPDATEs an existing row (see ``domain/shifts/entities.py``). ``area is
None`` means plant-wide; version numbering and the "history must move strictly
forward" rule are both scoped per area, so a plant-wide change and a Train-1-specific
change track independent version sequences. Every mutation is audited in the same
hash-chained trail as pending-actions and role changes (ES-311).
"""

import uuid
from datetime import UTC, datetime
from typing import Protocol

from src.api.errors.exceptions import ConflictError, ValidationError
from src.application.audit.recorder import AuditEntry, AuditRecorder
from src.application.shifts.repository import ShiftConfigRepository
from src.domain.shifts.entities import ShiftConfiguration


class ShiftConfigUnitOfWork(Protocol):
    """The transaction boundary ``create_shift_configuration`` runs within.

    A structural (``typing.Protocol``) shape rather than an import of the concrete
    infrastructure unit-of-work classes — the application layer must not depend
    outward on infrastructure (clean-architecture dependency rule); both
    ``SqlShiftConfigUnitOfWork`` and ``MemoryShiftConfigUnitOfWork`` satisfy this
    shape without inheriting from it.
    """

    shift_configs: ShiftConfigRepository
    audit: AuditRecorder


async def list_shift_configurations(repo: ShiftConfigRepository) -> list[ShiftConfiguration]:
    return await repo.list_all()


async def get_shift_configuration(
    repo: ShiftConfigRepository, config_id: str
) -> ShiftConfiguration | None:
    return await repo.get(config_id)


def _latest_for_area(
    configs: list[ShiftConfiguration], area: str | None
) -> ShiftConfiguration | None:
    """The highest-``version`` row for ``area`` (plant-wide when ``area is None``)."""
    scoped = [c for c in configs if c.area == area]
    if not scoped:
        return None
    return max(scoped, key=lambda c: c.version)


async def create_shift_configuration(
    uow: ShiftConfigUnitOfWork,
    *,
    area: str | None,
    start_hour: int,
    hours: int,
    overlap_minutes: int,
    effective_from: datetime,
    expected_version: int,
    actor: str,
) -> ShiftConfiguration:
    """Append a new shift-configuration version. Never updates an existing row.

    ``expected_version`` is optimistic concurrency: the caller must state the version
    it believes is current for ``area`` (0 if none exists yet), otherwise someone else
    changed it first (409). ``effective_from`` must be strictly later than the latest
    existing version's ``effective_from`` for the same area — history only moves
    forward (409 otherwise). Values are range-checked first (422).
    """
    existing = await uow.shift_configs.list_all()
    latest = _latest_for_area(existing, area)
    previous_version = latest.version if latest is not None else 0

    now = datetime.now(UTC)
    config = ShiftConfiguration(
        id=uuid.uuid4().hex,
        area=area,
        start_hour=start_hour,
        hours=hours,
        overlap_minutes=overlap_minutes,
        effective_from=effective_from,
        version=previous_version + 1,
        created_by=actor,
        created_at=now,
        updated_at=now,
    )
    try:
        config.validate()
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    if expected_version != previous_version:
        raise ConflictError(
            f"expected_version {expected_version} is stale; the current version for "
            f"this area is {previous_version}."
        )
    if latest is not None and effective_from <= latest.effective_from:
        raise ConflictError(
            "effective_from must be later than the latest existing version's "
            "effective_from for this area."
        )

    stored = await uow.shift_configs.add(config)
    await uow.audit.record(
        AuditEntry(
            actor=actor,
            action="shift_config.create",
            entity_type="shift_config",
            # is not None, not `or`: area="" is a distinct (if unusual) area key from
            # every other resolution path in this feature (effective_for,
            # _latest_for_area both use `==`/`is`), so it must not fall into the
            # plant-wide history bucket.
            entity_id=area if area is not None else "__plant__",
            payload={
                "id": stored.id,
                "area": stored.area,
                "start_hour": stored.start_hour,
                "hours": stored.hours,
                "overlap_minutes": stored.overlap_minutes,
                "effective_from": stored.effective_from.isoformat(),
                "version": stored.version,
                "expected_version": expected_version,
                "created_by": stored.created_by,
            },
        )
    )
    return stored
