"""Bound request bodies before framework parsing."""

import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from starlette.types import Message, Receive, Scope, Send

from app.core.exceptions import REQUEST_ID_HEADER, new_error_reference, public_error_detail

ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]
BODY_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
REQUEST_BODY_TOO_LARGE = "request_body_too_large"


@dataclass(frozen=True)
class BodyReadResult:
    messages: list[Message]
    exceeded: bool = False
    disconnected: bool = False


class RequestBodyLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        default_max_bytes: int,
        path_limits: Mapping[tuple[str, str], int] | None = None,
    ) -> None:
        self.app = app
        self.default_max_bytes = default_max_bytes
        self.path_limits = dict(path_limits or {})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in BODY_METHODS:
            await self.app(scope, receive, send)
            return

        max_bytes = self.path_limits.get((scope["method"], scope["path"]), self.default_max_bytes)
        if self._content_length_exceeds_limit(scope, max_bytes):
            await self._reject(scope, send)
            return

        result = await self._read_body(receive, max_bytes)
        if result.disconnected:
            return
        if result.exceeded:
            await self._reject(scope, send)
            return

        messages = result.messages

        async def replay() -> Message:
            if messages:
                return messages.pop(0)
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay, send)

    def _content_length_exceeds_limit(self, scope: Scope, max_bytes: int) -> bool:
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length is None:
            return False
        try:
            return int(content_length) > max_bytes
        except ValueError:
            return False

    async def _read_body(self, receive: Receive, max_bytes: int) -> BodyReadResult:
        messages: list[Message] = []
        received = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.disconnect":
                return BodyReadResult(messages, disconnected=True)
            received += len(message.get("body", b""))
            if received > max_bytes:
                return BodyReadResult(messages, exceeded=True)
            if not message.get("more_body", False):
                return BodyReadResult(messages)

    @staticmethod
    async def _reject(scope: Scope, send: Send) -> None:
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        incoming = headers.get(REQUEST_ID_HEADER.lower().encode(), b"").decode("ascii", "ignore")
        reference = (
            incoming if len(incoming) == 12 and incoming.isalnum() else new_error_reference()
        )
        detail = public_error_detail(
            code=REQUEST_BODY_TOO_LARGE,
            reference=reference,
            status_code=413,
        )
        body = json.dumps({"detail": detail}, separators=(",", ":"), ensure_ascii=False).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (REQUEST_ID_HEADER.lower().encode(), reference.encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
