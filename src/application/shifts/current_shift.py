"""Use case: resolve the current shift.

Application layer — orchestrates the domain rule with configuration. Depends inward
on the domain only; the API layer calls this, not the entity directly.
"""

from datetime import UTC, datetime

from src.application.shifts.repository import ShiftConfigRepository
from src.core.config import Settings
from src.domain.shifts.entities import Shift, ShiftConfiguration


def get_current_shift(settings: Settings, now: datetime | None = None) -> Shift:
    """Return the shift the current instant falls into, from the static ``Settings``.

    Bootstrap-only fallback with no configuration lookup — kept unchanged (signature
    included) because existing callers and ``tests/unit/test_shift_resolution.py``
    depend on it. ``resolve_current_shift`` below is the configuration-aware entry
    point new callers should use; it falls back to this when no persisted
    configuration is effective yet.
    """
    now = now or datetime.now(UTC)
    return Shift.resolve(
        now=now,
        start_hour=settings.shift_start_hour,
        hours=settings.shift_hours,
        overlap_minutes=settings.shift_overlap_minutes,
    )


async def resolve_current_shift(
    repo: ShiftConfigRepository,
    settings: Settings,
    now: datetime | None = None,
    area: str | None = None,
) -> tuple[Shift, str | None]:
    """Return the shift the current instant falls into, from the configured store.

    Loads every persisted configuration version and resolves the one effective at
    ``now`` for ``area`` (``ShiftConfiguration.effective_for``, ES-308). Falls back to
    the static ``Settings`` defaults — exactly like ``get_current_shift`` — when no
    configuration is effective yet (e.g. an empty repository).

    Returns the resolved ``Shift`` alongside the area whose configuration actually
    produced it (``None`` for the plant-wide config, or the ``Settings`` fallback).
    This can differ from the ``area`` argument: if the caller asked for an area that
    has no configuration of its own yet, resolution falls back to the plant-wide row
    and the returned area reflects that reality (``None``), not the requested lookup
    key — callers must not assume the requested area is what actually produced the
    window.
    """
    now = now or datetime.now(UTC)
    configs = await repo.list_all()
    cfg = ShiftConfiguration.effective_for(configs, now, area)
    if cfg is None:
        return get_current_shift(settings, now), None
    return Shift.from_config(cfg, now), cfg.area
