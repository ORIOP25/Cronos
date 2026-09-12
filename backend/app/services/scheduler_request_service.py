import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.core.auth import Actor
from app.core.exceptions import AppError
from app.db.tenant import set_async_tenant_context
from app.scheduler.domain.constraints import SchedulerConstraintPolicy
from app.services.availability_matrix_service import AvailabilityMatrixRepairService
from app.services.preflight_service import PreflightService
from app.services.scheduler_generation_service import (
    GenerationConfigurationError,
    GenerationSelectionError,
    SchedulerGenerationService,
)
from app.services.scheduler_job_service import (
    GenerationJobHandle,
    SchedulerJobError,
    SchedulerJobService,
)
from app.services.scheduler_state_service import SchedulerStateError

logger = structlog.get_logger(__name__)


async def persist_prepared_generation(db: AsyncSession) -> None:
    """Commit the durable job before handing it to an external dispatcher."""
    await db.commit()


async def persist_dispatch_failure(
    db: AsyncSession,
    *,
    organization_id: int,
    job_id: int,
    reason: str,
) -> None:
    """Persist a dispatch failure after the initial transaction has closed."""
    await set_async_tenant_context(db, organization_id)
    await SchedulerJobService(db).mark_dispatch_failed(organization_id, job_id, reason)
    await db.commit()


def _selection_conflict(exc: GenerationSelectionError | SchedulerStateError) -> AppError:
    if isinstance(exc, GenerationSelectionError):
        return AppError(
            kind="conflict",
            code=exc.code,
            detail=str(exc),
            metadata={
                "error": exc.code,
                "message": str(exc),
                "pending_draft_id": exc.pending_draft_id,
            },
            public_context={
                "pending_draft_id": exc.pending_draft_id,
            },
        )
    return AppError(
        kind="conflict",
        code="scheduler_state_invalid",
        detail=str(exc),
        metadata={"error": "scheduler_state_invalid", "message": str(exc)},
    )


async def prepare_generation_request(
    payload: schemas.ScheduleGenerateRequest,
    db: AsyncSession,
    current_user: Actor,
) -> GenerationJobHandle:
    """Validate scheduler preflight and persist a generation job."""
    organization_id = current_user.organization_id
    generation = SchedulerGenerationService(db)

    # 1. Repair missing availability cells within mutation transaction
    await AvailabilityMatrixRepairService.repair(db, organization_id=organization_id)
    await db.flush()

    try:
        selection = await generation.select_strategy(
            organization_id,
            replace_pending_draft=payload.replace_pending_draft,
        )
    except GenerationConfigurationError as exc:
        preflight_service = PreflightService(db)
        report = await preflight_service.evaluate(
            organization_id=organization_id,
            resolve_fingerprint=False,
        )
        raise AppError(
            kind="validation",
            code="preflight_failed",
            detail=str(exc),
            metadata={
                "error": "preflight_failed",
                "status": report.status,
                "report": report.model_dump(),
                "issues": [i.model_dump() for i in report.issues],
            },
            public_context={
                "status": report.status,
                "report": report.model_dump(),
                "issues": [i.model_dump() for i in report.issues],
            },
        ) from exc
    except (GenerationSelectionError, SchedulerStateError) as exc:
        raise _selection_conflict(exc) from exc

    stored_constraints = list(
        await db.scalars(
            select(models.Constraint)
            .where(models.Constraint.organization_id == organization_id)
            .order_by(models.Constraint.id)
        )
    )
    constraint_parse = SchedulerConstraintPolicy.parse(stored_constraints)
    if constraint_parse.configuration_violations:
        violation = constraint_parse.configuration_violations[0]
        logger.warning(
            "scheduler_constraint_preflight_rejected",
            rejection_code="configuration_invalid",
            constraint_type=violation.rule_type,
        )
        raise AppError(
            kind="conflict",
            code="SCHEDULER_CONSTRAINT_CONFIGURATION_INVALID",
            detail=violation.message,
            metadata={
                "error": "SCHEDULER_CONSTRAINT_CONFIGURATION_INVALID",
                "message": violation.message,
                "constraint_id": violation.constraint_id,
                "constraint_type": violation.rule_type,
            },
        )

    preflight_service = PreflightService(db)
    report = await preflight_service.evaluate(
        organization_id=organization_id,
        school_year_id=selection.school_year_id,
        strategy=selection.strategy,
        resolve_fingerprint=False,
    )
    if report.status == "BLOCKED" or any(i.severity == "BLOCKER" for i in report.issues):
        raise AppError(
            kind="validation",
            code="preflight_failed",
            detail="Scheduler preflight failed.",
            metadata={
                "error": "preflight_failed",
                "status": report.status,
                "report": report.model_dump(),
                "issues": [i.model_dump() for i in report.issues],
            },
            public_context={
                "status": report.status,
                "report": report.model_dump(),
                "issues": [i.model_dump() for i in report.issues],
            },
        )

    jobs = SchedulerJobService(db)
    try:
        handle = await jobs.create_or_get_job(
            selection,
            requested_by_membership_id=current_user.membership_id,
            idempotency_key=payload.idempotency_key,
        )
    except SchedulerJobError as exc:
        raise AppError(
            kind="conflict",
            code=exc.code,
            detail=str(exc),
            metadata={"error": exc.code, "message": str(exc)},
        ) from exc

    return handle
