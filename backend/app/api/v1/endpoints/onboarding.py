from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.schemas import OnboardingRequest, OnboardingStatusResponse
from app.services.organization_service import (
    complete_onboarding,
    mark_onboarding_complete_in_clerk,
)
from app.services.organization_service import (
    get_onboarding_status as svc_get_status,
)

router = APIRouter(tags=["onboarding"])


@router.get("/onboarding/status", response_model=OnboardingStatusResponse)
async def get_onboarding_status(
    current_user: deps.AdminActor,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
):
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization associated")

    is_complete, org_name = await svc_get_status(db, org_id)
    return OnboardingStatusResponse(
        onboarding_complete=is_complete,
        organization_name=org_name,
    )


@router.post("/onboarding")
async def submit_onboarding(
    data: OnboardingRequest,
    current_user: deps.AdminActor,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    clerk: deps.ClerkGatewayDep,
):
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization associated")

    await complete_onboarding(db, org_id, data, changed_by_membership_id=current_user.membership_id)
    await db.flush()

    if current_user.clerk_user_id:
        await mark_onboarding_complete_in_clerk(current_user.clerk_user_id, clerk)

    return {"status": "ok", "organization_id": org_id, "message": "Onboarding completo"}
