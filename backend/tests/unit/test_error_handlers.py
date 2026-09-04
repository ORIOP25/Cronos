import json
from types import SimpleNamespace

from app.main import global_exception_handler


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

    response = await global_exception_handler(
        request,
        RuntimeError("database password leaked in traceback"),
    )

    assert response.status_code == 500
    assert json.loads(response.body) == {"detail": "Ocorreu um erro inesperado. Tente novamente."}
    assert b"database password" not in response.body
    assert logged["event"] == "Unhandled application error"
    assert logged["context"]["method"] == "GET"
    assert logged["context"]["path"] == "/api/v1/private"
    assert logged["context"]["error_type"] == "RuntimeError"
    assert logged["context"]["error"] == "database password leaked in traceback"
    assert "RuntimeError: database password leaked in traceback" in logged["context"]["traceback"]
