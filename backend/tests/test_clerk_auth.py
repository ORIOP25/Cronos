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

    with patch("app.core.clerk._verify_clerk_request_sync") as mock_sync:
        mock_sync.return_value = mock_state
        result = await verify_clerk_request(mock_request)

    assert result.is_signed_in is True
    assert result.payload["sub"] == "user_123"
    assert result.payload["o"]["id"] == "org_456"


# ── T2: Token inválido ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_authenticate_request_invalid_token():
    from app.core.clerk import verify_clerk_request

    mock_request = MagicMock()
    mock_state = RequestState(status=AuthStatus.SIGNED_OUT)

    with patch("app.core.clerk._verify_clerk_request_sync") as mock_sync:
        mock_sync.return_value = mock_state
        result = await verify_clerk_request(mock_request)

    assert result.is_signed_in is False


# ── T3: Token expirado ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_authenticate_request_expired_token():
    from app.core.clerk import verify_clerk_request

    mock_request = MagicMock()
    mock_state = RequestState(status=AuthStatus.SIGNED_OUT)

    with patch("app.core.clerk._verify_clerk_request_sync") as mock_sync:
        mock_sync.return_value = mock_state
        result = await verify_clerk_request(mock_request)

    assert result.is_signed_in is False


# ── T4: Wrong authorized party ──────────────────────────────────
@pytest.mark.asyncio
async def test_authenticate_request_wrong_azp():
    from app.core.clerk import verify_clerk_request

    mock_request = MagicMock()
    mock_state = RequestState(status=AuthStatus.SIGNED_OUT)

    with patch("app.core.clerk._verify_clerk_request_sync") as mock_sync:
        mock_sync.return_value = mock_state
        result = await verify_clerk_request(mock_request)

    assert result.is_signed_in is False


# ── T5: User from DB ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_get_current_user_from_db(db_session):
    from app.api.deps import get_current_user
    from app import models

    org = models.Organization(name="TestOrg", clerk_org_id="org_1", plan_status="active")
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


@pytest.mark.asyncio
async def test_get_current_active_user_rejects_token_org_without_membership(db_session):
    from fastapi import HTTPException
    from app.api.deps import get_current_active_user
    from app import models
    from tests.conftest import ensure_membership_capabilities

    org_a = models.Organization(name="Org A", clerk_org_id="org_a", plan_status="active")
    org_b = models.Organization(name="Org B", clerk_org_id="org_b", plan_status="active")
    db_session.add_all([org_a, org_b])
    await db_session.flush()

    user = models.User(
        clerk_user_id="user_mismatch",
        email="mismatch@example.com",
        role="admin",
        organization_id=org_a.id,
    )
    db_session.add(user)
    await db_session.flush()
    await ensure_membership_capabilities(
        db_session,
        organization_id=org_a.id,
        user=user,
        capabilities=[models.MembershipCapability.admin],
        expected_clerk_role=models.ClerkOrganizationRole.admin,
    )
    await db_session.commit()

    mock_request = MagicMock()
    mock_request.state.current_organization_id = org_b.id
    mock_request.state.current_clerk_org_role = "admin"
    with pytest.raises(HTTPException) as exc:
        await get_current_active_user(mock_request, db_session, user)

    assert exc.value.status_code == 403
    assert exc.value.detail == "Active organization membership required"


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
    mock_user.organization_id = 1

    with patch("app.api.deps.get_clerk_payload") as mock_payload, \
         patch.object(clerk_sync, "sync_user_from_clerk_api") as mock_sync, \
         patch.object(clerk_sync, "sync_organization_from_clerk_api") as mock_org_sync:
        mock_payload.return_value = {"sub": "user_new", "o": {"id": "org_1", "rol": "admin"}}
        mock_sync.return_value = mock_user
        mock_org = MagicMock()
        mock_org.id = 1
        mock_org.clerk_org_id = "org_1"
        mock_org_sync.return_value = mock_org

        mock_request = MagicMock()
        result = await get_current_user(mock_request, db_session)

    assert result.clerk_user_id == "user_new"
    mock_sync.assert_called_once_with(
        db_session,
        "user_new",
        organization_id=1,
        role="admin",
    )


