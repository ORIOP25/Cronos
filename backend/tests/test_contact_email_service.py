import smtplib
import ssl
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.core.exceptions import AppError
from app.schemas import ContactSubmission
from app.services import contact_email_service as service


def submission(**changes):
    data = {"subject": "Criar hor?rios do zero", "courses": "Entre 1 e 5", "teachers": "Entre 1 e 15", "name": "Ana & <Coordenadora>", "email": "ana@escola.pt", "phone": None, "message": None, "website": ""}
    data.update(changes)
    return ContactSubmission(**data)


def config(password="secret"):
    return SimpleNamespace(CONTACT_SMTP_HOST="smtp.hostinger.com", CONTACT_SMTP_PORT=465, CONTACT_SMTP_USERNAME="contacto@cronos.pt", CONTACT_SMTP_PASSWORD=SecretStr(password) if password else None, CONTACT_EMAIL_TO="contacto@cronos.pt", CONTACT_SMTP_TIMEOUT_SECONDS=10)


def test_builds_safe_multipart_message():
    message = service.build_contact_message(submission(subject="Ol?\r\nBcc: attacker@example.com", message=None), config())
    assert message["From"] == "Cronos Website <contacto@cronos.pt>"
    assert message["To"] == "contacto@cronos.pt"
    assert message["Reply-To"] == "ana@escola.pt"
    assert "Bcc:" in message["Subject"]
    assert "\r" not in message["Subject"]
    parts = {part.get_content_type(): part.get_content() for part in message.iter_parts()}
    assert "text/plain" in parts and "text/html" in parts
    assert "N\u00e3o indicado" in parts["text/plain"] and "N\u00e3o indicada" in parts["text/plain"]
    assert "&lt;Coordenadora&gt;" in parts["text/html"]
    assert "Ana &amp; &lt;Coordenadora&gt;" in parts["text/html"]


def test_deliver_uses_tls_and_unwrapped_secret(monkeypatch):
    calls = {}
    class FakeSMTP:
        def __init__(self, host, port, timeout, context): calls.update(host=host, port=port, timeout=timeout, context=context)
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def login(self, username, password): calls.update(username=username, password=password)
        def send_message(self, message):
            calls["message"] = message
            return {}
    monkeypatch.setattr(service.smtplib, "SMTP_SSL", FakeSMTP)
    service._deliver_contact_message(service.build_contact_message(submission(), config()), config())
    assert calls["host"] == "smtp.hostinger.com" and calls["port"] == 465 and calls["timeout"] == 10
    assert calls["username"] == "contacto@cronos.pt" and calls["password"] == "secret"


@pytest.mark.asyncio
async def test_delivery_failure_becomes_safe_app_error(monkeypatch):
    monkeypatch.setattr(service, "settings", config())
    def fail(*_): raise TimeoutError("private detail")
    monkeypatch.setattr(service, "_deliver_contact_message", fail)
    with pytest.raises(AppError) as exc_info:
        await service.send_contact_email(submission())
    assert exc_info.value.kind == "unavailable"
    assert exc_info.value.metadata == {"code": "contact_delivery_unavailable", "message": "N\u00e3o foi poss\u00edvel enviar o pedido neste momento.", "retryable": True}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        smtplib.SMTPAuthenticationError(535, b"authentication failed"),
        smtplib.SMTPRecipientsRefused({"contacto@cronos.pt": (550, b"refused")}),
        ssl.SSLError("TLS failed"),
        OSError("connection failed"),
    ],
)
async def test_all_delivery_failures_become_safe_app_errors(monkeypatch, failure):
    monkeypatch.setattr(service, "settings", config())

    def fail(*_):
        raise failure

    monkeypatch.setattr(service, "_deliver_contact_message", fail)
    with pytest.raises(AppError) as exc_info:
        await service.send_contact_email(submission())
    assert exc_info.value.metadata["message"] == service.UNAVAILABLE_MESSAGE


@pytest.mark.asyncio
async def test_delivery_failure_log_excludes_submission_data(monkeypatch):
    events = []
    monkeypatch.setattr(service, "settings", config())
    monkeypatch.setattr(service.logger, "exception", lambda *args, **kwargs: events.append((args, kwargs)))
    monkeypatch.setattr(service, "_deliver_contact_message", lambda *_: (_ for _ in ()).throw(OSError("failed")))
    submitted = submission(name="Ana Privada", email="ana.privada@example.com", message="segredo")
    with pytest.raises(AppError):
        await service.send_contact_email(submitted)
    rendered = repr(events)
    assert "Ana Privada" not in rendered
    assert "ana.privada@example.com" not in rendered
    assert "segredo" not in rendered
    assert "secret" not in rendered
