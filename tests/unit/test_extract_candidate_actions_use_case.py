"""Unit tests for the extract-candidate-actions use case (ES-341)."""

import pytest

from src.api.errors.exceptions import ValidationError
from src.application.ai_extraction.extract_candidates import extract_candidate_actions
from src.application.ai_extraction.extractor import ActionExtractor, ExtractionRequest
from src.domain.ai_extraction.entities import CandidateAction
from src.domain.pending_actions.entities import Priority


class SpyExtractor(ActionExtractor):
    """Records the request it received so the use case's pass-through can be asserted."""

    def __init__(self) -> None:
        self.received: ExtractionRequest | None = None

    async def extract_candidates(self, request: ExtractionRequest) -> list[CandidateAction]:
        self.received = request
        return [CandidateAction(issue="stub issue", priority=Priority.MEDIUM)]


async def test_empty_text_is_rejected_before_reaching_the_extractor():
    extractor = SpyExtractor()
    with pytest.raises(ValidationError):
        await extract_candidate_actions(extractor, "   ")
    assert extractor.received is None


async def test_text_is_trimmed_and_context_passed_through():
    extractor = SpyExtractor()
    result = await extract_candidate_actions(
        extractor, "  Check alarm.  ", area="Train 1", equipment="V-101"
    )

    assert extractor.received.text == "Check alarm."
    assert extractor.received.area == "Train 1"
    assert extractor.received.equipment == "V-101"
    assert result[0].issue == "stub issue"
