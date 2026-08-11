"""Provider-independent contact submission use case."""

from dataclasses import dataclass

from app.contact.ports import ContactEmailGateway, TurnstileVerifier
from app.schemas import ContactSubmission


@dataclass(slots=True)
class ContactApplicationService:
    verifier: TurnstileVerifier
    email_gateway: ContactEmailGateway

    async def submit(self, submission: ContactSubmission, *, remote_ip: str | None) -> None:
        if submission.website:
            return
        await self.verifier.verify(submission.turnstile_token, remote_ip=remote_ip)
        await self.email_gateway.send(submission)
