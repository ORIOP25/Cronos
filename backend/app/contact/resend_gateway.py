"""Resend HTTPS adapter for public contact delivery."""

from __future__ import annotations

import html
from time import perf_counter

import httpx
import structlog

from app.core.exceptions import AppError
from app.schemas import ContactSubmission

RESEND_EMAILS_URL = "https://api.resend.com/emails"
UNAVAILABLE_MESSAGE = "Não foi possível enviar o pedido neste momento."

logger = structlog.get_logger(__name__)


def _answers(submission: ContactSubmission) -> list[tuple[str, str]]:
    return [
        ("Nome", submission.name),
        ("Email", str(submission.email)),
        ("Telefone", submission.phone or "Não indicado"),
        ("Assunto", submission.subject),
        ("Cursos", submission.courses),
        ("Professores", submission.teachers),
        ("Mensagem", submission.message or "Não indicada"),
    ]


def build_resend_payload(
    submission: ContactSubmission,
    *,
    email_from: str,
    email_to: str,
) -> dict[str, object]:
    answers = _answers(submission)
    text = "Novo contacto do website Cronos\n\n" + "\n".join(
        f"{label}: {value}" for label, value in answers
    )
    rows = "".join(
        f"<dt>{html.escape(label)}</dt><dd>{html.escape(value)}</dd>" for label, value in answers
    )
    subject = " ".join(submission.subject.split())
    return {
        "from": f"Cronos Website <{email_from}>",
        "to": [email_to],
        "reply_to": str(submission.email),
        "subject": f"[Cronos] Novo contacto — {subject}",
        "text": text,
        "html": f"<html><body><h1>Novo contacto do website Cronos</h1><dl>{rows}</dl></body></html>",
    }


class ResendContactEmailGateway:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        api_key: str,
        email_from: str,
        email_to: str,
        timeout_seconds: int,
        request_id: str | None = None,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._email_from = email_from
        self._email_to = email_to
        self._timeout_seconds = timeout_seconds
        self._request_id = request_id

    async def send(self, submission: ContactSubmission) -> None:
        started = perf_counter()
        provider_status: int | None = None
        try:
            response = await self._client.post(
                RESEND_EMAILS_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=build_resend_payload(
                    submission,
                    email_from=self._email_from,
                    email_to=self._email_to,
                ),
                timeout=self._timeout_seconds,
            )
            provider_status = response.status_code
            if not 200 <= response.status_code < 300:
                raise httpx.HTTPStatusError(
                    "Resend rejected contact delivery.",
                    request=response.request,
                    response=response,
                )
        except httpx.HTTPError as exc:
            logger.warning(
                "contact_email_delivery_failed",
                provider_status=provider_status,
                request_id=self._request_id,
                error_type=type(exc).__name__,
                duration_ms=round((perf_counter() - started) * 1000),
            )
            raise AppError(
                kind="unavailable",
                code="contact_delivery_unavailable",
                detail=UNAVAILABLE_MESSAGE,
            ) from exc
        logger.info(
            "contact_email_sent",
            provider_status=provider_status,
            request_id=self._request_id,
            duration_ms=round((perf_counter() - started) * 1000),
        )
