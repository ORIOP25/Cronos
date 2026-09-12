import pytest
from pydantic import ValidationError

from app.api.v1.endpoints.client_errors import report_client_error
from app.schemas import ClientErrorReport


def test_client_error_report_is_strict_and_public_safe():
    report = ClientErrorReport(
        reference="ABC123DEF456",
        category="chunk_load_error",
        revision="a1b2c3._-",
    )
    assert report.model_dump() == {
        "reference": "ABC123DEF456",
        "category": "chunk_load_error",
        "revision": "a1b2c3._-",
    }
    with pytest.raises(ValidationError):
        ClientErrorReport(
            reference="abc123def456",
            category="render_error",
            revision="main",
        )
    with pytest.raises(ValidationError):
        ClientErrorReport(
            reference="ABC123DEF456",
            category="render_error",
            revision="main",
            message="secret stack",
        )


@pytest.mark.asyncio
async def test_client_error_endpoint_returns_no_content(monkeypatch):
    logged = []
    monkeypatch.setattr(
        "app.api.v1.endpoints.client_errors.logger.info",
        lambda event, **context: logged.append((event, context)),
    )
    response = await report_client_error(
        object(),
        ClientErrorReport(reference="ABC123DEF456", category="render_error", revision="main"),
    )
    assert response.status_code == 204
    assert logged[0][0] == "client_error_reported"
    assert logged[0][1] == {
        "client_error_reference": "ABC123DEF456",
        "category": "render_error",
        "revision": "main",
    }
