"""Unit tests for the ``create_shift_configuration`` use case (US-008 ES-308).

Exercises the append-only happy path plus the conflict/validation branches, against an
in-memory repository + a fake audit recorder (present on the unit-of-work shape from
the start, matching every other mutating aggregate — but not yet called by this use
case; recording an entry is ES-311, tested there once it exists).
"""

from datetime import UTC, datetime

import pytest

from src.api.errors.exceptions import ConflictError, ValidationError
from src.application.admin.manage_config import (
    create_shift_configuration,
    get_shift_configuration,
    list_shift_configurations,
)
from src.application.audit.recorder import AuditEntry, AuditRecorder
from src.core.config import get_settings
from src.infrastructure.persistence.in_memory_shift_config import InMemoryShiftConfigRepository


class FakeAuditRecorder(AuditRecorder):
    """Collects every recorded entry for inspection instead of persisting anything."""

    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    async def record(self, entry: AuditEntry) -> None:
        self.entries.append(entry)


class FakeUow:
    """A minimal stand-in satisfying the ``ShiftConfigUnitOfWork`` shape."""

    def __init__(self) -> None:
        self.shift_configs = InMemoryShiftConfigRepository(get_settings())
        self.audit = FakeAuditRecorder()


@pytest.fixture
def uow() -> FakeUow:
    return FakeUow()


async def test_create_appends_version_previous_plus_one(uow):
    # The plant-wide seed row starts at version 1.
    created = await create_shift_configuration(
        uow,
        area=None,
        start_hour=7,
        hours=12,
        overlap_minutes=10,
        effective_from=datetime(2026, 6, 1, tzinfo=UTC),
        expected_version=1,
        actor="admin.user",
    )
    assert created.version == 2

    again = await create_shift_configuration(
        uow,
        area=None,
        start_hour=8,
        hours=12,
        overlap_minutes=10,
        effective_from=datetime(2026, 7, 1, tzinfo=UTC),
        expected_version=2,
        actor="admin.user",
    )
    assert again.version == 3


async def test_create_first_version_for_a_brand_new_area_uses_expected_version_zero(uow):
    created = await create_shift_configuration(
        uow,
        area="Train 1",
        start_hour=6,
        hours=12,
        overlap_minutes=15,
        effective_from=datetime(2026, 6, 1, tzinfo=UTC),
        expected_version=0,
        actor="admin.user",
    )
    assert created.version == 1
    assert created.area == "Train 1"


async def test_stale_expected_version_is_conflict(uow):
    with pytest.raises(ConflictError):
        await create_shift_configuration(
            uow,
            area=None,
            start_hour=7,
            hours=12,
            overlap_minutes=10,
            effective_from=datetime(2026, 6, 1, tzinfo=UTC),
            expected_version=99,
            actor="admin.user",
        )


async def test_effective_from_earlier_than_latest_is_conflict(uow):
    # The seed row's effective_from is 1900-01-01 — anything not later than that is stale.
    with pytest.raises(ConflictError):
        await create_shift_configuration(
            uow,
            area=None,
            start_hour=7,
            hours=12,
            overlap_minutes=10,
            effective_from=datetime(1899, 1, 1, tzinfo=UTC),
            expected_version=1,
            actor="admin.user",
        )


async def test_effective_from_equal_to_latest_is_conflict(uow):
    """History must move strictly forward — an equal effective_from does not count."""
    seeded = (await uow.shift_configs.list_all())[0]
    with pytest.raises(ConflictError):
        await create_shift_configuration(
            uow,
            area=None,
            start_hour=7,
            hours=12,
            overlap_minutes=10,
            effective_from=seeded.effective_from,
            expected_version=1,
            actor="admin.user",
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"start_hour": 25, "hours": 12, "overlap_minutes": 10},
        {"start_hour": -1, "hours": 12, "overlap_minutes": 10},
        {"start_hour": 6, "hours": 0, "overlap_minutes": 10},
        {"start_hour": 6, "hours": 5, "overlap_minutes": 10},
        {"start_hour": 6, "hours": 12, "overlap_minutes": -1},
        {"start_hour": 6, "hours": 12, "overlap_minutes": 720},
    ],
)
async def test_invalid_values_raise_validation_error(uow, kwargs):
    with pytest.raises(ValidationError):
        await create_shift_configuration(
            uow,
            area=None,
            effective_from=datetime(2026, 6, 1, tzinfo=UTC),
            expected_version=1,
            actor="admin.user",
            **kwargs,
        )


