"""Adapters for the backend<->ai-service action-extraction contract (ES-341).

Two implementations of ``ActionExtractor``, selected by ``ai_service_stub_enabled``
(``api/deps.py``), the same swap-by-config pattern used for AD FS and SMTP elsewhere in
this codebase — callers depend on the port, never on which one is wired in.

``StubActionExtractor`` is a deterministic, dependency-free placeholder for local/CI use
before the real ai-service is ready: it does no NLP, just splits free text into
candidate lines, so tests get stable, predictable output. ``HttpActionExtractor`` is the
real adapter; only its request/response shape is a guess pending the ai-service team's
confirmed contract — swapping the shape later is a one-file change, nothing upstream of
this module needs to know.
"""

import re

import httpx

from src.api.errors.exceptions import ExternalServiceError
from src.application.ai_extraction.extractor import ActionExtractor, ExtractionRequest
from src.core.logging import get_logger
from src.domain.ai_extraction.entities import CandidateAction
from src.domain.pending_actions.entities import Priority

logger = get_logger(__name__)

_SPLIT_RE = re.compile(r"[.\n;]+")
_MAX_STUB_CANDIDATES = 10


class StubActionExtractor(ActionExtractor):
    """Local placeholder: one candidate per non-empty sentence/line, capped and deduped.

    No real language understanding — good enough to exercise the full extract-then-
    confirm flow (endpoint, permissions, response shape) without depending on the real
    ai-service being reachable.
    """

    async def extract_candidates(self, request: ExtractionRequest) -> list[CandidateAction]:
        seen: set[str] = set()
        candidates: list[CandidateAction] = []
        for fragment in _SPLIT_RE.split(request.text):
            issue = fragment.strip()
            if not issue or issue.lower() in seen:
                continue
            seen.add(issue.lower())
            candidates.append(
                CandidateAction(
                    issue=issue,
                    priority=Priority.MEDIUM,
                    area=request.area,
                    equipment=request.equipment,
                )
            )
            if len(candidates) >= _MAX_STUB_CANDIDATES:
                break
        return candidates


def _parse_priority(raw: object) -> Priority:
    """Normalise casing before matching the enum.

    The real ai-service's casing convention for priority strings is unconfirmed, and
    rejecting a whole batch over "high" vs "High" would be a self-inflicted wound.
    """
    return Priority(str(raw).strip().capitalize())


class HttpActionExtractor(ActionExtractor):
    """Real adapter — calls the ai-service's extraction endpoint.

    Request/response shape is a placeholder pending the ai-service team's confirmed
    contract (Outstanding Items Tracker: ai-service built in parallel). A short timeout
    is deliberate: an unreachable/slow dependency must fail fast and loud, never hang
    the request indefinitely. The HTTP client is created once and reused for the life of
    this adapter — one pooled connection to ai-service, not a fresh TCP/TLS handshake per
    extraction call (``api/deps.py`` caches a single instance for exactly this reason).
    """

    def __init__(self, base_url: str, timeout_seconds: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    async def extract_candidates(self, request: ExtractionRequest) -> list[CandidateAction]:
        payload = {"text": request.text, "area": request.area, "equipment": request.equipment}
        try:
            resp = await self._client.post(f"{self._base_url}/extract", json=payload)
            resp.raise_for_status()
            body = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ExternalServiceError(f"ai-service extraction failed: {exc}") from exc

        try:
            raw_candidates = body["candidates"]
        except (KeyError, TypeError) as exc:
            raise ExternalServiceError(f"ai-service returned an unexpected shape: {exc}") from exc

        candidates: list[CandidateAction] = []
        for c in raw_candidates:
            try:
                candidates.append(
                    CandidateAction(
                        issue=c["issue"],
                        priority=_parse_priority(c.get("priority", Priority.MEDIUM.value)),
                        # falls back to the request's own context when the ai-service
                        # omits it per-candidate — the whole point of passing area/
                        # equipment in was to sharpen accuracy, not have it silently
                        # dropped on the one adapter dev/CI never exercises by default
                        area=c.get("area") or request.area,
                        equipment=c.get("equipment") or request.equipment,
                        confidence=c.get("confidence"),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning(f"ai-service returned a malformed candidate, skipping: {exc}")
        return candidates
