"""SMTP email adapter — stubbed until the relay is available (Tracker B-06).

Logs what would have been sent instead of actually sending — the real adapter (SMTP
client) drops in behind the same ``EmailSender`` port without touching callers, the
same swap-by-config pattern used for AD FS and ai-service.
"""

from src.application.notifications.email_sender import EmailSender
from src.core.config import Settings
from src.core.logging import get_logger

logger = get_logger(__name__)


class StubEmailSender(EmailSender):
    """Local/dev stand-in — logs the email instead of sending it over real SMTP."""

    async def send(self, to: str, subject: str, body: str) -> None:
        logger.info(f"[STUB EMAIL] to={to!r} subject={subject!r} body={body!r}")


def get_email_sender(settings: Settings) -> EmailSender:
    """The real SMTP client, or the local stub while ``email_stub_enabled``.

    Same swap-by-config pattern as AD FS (``auth_stub_enabled``) and ai-service
    (``ai_service_stub_enabled``) — found missing in code review, where the sweep
    script had ``StubEmailSender()`` hardcoded instead of going through this switch.
    No real SMTP relay is provisioned yet (Outstanding Items Tracker B-06), so
    disabling the stub has nowhere to go yet — matches how ``token_validator.py``'s
    live-AD-FS path raises until A-01 lands.
    """
    if settings.email_stub_enabled:
        return StubEmailSender()
    raise NotImplementedError("Live SMTP sending not yet configured (Tracker B-06).")
