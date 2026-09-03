from unittest.mock import AsyncMock, MagicMock

import pytest

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
