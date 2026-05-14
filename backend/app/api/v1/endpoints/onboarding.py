from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.api.deps import get_current_active_admin, get_db
from app import models
from app.schemas import OnboardingRequest, OnboardingStatusResponse
from app.services.organization_service import complete_onboarding

router = APIRouter(tags=["onboarding"])


@router.get("/onboarding/status", response_model=OnboardingStatusResponse)
async def get_onboarding_status(
    current_user: models.User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization associated")

    result = await db.execute(
        select(models.OrganizationSettings).where(
            models.OrganizationSettings.organization_id == org_id
        )
    )
    settings = result.scalar_one_or_none()

    org_result = await db.execute(
        select(models.Organization).where(models.Organization.id == org_id)
    )
    org = org_result.scalar_one_or_none()

    return OnboardingStatusResponse(
        onboarding_complete=settings is not None,
        organization_name=org.name if org else None,
    )


@router.post("/onboarding", status_code=201)
async def submit_onboarding(
    data: OnboardingRequest,
    current_user: models.User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization associated")

    await complete_onboarding(db, org_id, data)
    await db.commit()

    return {"status": "ok", "organization_id": org_id, "message": "Onboarding completo"}
