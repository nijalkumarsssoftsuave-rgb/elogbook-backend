"""Application configuration, loaded from the environment.

Follows the Engineering Code Standards: no secrets in code — everything sensitive
comes from the environment (managed secrets engine in the real environments).
"""

from functools import lru_cache
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="ELOG_", extra="ignore")

    # --- service ---
    app_name: str = "elogbook-backend"
    environment: str = Field(default="local", description="local | dev | prod")
    api_v1_prefix: str = "/api/v1"
    debug: bool = False

    # --- auth (AD FS / OAuth 2.0; stub issuer locally until A-01) ---
    auth_issuer: str = "https://stub-issuer.local"
    auth_audience: str = "elogbook"
    auth_stub_enabled: bool = True  # local stub token validation; disabled once AD FS is wired
    token_ttl_minutes: int = 15
    # RSA keypair for the local dev token issuer (stub mode only) — signs stand-in tokens
    # shaped like real AD FS ones so the validation code needs no change when A-01 lands.
    auth_dev_keys_dir: str = ".devkeys"

    # --- persistence ---
    # backend: "memory" (default; no server needed) | "sql" (SQLAlchemy: MS SQL / SQLite)
    persistence_backend: str = "memory"
    # MS SQL over the async aioodbc driver in the deployed environments (local container
    # until A-04); an aiosqlite URL is used for local/CI runs without a SQL Server.
    database_url: str = "mssql+aioodbc://sa:Local_dev_pw1@localhost:1433/elogbook_app?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
    db_echo: bool = False  # log emitted SQL (local debugging only)
    db_create_all: bool = False  # bootstrap tables from metadata (local/test only)

    # --- audit (hash-chained, append-only; written in the same transaction as each mutation) ---
    audit_enabled: bool = True

    # --- cache (Valkey; confirmed C17) ---
    valkey_url: str = "redis://localhost:6379/0"

    # --- ai-service (backend<->AI contract; stub until the ai-service repo is ready) ---
    ai_service_url: str = "http://localhost:9000"
    ai_service_stub_enabled: bool = True

    # --- shift definition bootstrap defaults (BRD FR-HOME-03) ---
    # US-008 ES-308: the live source of truth is now the persisted, append-only,
    # effective-dated shift_configurations store (src/domain/shifts/entities.py:
    # ShiftConfiguration) — these three settings are only the bootstrap fallback: the
    # values baked into the MS SQL seed row (migrations/0003_shift_configurations.sql),
    # the in-memory backend's seed row (InMemoryShiftConfigRepository), and what the
    # resolver falls back to when no configuration is effective yet.
    shift_hours: int = 12
    shift_start_hour: int = 6  # 06:00
    shift_overlap_minutes: int = 15  # 06:00–06:15 overlap

    # --- shift history query range + pagination (US-009 ES-312/314) ---
    # A distinct concern from the shift-*definition* bootstrap defaults above: these
    # bound the GET /shifts date range and page size, not the shift window shape itself.
    shift_history_max_range_days: int = 92
    shift_history_page_size_default: int = 20
    shift_history_page_size_max: int = 100

    # --- pending-action workflow (Admin-toggled; BRD FR-PA-05) ---
    # when False: capture + confirm-inclusion only, no assignment or lifecycle tracking
    action_workflow_enabled: bool = False

    @model_validator(mode="after")
    def _shift_history_page_size_default_within_max(self) -> Self:
        """A misconfigured ``.env`` (default > max) would silently defeat the max cap
        for every request that omits ``page_size`` — fail fast at startup instead."""
        if self.shift_history_page_size_default > self.shift_history_page_size_max:
            raise ValueError(
                "shift_history_page_size_default "
                f"({self.shift_history_page_size_default}) must not exceed "
                f"shift_history_page_size_max ({self.shift_history_page_size_max})."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()


settings = get_settings()
