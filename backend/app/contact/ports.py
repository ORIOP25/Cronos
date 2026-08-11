"""Provider-independent contact service contracts."""

from typing import Protocol

from app.schemas import ContactSubmission


class ContactEmailGateway(Protocol):
    async def send(self, submission: ContactSubmission) -> None: ...


class TurnstileVerifier(Protocol):
    async def verify(self, token: str, *, remote_ip: str | None) -> None: ...
