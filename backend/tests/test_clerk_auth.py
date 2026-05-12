import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from clerk_backend_api.security.types import RequestState, AuthStatus


# ── T1: Token válido ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_authenticate_request_valid_token():
    from app.core.clerk import verify_clerk_request

    mock_request = MagicMock()
    mock_state = RequestState(
        status=AuthStatus.SIGNED_IN,
        payload={"sub": "user_123", "o": {"id": "org_456", "rol": "admin"}},
    )

    with patch("app.core.clerk.get_clerk_sdk") as mock_sdk:
        mock_sdk.return_value.authenticate_request.return_value = mock_state
        result = verify_clerk_request(mock_request)

    assert result.is_signed_in is True
    assert result.payload["sub"] == "user_123"
    assert result.payload["o"]["id"] == "org_456"


# ── T2: Token inválido ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_authenticate_request_invalid_token():
    from app.core.clerk import verify_clerk_request

    mock_request = MagicMock()
    mock_state = RequestState(status=AuthStatus.SIGNED_OUT)

    with patch("app.core.clerk.get_clerk_sdk") as mock_sdk:
        mock_sdk.return_value.authenticate_request.return_value = mock_state
        result = verify_clerk_request(mock_request)

    assert result.is_signed_in is False


# ── T3: Token expirado ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_authenticate_request_expired_token():
    from app.core.clerk import verify_clerk_request

    mock_request = MagicMock()
    mock_state = RequestState(status=AuthStatus.SIGNED_OUT)

    with patch("app.core.clerk.get_clerk_sdk") as mock_sdk:
        mock_sdk.return_value.authenticate_request.return_value = mock_state
        result = verify_clerk_request(mock_request)

    assert result.is_signed_in is False


# ── T4: Wrong authorized party ──────────────────────────────────
@pytest.mark.asyncio
async def test_authenticate_request_wrong_azp():
    from app.core.clerk import verify_clerk_request

    mock_request = MagicMock()
    mock_state = RequestState(status=AuthStatus.SIGNED_OUT)

    with patch("app.core.clerk.get_clerk_sdk") as mock_sdk:
        mock_sdk.return_value.authenticate_request.return_value = mock_state
        result = verify_clerk_request(mock_request)

    assert result.is_signed_in is False


# ── T5: User from DB ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_get_current_user_from_db(db_session):
    from app.api.deps import get_current_user
    from app import models

    org = models.Organization(name="TestOrg", plan_status="active")
    db_session.add(org)
    await db_session.flush()

    user = models.User(
        clerk_user_id="user_123",
        email="test@example.com",
        role="admin",
        organization_id=org.id,
    )
    db_session.add(user)
    await db_session.commit()

    with patch("app.api.deps.get_clerk_payload") as mock_payload:
        mock_payload.return_value = {"sub": "user_123", "o": {"id": "org_1", "rol": "admin"}}
        mock_request = MagicMock()
        result = await get_current_user(mock_request, db_session)

    assert result.clerk_user_id == "user_123"
    assert result.email == "test@example.com"


# ── T6: User NOT in DB → fallback creates ───────────────────────
@pytest.mark.asyncio
async def test_get_current_user_fallback_creates_user(db_session):
    from app.api.deps import get_current_user
    from app.services import clerk_sync

    mock_user = MagicMock()
    mock_user.clerk_user_id = "user_new"
    mock_user.email = "new@example.com"
    mock_user.is_active = True
    mock_user.role = "admin"

    with patch("app.api.deps.get_clerk_payload") as mock_payload, \
         patch.object(clerk_sync, "sync_user_from_clerk_api") as mock_sync, \
         patch.object(clerk_sync, "sync_organization_from_clerk_api"):
        mock_payload.return_value = {"sub": "user_new", "o": {"id": "org_1", "rol": "admin"}}
        mock_sync.return_value = mock_user

        mock_request = MagicMock()
        result = await get_current_user(mock_request, db_session)

    assert result.clerk_user_id == "user_new"
    mock_sync.assert_called_once_with(db_session, "user_new")


# ── T7: Admin access ────────────────────────────────────────────
def test_get_current_active_admin():
    from app.api.deps import get_current_active_admin

    mock_user = MagicMock()
    mock_user.role = "admin"
    mock_user.is_active = True
    mock_user.is_superuser = False

    result = get_current_active_admin(mock_user)
    assert result == mock_user


# ── T8: Teacher rejected ────────────────────────────────────────
def test_get_current_active_admin_rejects_teacher():
    from fastapi import HTTPException
    from app.api.deps import get_current_active_admin

    mock_user = MagicMock()
    mock_user.role = "teacher"
    mock_user.is_active = True
    mock_user.is_superuser = False

    with pytest.raises(HTTPException) as exc:
        get_current_active_admin(mock_user)
    assert exc.value.status_code == 403
