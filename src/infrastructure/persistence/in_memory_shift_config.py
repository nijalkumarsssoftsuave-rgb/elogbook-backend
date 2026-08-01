"""In-memory shift-configuration repository — the default local/test backend.

Seeded at construction with one plant-wide configuration (``version=1``, ``area=None``)
built from the ``Settings`` bootstrap defaults (``shift_start_hour``, ``shift_hours``,
``shift_overlap_minutes``) — mirrors the seed row the MS SQL migration inserts
(``migrations/0003_shift_configurations.sql``).
"""

import uuid
from datetime import UTC, datetime

from src.application.shifts.repository import ShiftConfigRepository
from src.core.config import Settings
from src.domain.shifts.entities import ShiftConfiguration

# "In effect since forever" — always the fallback until an admin posts a real change.
# Matches the seed row's effective_from in migrations/0003_shift_configurations.sql.
EPOCH = datetime(1900, 1, 1, tzinfo=UTC)


def seed_shift_configuration(settings: Settings) -> ShiftConfiguration:
    """Build the bootstrap plant-wide configuration row from ``Settings`` defaults."""
    now = datetime.now(UTC)
    return ShiftConfiguration(
        id=uuid.uuid4().hex,
        area=None,
        start_hour=settings.shift_start_hour,
        hours=settings.shift_hours,
        overlap_minutes=settings.shift_overlap_minutes,
        effective_from=EPOCH,
        version=1,
        created_by="system",
        created_at=now,
        updated_at=now,
    )


class InMemoryShiftConfigRepository(ShiftConfigRepository):
    """Process-local store. Not for production — replaced by the MS SQL adapter.

    Unlike the SQL adapter, ``add`` here has no uniqueness guard: it cannot race in
    practice (single process, no concurrent writers), so it does not need the SQL
    backend's filtered-unique-index protection against two callers computing the same
    "next version" (see ``sql_shift_config.py``). Do not treat this backend as proof
    the optimistic-concurrency check is safe under real concurrency — only the SQL
    adapter's constraints guarantee that.
    """

    def __init__(self, settings: Settings) -> None:
        seed = seed_shift_configuration(settings)
        self._items: dict[str, ShiftConfiguration] = {seed.id: seed}

    async def list_all(self) -> list[ShiftConfiguration]:
        return sorted(self._items.values(), key=lambda c: c.effective_from)

    async def get(self, config_id: str) -> ShiftConfiguration | None:
        return self._items.get(config_id)

    async def add(self, config: ShiftConfiguration) -> ShiftConfiguration:
        self._items[config.id] = config
        return config
