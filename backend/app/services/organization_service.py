from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app import models
from app.schemas import OnboardingRequest


async def complete_onboarding(
    db: AsyncSession,
    organization_id: int,
    data: OnboardingRequest,
) -> None:
    existing = await db.execute(
        select(models.OrganizationSettings).where(
            models.OrganizationSettings.organization_id == organization_id
        )
    )
    if existing.scalar_one_or_none():
        return

    db.add(models.OrganizationSettings(
        organization_id=organization_id,
        school_start_date=data.school_start_date,
        school_target_end_date=data.school_target_end_date,
        school_hard_end_date=data.school_hard_end_date,
        repair_stability_window_days=1,
    ))

    db.add(models.OrganizationGridSettings(
        organization_id=organization_id,
        lunch_window_start=data.lunch_start,
        lunch_window_end=data.lunch_end,
        lunch_min_duration_minutes=data.lunch_min_duration,
    ))

    await db.flush()
