"""Contract test: the shift resolver is a reusable, standalone entry point (ES-310).

ES-309 built ``resolve_current_shift`` for ``GET /shifts/current``. ES-310's requirement
is that the *same* definition drives other, not-yet-built consumers — shift summaries,
scheduled reports — without duplicating the resolution logic. This test proves the
contract holds by calling the resolver exactly as a future, unrelated application-layer
consumer would: directly, with its own repository and settings, no HTTP layer involved.
"""

from datetime import UTC, datetime

from src.application.shifts.current_shift import resolve_current_shift
from src.core.config import get_settings
from src.domain.shifts.entities import Shift, ShiftConfiguration
from src.infrastructure.persistence.in_memory_shift_config import InMemoryShiftConfigRepository


async def test_a_hypothetical_future_consumer_can_resolve_the_same_shift_independently():
    """Simulates a not-yet-built consumer (e.g. a scheduled summary job) that needs
    "what shift covers this moment" without going through the API layer at all —
    proving the resolver is a standalone, reusable contract, not something wired only
    into the /shifts/current endpoint.

    Seeds a config whose ``start_hour`` (7) deliberately differs from the ``Settings``
    default (6): the repo's bootstrap seed row already matches ``Settings`` exactly, so
    asserting against that row alone couldn't tell a real repo-driven resolution apart
    from a resolver that silently ignored the repo and fell back to Settings. A later,
    distinctly-valued row closes that gap.
    """
    settings = get_settings()
    repo = InMemoryShiftConfigRepository(settings)
    now = datetime(2026, 7, 30, 10, 0, tzinfo=UTC)
    custom = await repo.add(
        ShiftConfiguration(
            id="custom-plant-wide",
            area=None,
            start_hour=7,
            hours=12,
            overlap_minutes=15,
            effective_from=datetime(2020, 1, 1, tzinfo=UTC),
            version=2,
            created_by="admin.user",
            created_at=now,
            updated_at=now,
        )
    )

    shift, resolved_area = await resolve_current_shift(repo, settings, now=now, area=None)

    assert shift == Shift.from_config(custom, now)
    assert resolved_area is None


async def test_two_independent_callers_resolving_the_same_instant_agree():
    """Two separate call sites (standing in for the real endpoint and a future summary
    job), sharing one repository, must derive the identical shift from the identical
    configuration state for the identical instant — the whole point of a single shared
    resolver instead of each consumer reimplementing shift-window math. (This does not
    by itself prove either caller resolved correctly — see the test above for that —
    only that the two callers can't disagree with each other.)
    """
    settings = get_settings()
    repo = InMemoryShiftConfigRepository(settings)
    now = datetime(2026, 7, 30, 20, 0, tzinfo=UTC)

    caller_a = await resolve_current_shift(repo, settings, now=now, area=None)
    caller_b = await resolve_current_shift(repo, settings, now=now, area=None)

    assert caller_a == caller_b
