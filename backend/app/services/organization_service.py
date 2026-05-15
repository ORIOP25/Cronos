import asyncio
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app import models
from app.schemas import OnboardingRequest

logger = structlog.get_logger(__name__)


async def get_onboarding_status(db: AsyncSession, organization_id: int) -> tuple[bool, str | None]:
    result = await db.execute(
        select(models.OrganizationSettings).where(
            models.OrganizationSettings.organization_id == organization_id
        )
    )
    settings = result.scalar_one_or_none()

    org_result = await db.execute(
        select(models.Organization).where(models.Organization.id == organization_id)
    )
    org = org_result.scalar_one_or_none()

    return settings is not None, org.name if org else None


async def mark_onboarding_complete_in_clerk(clerk_user_id: str) -> None:
    from app.core.clerk import get_clerk_sdk
    sdk = get_clerk_sdk()
    try:
        await asyncio.to_thread(
            lambda: sdk.users.update(
                user_id=clerk_user_id,
                public_metadata={"onboardingComplete": True},
            )
        )
        logger.info("Clerk public_metadata actualizado", clerk_user_id=clerk_user_id)
    except Exception as e:
        logger.warning("Falha ao actualizar Clerk public_metadata", clerk_user_id=clerk_user_id, error=str(e))


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
