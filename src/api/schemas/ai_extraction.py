"""AI action-extraction request/response schemas (ES-341)."""

from pydantic import BaseModel, Field

from src.domain.ai_extraction.entities import CandidateAction
from src.domain.pending_actions.entities import Priority


class ExtractCandidatesRequest(BaseModel):
    """Free text to extract candidate actions from, plus optional context."""

    text: str = Field(min_length=1, max_length=10_000)
    area: str | None = None
    equipment: str | None = None


class CandidateActionResponse(BaseModel):
    """One AI-suggested action — not yet a real pending action until confirmed."""

    issue: str
    priority: Priority
    area: str | None
    equipment: str | None
    confidence: float | None

    @staticmethod
    def of(c: CandidateAction) -> "CandidateActionResponse":
        return CandidateActionResponse(
            issue=c.issue,
            priority=c.priority,
            area=c.area,
            equipment=c.equipment,
            confidence=c.confidence,
        )
