import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.core.auth import Actor
from app.core.exceptions import AppError
from app.scheduler.application.contracts import SchedulerTaskDispatcher
from app.scheduler.domain.constraints import SchedulerConstraintPolicy
from app.services.availability_matrix_service import AvailabilityMatrixRepairService
from app.services.preflight_service import PreflightService
from app.services.scheduler_generation_service import (
    GenerationConfigurationError,
    GenerationSelectionError,
    SchedulerGenerationService,
)
from app.services.scheduler_job_service import SchedulerJobError, SchedulerJobService
from app.services.scheduler_state_service import SchedulerStateError

logger = structlog.get_logger(__name__)


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
        )
    return AppError(
        kind="conflict",
        code="scheduler_state_invalid",
        detail=str(exc),
        metadata={"error": "scheduler_state_invalid", "message": str(exc)},
    )


async def start_generation_request(
    payload: schemas.ScheduleGenerateRequest,
    db: AsyncSession,
    current_user: Actor,
    dispatcher: SchedulerTaskDispatcher,
) -> dict[str, int | str]:
    """Validate scheduler preflight, persist a generation job, and dispatch it."""
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
        report = await preflight_service.evaluate(organization_id=organization_id)
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

    task_id = jobs.worker_task_id(handle.job.id)
    if handle.created:
        try:
            dispatcher.dispatch(
                organization_id=organization_id,
                job_id=handle.job.id,
                task_id=task_id,
            )
        except Exception as dispatch_error:
            await jobs.mark_dispatch_failed(
                organization_id,
                handle.job.id,
                f"Could not dispatch generation job: {dispatch_error}",
            )
            raise AppError(
                kind="unavailable",
                code="generation_dispatch_failed",
                detail="Generation could not be queued.",
                metadata={
                    "error": "generation_dispatch_failed",
                    "message": "Generation could not be queued.",
                    "job_id": handle.job.id,
                },
            ) from dispatch_error

    return {
        "job_id": handle.job.id,
        "strategy": handle.job.strategy.value,
        "trigger_type": handle.job.trigger_type.value,
        "status": handle.job.job_status.value,
    }
