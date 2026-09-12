import json

import pytest
from httpx import ASGITransport, AsyncByteStream, AsyncClient

from app.middleware.request_body_limit import RequestBodyLimitMiddleware


class ChunkedBody(AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk


class ProbeApp:
    def __init__(self):
        self.calls = 0
        self.received = b""

    async def __call__(self, scope, receive, send):
        self.calls += 1
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            self.received += message.get("body", b"")
            if not message.get("more_body", False):
                break
        body = json.dumps({"size": len(self.received)}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": body})


def make_client(probe, *, default=100, overrides=None):
    app = RequestBodyLimitMiddleware(
        probe,
        default_max_bytes=default,
        path_limits=overrides,
    )
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_content_length_rejection_happens_before_downstream():
    probe = ProbeApp()
    async with make_client(probe) as client:
        response = await client.post("/api/data", content=b"x" * 101)

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "request_body_too_large"
    assert response.json()["detail"]["message"] == "O pedido excede o limite permitido."
    assert response.headers["X-Request-ID"] == response.json()["detail"]["reference"]
    assert probe.calls == 0


@pytest.mark.asyncio
async def test_rejection_reuses_state_reference_before_header_and_logs_without_body(monkeypatch):
    probe = ProbeApp()
    events = []

    def capture(event, **context):
        events.append((event, context))

    monkeypatch.setattr("app.middleware.request_body_limit.logger.info", capture)
    middleware = RequestBodyLimitMiddleware(probe, default_max_bytes=10)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/private",
        "query_string": b"secret=query",
        "headers": [(b"x-request-id", b"LOWERcase12")],
        "state": {"request_reference": "STATE12ABC34"},
    }
    sent = []

    async def send(message):
        sent.append(message)

    await middleware._reject(scope, send)

    body = sent[1]["body"]
    assert scope["state"]["request_reference"] == "STATE12ABC34"
    assert b"STATE12ABC34" in body
    assert b"secret" not in body
    assert events == [
        (
            "request_rejected",
            {
                "request_id": "STATE12ABC34",
                "code": "request_body_too_large",
                "status_code": 413,
                "method": "POST",
                "path": "/api/private",
            },
        )
    ]


@pytest.mark.asyncio
async def test_chunked_body_cannot_bypass_the_limit_with_a_small_content_length():
    probe = ProbeApp()
    stream = ChunkedBody([b"x" * 60, b"y" * 41])
    async with make_client(probe) as client:
        request = client.build_request("POST", "/api/data", content=stream)
        request.headers["content-length"] = "1"
        response = await client.send(request)

    assert response.status_code == 413
    assert probe.calls == 0


@pytest.mark.asyncio
async def test_exact_boundary_is_replayed_unchanged():
    probe = ProbeApp()
    async with make_client(probe) as client:
        response = await client.post("/api/data", content=b"x" * 100)

    assert response.status_code == 200
    assert response.json() == {"size": 100}
    assert probe.calls == 1
    assert probe.received == b"x" * 100


@pytest.mark.asyncio
async def test_path_override_applies_only_to_the_configured_route():
    probe = ProbeApp()
    async with make_client(
        probe,
        default=100,
        overrides={("POST", "/api/contact"): 16},
    ) as client:
        contact = await client.post("/api/contact", content=b"x" * 17)
        ordinary = await client.post("/api/data", content=b"x" * 17)

    assert contact.status_code == 413
    assert ordinary.status_code == 200
    assert ordinary.json() == {"size": 17}
    assert probe.calls == 1
