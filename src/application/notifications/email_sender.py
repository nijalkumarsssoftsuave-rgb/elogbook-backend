"""Email-sender port — the backend<->SMTP contract (ES-355).

Defined here so use cases depend on the port, never on whether the real relay or a
local stub is wired in — the same swap-by-config pattern used for AD FS and ai-service
elsewhere in this codebase. Real SMTP is stubbed until the relay is available
(Outstanding Items Tracker B-06); the stub logs what would have been sent instead.
"""

from abc import ABC, abstractmethod


class EmailSender(ABC):
    """Contract for sending a single email."""

    @abstractmethod
    async def send(self, to: str, subject: str, body: str) -> None: ...
