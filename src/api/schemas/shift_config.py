"""Shift-configuration request/response schemas (US-008)."""

from pydantic import AwareDatetime, BaseModel, Field

from src.domain.shifts.entities import ShiftConfiguration


class CreateShiftConfigRequest(BaseModel):
    """Append a new shift-configuration version."""

    # min_length=1: an omitted/null area means plant-wide; "" must not be accepted as a
    # silent, distinct third option (it would create its own orphaned area-scoped
    # version series with an empty-string area — reject it at the boundary instead).
    area: str | None = Field(default=None, min_length=1)
    start_hour: int
    hours: int
    overlap_minutes: int
    # AwareDatetime, not plain datetime: a naive value would compare incomparably
    # against the tz-aware effective_from values everywhere else in this feature
    # (ShiftConfiguration.effective_for, the "history must move forward" check), and
    # once persisted would keep raising on every later read — reject it at the
    # boundary (422) instead.
    effective_from: AwareDatetime
    expected_version: int = Field(
        description="The version this change is based on (0 if none exists yet for this area)."
    )


class ShiftConfigResponse(BaseModel):
    """The shift-configuration representation returned to clients."""

    id: str
    area: str | None
    start_hour: int
    hours: int
    overlap_minutes: int
    effective_from: str
    version: int
    created_by: str
    created_at: str
    updated_at: str

    @staticmethod
    def of(cfg: ShiftConfiguration) -> "ShiftConfigResponse":
        return ShiftConfigResponse(
            id=cfg.id,
            area=cfg.area,
            start_hour=cfg.start_hour,
            hours=cfg.hours,
            overlap_minutes=cfg.overlap_minutes,
            effective_from=cfg.effective_from.isoformat(),
            version=cfg.version,
            created_by=cfg.created_by,
            created_at=cfg.created_at.isoformat(),
            updated_at=cfg.updated_at.isoformat(),
        )
