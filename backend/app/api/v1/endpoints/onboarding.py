from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_active_admin, get_db
from app import models
from app.schemas import OnboardingRequest, OnboardingStatusResponse
from app.services.organization_service import (
    complete_onboarding,
    get_onboarding_status as svc_get_status,
    mark_onboarding_complete_in_clerk,
)

router = APIRouter(tags=["onboarding"])


@router.get("/onboarding/status", response_model=OnboardingStatusResponse)
async def get_onboarding_status(
    current_user: Annotated[models.User, Depends(get_current_active_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
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
    current_user: Annotated[models.User, Depends(get_current_active_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization associated")

    await complete_onboarding(db, org_id, data)
    await db.commit()

    if current_user.clerk_user_id:
        await mark_onboarding_complete_in_clerk(current_user.clerk_user_id)

    return {"status": "ok", "organization_id": org_id, "message": "Onboarding completo"}