# ── T7: Admin access ────────────────────────────────────────────
def test_get_current_active_admin():
    from app.api.deps import get_current_active_admin
    from app import models

    mock_user = MagicMock()
    mock_user.role = "admin"
    mock_user.is_active = True
    mock_user.is_superuser = False
    mock_user._membership_capabilities = {models.MembershipCapability.admin}

    result = get_current_active_admin(mock_user)
    assert result == mock_user


# ── T8: Teacher rejected ────────────────────────────────────────
def test_get_current_active_admin_rejects_teacher():
    from fastapi import HTTPException
    from app.api.deps import get_current_active_admin
    from app import models

    mock_user = MagicMock()
    mock_user.role = "teacher"
    mock_user.is_active = True
    mock_user.is_superuser = False
    mock_user._membership_capabilities = {models.MembershipCapability.teacher}

    with pytest.raises(HTTPException) as exc:
        get_current_active_admin(mock_user)
    assert exc.value.status_code == 403


# ── T6b: Fallback BAPI fails ────────────────────────────────────
@pytest.mark.asyncio
async def test_get_current_user_fallback_bapi_fails(db_session):
    from fastapi import HTTPException
    from app.api.deps import get_current_user
    from app.services import clerk_sync

    with patch("app.api.deps.get_clerk_payload") as mock_payload, \
         patch.object(clerk_sync, "sync_organization_from_clerk_api") as mock_org, \
         patch.object(clerk_sync, "sync_user_from_clerk_api") as mock_user:
        mock_payload.return_value = {"sub": "user_fail", "o": {"id": "org_x", "rol": "admin"}}
        mock_org.return_value = None
        mock_user.return_value = None

        mock_request = MagicMock()
        with pytest.raises(HTTPException) as exc:
            await get_current_user(mock_request, db_session)
        assert exc.value.status_code == 403
        assert "Organization mismatch" in str(exc.value.detail)
        mock_user.assert_not_called()


# ── T20a: parse_role edge cases ─────────────────────────────────
def test_parse_role_admin():
    from app.services.clerk_sync import parse_role
    assert parse_role("admin") == "admin"


def test_parse_role_member():
    from app.services.clerk_sync import parse_role
    assert parse_role("member") == "teacher"


def test_parse_role_none():
    from app.services.clerk_sync import parse_role
    assert parse_role(None) == "teacher"


def test_parse_role_unknown():
    from app.services.clerk_sync import parse_role
    assert parse_role("invalid_role") == "teacher"


# ── FASE 1.2: Claims inválidas no token Clerk ───────────────────

@pytest.mark.asyncio
async def test_get_current_user_missing_sub(db_session):
    """Token sem 'sub' → 401 'No user ID in token'."""
    from fastapi import HTTPException
    from app.api.deps import get_current_user

    with patch("app.api.deps.get_clerk_payload") as mock_payload:
        mock_payload.return_value = {"o": {"id": "org_1", "rol": "admin"}}

        mock_request = MagicMock()
        with pytest.raises(HTTPException) as exc:
            await get_current_user(mock_request, db_session)
        assert exc.value.status_code == 401
        assert "No user ID" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_get_current_user_missing_org_in_token(db_session):
    """Token sem org nao pode criar utilizador sem tenant."""
    from fastapi import HTTPException
    from app.api.deps import get_current_user
    from app.services import clerk_sync

    with patch("app.api.deps.get_clerk_payload") as mock_payload, \
         patch.object(clerk_sync, "sync_user_from_clerk_api") as mock_sync:
        mock_payload.return_value = {"sub": "user_no_org"}

        mock_request = MagicMock()
        with pytest.raises(HTTPException) as exc:
            await get_current_user(mock_request, db_session)

    assert exc.value.status_code == 403
    assert exc.value.detail == "Organization required"
    mock_sync.assert_not_called()


@pytest.mark.asyncio
async def test_get_current_user_null_org_id(db_session):
    """Token com org nula nao pode criar utilizador sem tenant."""
    from fastapi import HTTPException
    from app.api.deps import get_current_user
    from app.services import clerk_sync

    with patch("app.api.deps.get_clerk_payload") as mock_payload, \
         patch.object(clerk_sync, "sync_user_from_clerk_api") as mock_sync:
        mock_payload.return_value = {"sub": "user_null_org", "o": {"id": None, "rol": "admin"}}

        mock_request = MagicMock()
        with pytest.raises(HTTPException) as exc:
            await get_current_user(mock_request, db_session)

    assert exc.value.status_code == 403
    assert exc.value.detail == "Organization required"
    mock_sync.assert_not_called()