async def test_invalid_values_do_not_persist_or_audit(uow):
    with pytest.raises(ValidationError):
        await create_shift_configuration(
            uow,
            area=None,
            start_hour=25,
            hours=12,
            overlap_minutes=10,
            effective_from=datetime(2026, 6, 1, tzinfo=UTC),
            expected_version=1,
            actor="admin.user",
        )
    assert len(await uow.shift_configs.list_all()) == 1  # only the seed row
    assert uow.audit.entries == []


async def test_conflict_does_not_persist_or_audit(uow):
    with pytest.raises(ConflictError):
        await create_shift_configuration(
            uow,
            area=None,
            start_hour=7,
            hours=12,
            overlap_minutes=10,
            effective_from=datetime(2026, 6, 1, tzinfo=UTC),
            expected_version=99,
            actor="admin.user",
        )
    assert len(await uow.shift_configs.list_all()) == 1  # only the seed row
    assert uow.audit.entries == []


async def test_create_records_exactly_one_audit_entry_with_correct_actor_and_payload(uow):
    effective_from = datetime(2026, 6, 1, tzinfo=UTC)
    created = await create_shift_configuration(
        uow,
        area="Train 1",
        start_hour=7,
        hours=8,
        overlap_minutes=20,
        effective_from=effective_from,
        expected_version=0,
        actor="admin.user",
    )

    assert len(uow.audit.entries) == 1
    entry = uow.audit.entries[0]
    assert entry.actor == "admin.user"
    assert entry.action == "shift_config.create"
    assert entry.entity_type == "shift_config"
    assert entry.entity_id == "Train 1"
    assert entry.payload == {
        "id": created.id,
        "area": "Train 1",
        "start_hour": 7,
        "hours": 8,
        "overlap_minutes": 20,
        "effective_from": effective_from.isoformat(),
        "version": 1,
        "expected_version": 0,
        "created_by": "admin.user",
    }


async def test_plant_wide_audit_entity_id_is_stable_placeholder(uow):
    await create_shift_configuration(
        uow,
        area=None,
        start_hour=7,
        hours=12,
        overlap_minutes=10,
        effective_from=datetime(2026, 6, 1, tzinfo=UTC),
        expected_version=1,
        actor="admin.user",
    )
    assert uow.audit.entries[0].entity_id == "__plant__"


async def test_list_and_get_shift_configuration(uow):
    seeded = (await list_shift_configurations(uow.shift_configs))[0]
    fetched = await get_shift_configuration(uow.shift_configs, seeded.id)
    assert fetched == seeded
    assert await get_shift_configuration(uow.shift_configs, "does-not-exist") is None


async def test_area_and_plant_wide_versions_are_independent_sequences(uow):
    """A plant-wide change and an area-specific change track separate version counters."""
    train1 = await create_shift_configuration(
        uow,
        area="Train 1",
        start_hour=6,
        hours=12,
        overlap_minutes=15,
        effective_from=datetime(2026, 6, 1, tzinfo=UTC),
        expected_version=0,
        actor="admin.user",
    )
    assert train1.version == 1

    plant = await create_shift_configuration(
        uow,
        area=None,
        start_hour=7,
        hours=12,
        overlap_minutes=15,
        effective_from=datetime(2026, 6, 1, tzinfo=UTC),
        expected_version=1,
        actor="admin.user",
    )
    assert plant.version == 2  # plant-wide was already at version 1 (the seed)
