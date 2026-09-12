import json
from types import SimpleNamespace

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError

from app.main import (
    global_exception_handler,
    http_error_handler,
    request_validation_error_handler,
)


def make_request(headers=()):
    if len(headers) == 2 and all(isinstance(item, str) for item in headers):
        headers = [headers]
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/example",
            "query_string": b"",
            "headers": [(key.lower().encode(), value.encode()) for key, value in headers],
            "server": ("test", 80),
            "client": ("127.0.0.1", 1),
            "scheme": "http",
        }
    )


async def test_http_exception_uses_safe_envelope_and_preserves_auth_header():
    response = await http_error_handler(
        make_request(("X-Request-ID", "SAFE12ABC789")),
        HTTPException(
            status_code=401,
            detail="Bearer secret-token and internal details",
            headers={"WWW-Authenticate": "Bearer"},
        ),
    )

    detail = json.loads(response.body)["detail"]
    assert detail["code"] == "authentication_required"
    assert detail["reference"] == "SAFE12ABC789"
    assert response.headers["X-Request-ID"] == "SAFE12ABC789"
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert b"secret-token" not in response.body


async def test_malformed_request_id_is_replaced():
    response = await http_error_handler(
        make_request(("X-Request-ID", "too-long-request-id")),
        HTTPException(status_code=404, detail="raw not found"),
    )

    detail = json.loads(response.body)["detail"]
    assert detail["code"] == "resource_not_found"
    assert len(detail["reference"]) == 12
    assert detail["reference"] != "too-long-request-id"


async def test_validation_errors_expose_only_safe_field_guidance():
    response = await request_validation_error_handler(
        make_request(),
        RequestValidationError(
            [
                {
                    "loc": ("body", "email"),
                    "msg": "Input should be a valid email; database password leaked",
                    "type": "value_error",
                }
            ]
        ),
    )

    detail = json.loads(response.body)["detail"]
    assert detail["code"] == "validation_error"
    assert detail["fields"] == {"email": "Valor inválido."}
    assert b"database password" not in response.body


async def test_global_exception_handler_hides_internal_error_details(monkeypatch):
    logged = {}

    def capture_error(event, **context):
        logged["event"] = event
        logged["context"] = context

    monkeypatch.setattr("app.main.logger.error", capture_error)
    request = SimpleNamespace(
        method="GET",
        url=SimpleNamespace(path="/api/v1/private"),
    )

    try:
        raise RuntimeError("Bearer production-secret-token")
    except RuntimeError as exc:
        response = await global_exception_handler(request, exc)

    assert response.status_code == 500
    detail = json.loads(response.body)["detail"]
    assert detail["code"] == "unexpected_error"
    assert detail["message"] == "Ocorreu um erro inesperado. Tente novamente."
    assert len(detail["reference"]) == 12
    assert response.headers["X-Request-ID"] == detail["reference"]
    assert b"production-secret-token" not in response.body
    assert logged["event"] == "unhandled_application_error"
    assert logged["context"]["request_id"] == detail["reference"]
    assert logged["context"]["method"] == "GET"
    assert logged["context"]["path"] == "/api/v1/private"
    assert logged["context"]["error_type"] == "RuntimeError"
    assert "error" not in logged["context"]
    assert "traceback" not in logged["context"]
    assert logged["context"]["exception_frames"]
    assert all(
        set(frame) == {"file", "function", "line"}
        for frame in logged["context"]["exception_frames"]
    )
    assert "production-secret-token" not in repr(logged)
