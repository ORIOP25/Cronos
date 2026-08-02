"""SMTP delivery for public website contact submissions."""

from __future__ import annotations

import html
import smtplib
import ssl
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid

import anyio
import structlog

from app.config import Settings, settings
from app.core.exceptions import AppError
from app.schemas import ContactSubmission

logger = structlog.get_logger(__name__)
UNAVAILABLE_MESSAGE = "N\u00e3o foi poss\u00edvel enviar o pedido neste momento."


def _answers(submission: ContactSubmission) -> list[tuple[str, str]]:
    return [
        ("Nome", submission.name),
        ("Email", str(submission.email)),
        ("Telefone", submission.phone or "N\u00e3o indicado"),
        ("Assunto", submission.subject),
        ("Cursos", submission.courses),
        ("Professores", submission.teachers),
        ("Mensagem", submission.message or "N\u00e3o indicada"),
    ]


def build_contact_message(submission: ContactSubmission, configuration: Settings) -> EmailMessage:
    """Build a multipart message without network I/O."""
    message = EmailMessage()
    message["From"] = f"Cronos Website <{configuration.CONTACT_SMTP_USERNAME}>"
    message["To"] = str(configuration.CONTACT_EMAIL_TO)
    message["Reply-To"] = str(submission.email)
    message["Subject"] = f"[Cronos] Novo contacto \u2014 {' '.join(submission.subject.split())}"
    message["Date"] = format_datetime(datetime.now(UTC))
    message["Message-ID"] = make_msgid(domain="cronos.pt")
    answers = _answers(submission)
    message.set_content(
        "Novo contacto do website Cronos\n\n"
        + "\n".join(f"{label}: {value}" for label, value in answers)
    )
    rows = "".join(
        f"<dt>{html.escape(label)}</dt><dd>{html.escape(value)}</dd>" for label, value in answers
    )
    message.add_alternative(
        f"<html><body><h1>Novo contacto do website Cronos</h1><dl>{rows}</dl></body></html>",
        subtype="html",
    )
    return message


def _deliver_contact_message(message: EmailMessage, configuration: Settings) -> None:
    password = configuration.CONTACT_SMTP_PASSWORD
    if password is None:
        raise RuntimeError("Contact SMTP password is not configured.")
    tls_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    tls_context.check_hostname = True
    tls_context.verify_mode = ssl.CERT_REQUIRED
    with smtplib.SMTP_SSL(
        configuration.CONTACT_SMTP_HOST,
        configuration.CONTACT_SMTP_PORT,
        timeout=configuration.CONTACT_SMTP_TIMEOUT_SECONDS,
        context=tls_context,
    ) as smtp:
        smtp.login(configuration.CONTACT_SMTP_USERNAME, password.get_secret_value())
        refused = smtp.send_message(message)
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)


async def send_contact_email(submission: ContactSubmission) -> None:
    try:
        message = build_contact_message(submission, settings)
        await anyio.to_thread.run_sync(_deliver_contact_message, message, settings)
    except (smtplib.SMTPException, OSError, TimeoutError, RuntimeError) as exc:
        logger.exception("contact_email_delivery_failed", error_type=type(exc).__name__)
        raise AppError(
            kind="unavailable",
            code="contact_delivery_unavailable",
            detail=UNAVAILABLE_MESSAGE,
            metadata={
                "code": "contact_delivery_unavailable",
                "message": UNAVAILABLE_MESSAGE,
                "retryable": True,
            },
        ) from exc
    logger.info("contact_email_sent")
