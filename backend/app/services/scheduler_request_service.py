from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.scheduler_worker import run_schedule_generation_job_task
from app.services.preflight_service import _preflight_check
from app.services.scheduler_generation_service import (
    GenerationConfigurationError,
    GenerationSelectionError,
    SchedulerGenerationService,
)
from app.services.scheduler_job_service import SchedulerJobError, SchedulerJobService
from app.services.scheduler_state_service import SchedulerStateError


async def start_generation_request(
    payload: schemas.ScheduleGenerateRequest,
    db: AsyncSession,
    current_user: models.User,
) -> dict[str, int | str]:
    """Validate scheduler preflight, persist a generation job, and dispatch it."""
    organization_id = current_user.organization_id

    try:
        selection = await SchedulerGenerationService(db).select_strategy(
            organization_id,
            replace_pending_draft=payload.replace_pending_draft,
        )
    except GenerationConfigurationError as exc:
        preflight_errors, preflight_summary = await _preflight_check(
            db,
            organization_id,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "error": "preflight_failed",
                "problems": preflight_errors or [str(exc)],
                "preflight": jsonable_encoder(preflight_summary),
            },
        ) from exc
    except GenerationSelectionError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": exc.code,
                "message": str(exc),
                "pending_draft_id": exc.pending_draft_id,
            },
        ) from exc
    except SchedulerStateError as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": "scheduler_state_invalid", "message": str(exc)},
        ) from exc

    preflight_errors, preflight_summary = await _preflight_check(
        db,
        organization_id,
        selection.strategy,
        replace_pending_draft=payload.replace_pending_draft,
    )
    encoded_preflight = jsonable_encoder(preflight_summary)
    if preflight_errors:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "preflight_failed",
                "problems": preflight_errors,
                "preflight": encoded_preflight,
            },
        )

    jobs = SchedulerJobService(db)
    try:
        handle = await jobs.create_or_get_job(
            selection,
            requested_by_user_id=current_user.id,
            idempotency_key=payload.idempotency_key,
        )
        await db.commit()
    except SchedulerJobError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"error": exc.code, "message": str(exc)},
        ) from exc

    task_id = jobs.worker_task_id(handle.job.id)
    if handle.created:
        try:
            run_schedule_generation_job_task.apply_async(
                args=[handle.job.id],
                task_id=task_id,
            )
        except Exception as dispatch_error:
            await jobs.mark_dispatch_failed(
                organization_id,
                handle.job.id,
                f"Could not dispatch generation job: {dispatch_error}",
            )
            await db.commit()
            raise HTTPException(
                status_code=503,
                detail={
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
