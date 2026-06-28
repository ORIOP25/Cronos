import asyncio
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app import models
from app.schemas import OnboardingRequest
from app.services.scheduler_state_service import SchedulerStateService

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
    changed_by_user_id: int | None = None,
) -> None:
    existing = await db.execute(
        select(models.OrganizationSettings).where(
            models.OrganizationSettings.organization_id == organization_id
        )
    )
    if existing.scalar_one_or_none():
        return

    settings = models.OrganizationSettings(
        organization_id=organization_id,
        school_start_date=data.school_start_date,
        school_hard_end_date=data.school_hard_end_date,
        repair_stability_window_days=1,
    )
    db.add(settings)

    grid_settings = models.OrganizationGridSettings(
        organization_id=organization_id,
        lunch_window_start=data.lunch_start,
        lunch_window_end=data.lunch_end,
        lunch_min_duration_minutes=data.lunch_min_duration,
    )
    db.add(grid_settings)

    await db.flush()
    state_service = SchedulerStateService(db)
    await state_service.get_or_create_active_state(
        organization_id,
        start_date=data.school_start_date,
        hard_end_date=data.school_hard_end_date,
    )
    await state_service.record_change(
        organization_id,
        entity_type="ONBOARDING_CONFIGURATION",
        entity_id=settings.id,
        operation=models.SchedulerStateChangeOperation.BULK_IMPORT,
        before=None,
        after={
            "school_start_date": settings.school_start_date,
            "school_hard_end_date": settings.school_hard_end_date,
            "lunch_window_start": grid_settings.lunch_window_start,
            "lunch_window_end": grid_settings.lunch_window_end,
            "lunch_min_duration_minutes": grid_settings.lunch_min_duration_minutes,
        },
        changed_by_user_id=changed_by_user_id,
        metadata={"repair_stability_window_days": settings.repair_stability_window_days},
    )
