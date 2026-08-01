"""Unit tests for the local stub AI extractor (ES-341) — deterministic, no network."""

from src.application.ai_extraction.extractor import ExtractionRequest
from src.domain.pending_actions.entities import Priority
from src.infrastructure.ai_client.client import StubActionExtractor


async def test_splits_text_into_one_candidate_per_sentence():
    extractor = StubActionExtractor()
    request = ExtractionRequest(text="Inspect PSV on V-101. Replace worn gasket on P-204.")
    candidates = await extractor.extract_candidates(request)

    issues = [c.issue for c in candidates]
    assert issues == ["Inspect PSV on V-101", "Replace worn gasket on P-204"]
    assert all(c.priority == Priority.MEDIUM for c in candidates)


async def test_context_area_and_equipment_pass_through_to_every_candidate():
    extractor = StubActionExtractor()
    request = ExtractionRequest(text="Check alarm.", area="Train 1", equipment="V-101")
    candidates = await extractor.extract_candidates(request)

    assert len(candidates) == 1
    assert candidates[0].area == "Train 1"
    assert candidates[0].equipment == "V-101"


async def test_blank_and_duplicate_fragments_are_dropped():
    extractor = StubActionExtractor()
    request = ExtractionRequest(text="Check alarm.. Check alarm.  ;  ")
    candidates = await extractor.extract_candidates(request)

    assert [c.issue for c in candidates] == ["Check alarm"]


async def test_candidate_count_is_capped():
    extractor = StubActionExtractor()
    text = ". ".join(f"issue {i}" for i in range(20))
    candidates = await extractor.extract_candidates(ExtractionRequest(text=text))

    assert len(candidates) == 10
