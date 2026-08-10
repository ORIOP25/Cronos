"""Bound request bodies before framework parsing."""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from starlette.types import Message, Receive, Scope, Send

ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


@dataclass(frozen=True)
class BodyReadResult:
    messages: list[Message]
    exceeded: bool = False
    disconnected: bool = False


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_bytes: int, method: str, path: str) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.method = method
        self.path = path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != self.method or scope["path"] != self.path:
            await self.app(scope, receive, send)
            return

        if self._content_length_exceeds_limit(scope):
            await self._reject(send)
            return

        result = await self._read_body(receive)
        if result.disconnected:
            return
        if result.exceeded:
            await self._reject(send)
            return

        messages = result.messages

        async def replay() -> Message:
            if messages:
                return messages.pop(0)
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay, send)

    def _content_length_exceeds_limit(self, scope: Scope) -> bool:
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length is None:
            return False
        try:
            return int(content_length) > self.max_bytes
        except ValueError:
            return False

    async def _read_body(self, receive: Receive) -> BodyReadResult:
        messages: list[Message] = []
        received = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.disconnect":
                return BodyReadResult(messages, disconnected=True)
            received += len(message.get("body", b""))
            if received > self.max_bytes:
                return BodyReadResult(messages, exceeded=True)
            if not message.get("more_body", False):
                return BodyReadResult(messages)

    @staticmethod
    async def _reject(send: Send) -> None:
        body = json.dumps({"detail": "O pedido excede o limite de 16 KiB."}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
