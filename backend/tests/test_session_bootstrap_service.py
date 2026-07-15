import pytest

from app.services.session_bootstrap_service import (
    ActiveOrganizationAccessDeniedError,
    ActiveOrganizationRequiredError,
    SessionBootstrapService,
)


pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_bootstrap_requires_active_organization_claim_before_database_access():
    service = SessionBootstrapService(object())
    with pytest.raises(ActiveOrganizationRequiredError):
        await service.bootstrap({"sub": "user_1"})


@pytest.mark.asyncio
async def test_bootstrap_requires_admin_role_before_database_access():
    service = SessionBootstrapService(object())
    with pytest.raises(ActiveOrganizationAccessDeniedError):
        await service.bootstrap({"sub": "user_1", "o": {"id": "org_1", "rol": "org:member"}})
