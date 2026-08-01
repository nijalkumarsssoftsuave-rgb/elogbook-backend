"""Action-extractor port — the backend<->ai-service contract for ES-341.

Defined in the application layer so the use case and API depend on this shape, not on
how or where extraction actually runs (clean-architecture dependency rule) — swapping
the local stub for the real ai-service (Outstanding Items Tracker: ai-service built in
parallel) is an adapter change in ``infrastructure/ai_client``, never a caller change.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.domain.ai_extraction.entities import CandidateAction


@dataclass(frozen=True)
class ExtractionRequest:
    """Free text plus optional context that sharpens extraction accuracy.

    ``area``/``equipment`` are the same vocabulary ``PendingAction`` already uses —
    passing them through lets the model (real or stub) bias its suggestions toward the
    part of the plant the entry is actually about, instead of guessing from text alone.
    """

    text: str
    area: str | None = None
    equipment: str | None = None


class ActionExtractor(ABC):
    """Contract for turning free text into candidate (unconfirmed) actions."""

    @abstractmethod
    async def extract_candidates(self, request: ExtractionRequest) -> list[CandidateAction]: ...
