import httpx
import pytest

from app.contact import resend_gateway
from app.contact.resend_gateway import ResendContactEmailGateway, build_resend_payload
from app.core.exceptions import AppError
from app.schemas import ContactSubmission


def submission(**changes):
    values = {
        "subject": "  Criar   horários  ",
        "courses": "Entre 1 e 5",
        "teachers": "Entre 1 e 15",
        "name": "Ana & <Coordenadora>",
        "email": "ana@escola.pt",
        "message": "<script>segredo</script>",
        "website": "",
        "turnstile_token": "token",
    }
    return ContactSubmission(**(values | changes))


def gateway(client):
    return ResendContactEmailGateway(
        client,
        api_key="secret-key",
        email_from="website@forms.cronos.pt",
        email_to="contacto@cronos.pt",
        timeout_seconds=10,
    )


def test_payload_has_reply_to_plain_text_and_escaped_html():
    payload = build_resend_payload(
        submission(),
        email_from="website@forms.cronos.pt",
        email_to="contacto@cronos.pt",
    )
    assert payload["reply_to"] == "ana@escola.pt"
    assert payload["subject"] == "[Cronos] Novo contacto — Criar horários"
    assert "<script>segredo</script>" in payload["text"]
    assert "&lt;script&gt;segredo&lt;/script&gt;" in payload["html"]
    assert "Ana &amp; &lt;Coordenadora&gt;" in payload["html"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 201, 202, 204, 299])
async def test_accepts_every_2xx_response(status):
    async def handler(request):
        assert request.headers["authorization"] == "Bearer secret-key"
        return httpx.Response(status)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await gateway(client).send(submission())


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 429, 500, 503])
async def test_provider_rejection_is_unavailable(status):
    async def handler(request):
        return httpx.Response(status)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AppError) as exc_info:
            await gateway(client).send(submission())
    assert exc_info.value.kind == "unavailable"
    assert exc_info.value.detail == resend_gateway.UNAVAILABLE_MESSAGE


@pytest.mark.asyncio
async def test_timeout_is_unavailable_and_logs_exclude_pii(monkeypatch):
    events = []

    async def handler(request):
        raise httpx.ReadTimeout("private provider failure", request=request)

    monkeypatch.setattr(
        resend_gateway.logger,
        "warning",
        lambda *args, **kwargs: events.append((args, kwargs)),
    )
    private_submission = submission(
        name="Nome Privado", email="privado@example.com", message="Mensagem privada"
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AppError):
            await gateway(client).send(private_submission)
    rendered = repr(events)
    assert "Nome Privado" not in rendered
    assert "privado@example.com" not in rendered
    assert "Mensagem privada" not in rendered
    assert "secret-key" not in rendered
