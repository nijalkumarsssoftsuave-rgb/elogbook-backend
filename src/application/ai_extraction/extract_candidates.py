"""Use case: extract candidate actions from free text via ai-service (ES-341)."""

from src.api.errors.exceptions import ValidationError
from src.application.ai_extraction.extractor import ActionExtractor, ExtractionRequest
from src.domain.ai_extraction.entities import CandidateAction


async def extract_candidate_actions(
    extractor: ActionExtractor,
    text: str,
    area: str | None = None,
    equipment: str | None = None,
) -> list[CandidateAction]:
    """Ask the ai-service (or its local stub) for candidate actions in ``text``.

    Nothing is persisted or audited here — extraction is a read, not a mutation. The
    caller confirms individual candidates by capturing them through the existing
    ``POST /pending-actions`` with ``source: "ai"``.
    """
    if not text or not text.strip():
        raise ValidationError("Text to extract from must not be empty.")
    return await extractor.extract_candidates(
        ExtractionRequest(text=text.strip(), area=area, equipment=equipment)
    )
