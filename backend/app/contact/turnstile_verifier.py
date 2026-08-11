"""Cloudflare Turnstile verification adapter."""

from __future__ import annotations

from time import perf_counter

import httpx
import structlog

from app.core.exceptions import AppError

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
INVALID_MESSAGE = "A verificação anti-spam não foi aceite."
UNAVAILABLE_MESSAGE = "Não foi possível validar o pedido neste momento."

logger = structlog.get_logger(__name__)


class CloudflareTurnstileVerifier:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        secret_key: str,
        allowed_hostnames: set[str],
        timeout_seconds: int,
        request_id: str | None = None,
    ) -> None:
        self._client = client
        self._secret_key = secret_key
        self._allowed_hostnames = {hostname.lower() for hostname in allowed_hostnames}
        self._timeout_seconds = timeout_seconds
        self._request_id = request_id

    async def verify(self, token: str, *, remote_ip: str | None) -> None:
        started = perf_counter()
        data = {"secret": self._secret_key, "response": token}
        if remote_ip:
            data["remoteip"] = remote_ip
        try:
            response = await self._client.post(
                TURNSTILE_VERIFY_URL,
                data=data,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "turnstile_verification_unavailable",
                failure_type=type(exc).__name__,
                request_id=self._request_id,
                duration_ms=round((perf_counter() - started) * 1000),
            )
            raise AppError(
                kind="unavailable",
                code="turnstile_unavailable",
                detail=UNAVAILABLE_MESSAGE,
            ) from exc

        if not isinstance(payload, dict):
            raise AppError(
                kind="unavailable",
                code="turnstile_unavailable",
                detail=UNAVAILABLE_MESSAGE,
            )
        error_codes = payload.get("error-codes", [])
        valid = (
            payload.get("success") is True
            and payload.get("action") == "contact"
            and isinstance(payload.get("hostname"), str)
            and payload["hostname"].lower() in self._allowed_hostnames
        )
        if not valid:
            logger.info(
                "turnstile_verification_rejected",
                failure_type="invalid_challenge",
                request_id=self._request_id,
                error_codes=error_codes if isinstance(error_codes, list) else [],
                duration_ms=round((perf_counter() - started) * 1000),
            )
            raise AppError(
                kind="bad_request",
                code="turnstile_rejected",
                detail=INVALID_MESSAGE,
            )
