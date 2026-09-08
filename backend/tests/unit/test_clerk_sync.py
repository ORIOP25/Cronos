from unittest.mock import AsyncMock, MagicMock

import pytest

from app import models
from app.services import clerk_sync
from app.services.clerk_sync import clerk_user_exists


class DummyClerkError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@pytest.mark.asyncio
async def test_clerk_user_exists_returns_true_on_success():
    gateway = MagicMock()
    gateway.sdk.users.get_async = AsyncMock(return_value={"id": "user_123"})

    result = await clerk_user_exists("user_123", gateway=gateway)
    assert result is True


@pytest.mark.asyncio
async def test_clerk_user_exists_returns_false_only_on_structured_404():
    gateway = MagicMock()
    gateway.sdk.users.get_async = AsyncMock(
        side_effect=DummyClerkError("User not found", status_code=404)
    )

    result = await clerk_user_exists("user_123", gateway=gateway)
    assert result is False


@pytest.mark.asyncio
async def test_clerk_user_exists_returns_none_on_500_even_with_404_in_message():
    gateway = MagicMock()
    # Message has "404" in text, but status code is 500 (e.g. proxy trace or internal ID)
    gateway.sdk.users.get_async = AsyncMock(
        side_effect=DummyClerkError("Error 40412 upstream service error", status_code=500)
    )

    result = await clerk_user_exists("user_123", gateway=gateway)
    assert result is None


@pytest.mark.asyncio
async def test_clerk_user_exists_returns_none_on_403_forbidden():
    gateway = MagicMock()
    gateway.sdk.users.get_async = AsyncMock(
        side_effect=DummyClerkError("Forbidden", status_code=403)
    )

    result = await clerk_user_exists("user_123", gateway=gateway)
    assert result is None


@pytest.mark.asyncio
async def test_clerk_user_exists_returns_none_on_429_rate_limit():
    gateway = MagicMock()
    gateway.sdk.users.get_async = AsyncMock(
        side_effect=DummyClerkError("Too Many Requests", status_code=429)
    )

    result = await clerk_user_exists("user_123", gateway=gateway)
    assert result is None


@pytest.mark.asyncio
async def test_clerk_user_exists_returns_none_on_timeout_with_404_string():
    gateway = MagicMock()
    gateway.sdk.users.get_async = AsyncMock(
        side_effect=TimeoutError("Connection to port 4040 timed out")
    )

    result = await clerk_user_exists("user_123", gateway=gateway)
    assert result is None


@pytest.mark.asyncio
async def test_clerk_provider_error_log_excludes_raw_payload(monkeypatch):
    gateway = MagicMock()
    gateway.sdk.users.get_async = AsyncMock(
        side_effect=DummyClerkError("Bearer provider-secret-payload", status_code=500)
    )
    events = []
    monkeypatch.setattr(
        clerk_sync.logger,
        "error",
        lambda *args, **kwargs: events.append((args, kwargs)),
    )

    result = await clerk_user_exists("user_123", gateway=gateway)

    assert result is None
    assert "provider-secret-payload" not in repr(events)
    assert events[0][1]["error_type"] == "DummyClerkError"
    assert events[0][1]["exception_frames"]


@pytest.mark.asyncio
async def test_organization_sync_does_not_fall_back_to_generic_identity_repair(monkeypatch):
    organization = models.Organization(id=7, name="Tenant", clerk_org_id="org_7")
    db = MagicMock()
    db.get = AsyncMock(return_value=organization)
    safe_reconciliation = AsyncMock(return_value=None)
    generic_repair = AsyncMock()
    monkeypatch.setattr(
        clerk_sync.member_reconciliation_service,
        "reconcile_first_login_by_email",
        safe_reconciliation,
    )
    monkeypatch.setattr(clerk_sync, "ensure_user_exists", generic_repair)
    monkeypatch.setattr(
        clerk_sync,
        "fetch_clerk_user_profile",
        AsyncMock(return_value=clerk_sync.ClerkUserProfile("member@example.com", "Member")),
    )

    result = await clerk_sync.sync_user_from_clerk_api(
        db,
        "user_7",
        organization_id=7,
        role="member",
    )

    assert result is None
    safe_reconciliation.assert_awaited_once()
    generic_repair.assert_not_awaited()
