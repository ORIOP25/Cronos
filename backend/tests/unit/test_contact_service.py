from dataclasses import dataclass, field

import pytest

from app.contact.service import ContactApplicationService
from app.schemas import ContactSubmission


def submission(**changes) -> ContactSubmission:
    values = {
        "subject": "Criar horários",
        "courses": "Entre 1 e 5",
        "teachers": "Entre 1 e 15",
        "name": "Ana",
        "email": "ana@escola.pt",
        "website": "",
        "turnstile_token": "valid-token",
    }
    return ContactSubmission(**(values | changes))


@dataclass
class FakeVerifier:
    failure: Exception | None = None
    calls: list[tuple[str, str | None]] = field(default_factory=list)

    async def verify(self, token: str, *, remote_ip: str | None) -> None:
        self.calls.append((token, remote_ip))
        if self.failure:
            raise self.failure


@dataclass
class FakeEmailGateway:
    calls: list[ContactSubmission] = field(default_factory=list)

    async def send(self, value: ContactSubmission) -> None:
        self.calls.append(value)


@pytest.mark.asyncio
async def test_honeypot_returns_without_verification_or_email():
    verifier = FakeVerifier()
    gateway = FakeEmailGateway()
    service = ContactApplicationService(verifier, gateway)

    await service.submit(submission(website="bot"), remote_ip="192.0.2.10")

    assert verifier.calls == []
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_valid_token_is_verified_before_email_delivery():
    events = []

    class Verifier:
        async def verify(self, token, *, remote_ip):
            events.append(("verify", token, remote_ip))

    class Gateway:
        async def send(self, value):
            events.append(("send", value.email))

    await ContactApplicationService(Verifier(), Gateway()).submit(
        submission(), remote_ip="192.0.2.10"
    )

    assert events == [
        ("verify", "valid-token", "192.0.2.10"),
        ("send", "ana@escola.pt"),
    ]


@pytest.mark.asyncio
async def test_verification_failure_never_sends_email():
    verifier = FakeVerifier(failure=RuntimeError("invalid"))
    gateway = FakeEmailGateway()
    service = ContactApplicationService(verifier, gateway)

    with pytest.raises(RuntimeError, match="invalid"):
        await service.submit(submission(), remote_ip=None)

    assert gateway.calls == []