@pytest.mark.asyncio
async def test_get_current_user_unknown_role_string(db_session):
    """Token com role desconhecida → parse_role retorna 'teacher' (default)."""
    from app.api.deps import get_current_user
    from app.services import clerk_sync
    from app.models import UserRole

    mock_user = MagicMock()
    mock_user.clerk_user_id = "user_unknown_role"
    mock_user.email = "unknown@test.com"
    mock_user.is_active = True
    mock_user.role = UserRole.teacher.value
    mock_user.organization_id = 1

    with patch("app.api.deps.get_clerk_payload") as mock_payload, \
         patch.object(clerk_sync, "sync_user_from_clerk_api") as mock_sync, \
         patch.object(clerk_sync, "sync_organization_from_clerk_api") as mock_org_sync:
        mock_payload.return_value = {"sub": "user_unknown_role", "o": {"id": "org_1", "rol": "org:superadmin"}}
        mock_sync.return_value = mock_user
        mock_org = MagicMock()
        mock_org.id = 1
        mock_org.clerk_org_id = "org_1"
        mock_org_sync.return_value = mock_org

        mock_request = MagicMock()
        result = await get_current_user(mock_request, db_session)

    assert result.role == UserRole.teacher.value
    mock_sync.assert_called_once_with(
        db_session,
        "user_unknown_role",
        organization_id=1,
        role="org:superadmin",
    )


@pytest.mark.asyncio
async def test_clerk_payload_not_signed_in():
    """verify_clerk_request retorna is_signed_in=False → get_clerk_payload levanta 401."""
    from fastapi import HTTPException
    from app.api.deps import get_clerk_payload
    from app.core.clerk import verify_clerk_request

    mock_request = MagicMock()
    with patch("app.api.deps.verify_clerk_request") as mock_verify:
        from clerk_backend_api.security.types import RequestState, AuthStatus
        mock_state = RequestState(status=AuthStatus.SIGNED_OUT)
        mock_verify.return_value = mock_state

        with pytest.raises(HTTPException) as exc:
            await get_clerk_payload(mock_request)
        assert exc.value.status_code == 401
        assert "Not authenticated" in str(exc.value.detail)


# ── FASE 1.6: Organização sem clerk_org_id ────────────────────

@pytest.mark.asyncio
async def test_get_current_user_org_without_clerk_org_id(db_session):
    """Org local sem clerk_org_id → BAPI fallback sync encontra e atualiza."""
    from app.api.deps import get_current_user
    from app.services import clerk_sync
    from app import models

    # Criar org local sem clerk_org_id (pré-migração)
    org = models.Organization(name="Org Pre-Migration", clerk_org_id=None, plan_status="active")
    db_session.add(org)
    await db_session.flush()
    org_id = org.id
    await db_session.commit()

    # Mock do fallback BAPI
    with patch("app.api.deps.get_clerk_payload") as mock_payload, \
         patch.object(clerk_sync, "sync_user_from_clerk_api") as mock_user_sync, \
         patch.object(clerk_sync, "sync_organization_from_clerk_api") as mock_org_sync:

        mock_payload.return_value = {
            "sub": "user_pre_mig",
            "o": {"id": "org_clerk_abc", "rol": "admin"},
        }

        mock_org_result = MagicMock()
        mock_org_result.id = org_id
        mock_org_result.name = "Org Pre-Migration Updated"
        mock_org_result.clerk_org_id = "org_clerk_abc"
        mock_org_sync.return_value = mock_org_result

        mock_user_result = MagicMock()
        mock_user_result.clerk_user_id = "user_pre_mig"
        mock_user_result.email = "pre@test.com"
        mock_user_result.is_active = True
        mock_user_result.role = "admin"
        mock_user_result.organization_id = org_id
        mock_user_sync.return_value = mock_user_result

        mock_request = MagicMock()
        result = await get_current_user(mock_request, db_session)

        assert result is not None
        mock_org_sync.assert_called_once_with(db_session, "org_clerk_abc")
        mock_user_sync.assert_called_once_with(
            db_session,
            "user_pre_mig",
            organization_id=org_id,
            role="admin",
        )
