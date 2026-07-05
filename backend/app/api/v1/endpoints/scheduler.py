from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.api import deps
from app.services.scheduler_status_service import SchedulerStatusService
from app.services.scheduler_draft_service import (
    SchedulerDraftNotFoundError,
    SchedulerDraftService,
)
from app.services.scheduler_diff_service import SchedulerDiffService
from app.services.scheduler_approval_service import (
    DraftApprovalConflictError,
    DraftApprovalNotFoundError,
    SchedulerApprovalService,
)
from app.services.scheduler_lifecycle_service import (
    SchedulerLifecycleConflictError,
    SchedulerLifecycleNotFoundError,
    SchedulerLifecycleService,
)
from app.services.scheduler_job_service import (
    SchedulerJobNotFoundError,
    SchedulerJobService,
)
from app.services.scheduler_observability import emit_scheduler_job_event
from app.services.scheduler_request_service import start_generation_request
from app.core.ratelimit import limiter


router = APIRouter()


@router.post("/generate", response_model=schemas.SchedulerGenerateResponse)
@limiter.limit("5/minute")
async def generate_schedule(
    request: Request,
    payload: schemas.ScheduleGenerateRequest,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
):
    return await start_generation_request(payload, db, current_user)


@router.get(
    "/jobs/{job_id}",
    response_model=schemas.ScheduleGenerationJobResponse,
    responses={404: {"description": "Generation job not found"}},
)
async def get_generation_job(
    job_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)],
) -> models.ScheduleGenerationJob:
    try:
        return await SchedulerJobService(db).get_job(
            current_user.organization_id,
            job_id,
        )
    except SchedulerJobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=schemas.ScheduleGenerationCancelResponse,
    responses={404: {"description": "Generation job not found"}},
)
async def cancel_generation_job(
    job_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
) -> dict[str, int | str]:
    try:
        job = await SchedulerJobService(db).request_cancellation(
            current_user.organization_id,
            job_id,
        )
    except SchedulerJobNotFoundError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await db.commit()
    emit_scheduler_job_event("generation_cancellation_requested", job)
    return {"job_id": job.id, "job_status": job.job_status.value}


@router.get("/status", response_model=schemas.SchedulerStatusResponse)
async def get_scheduler_status(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)],
) -> schemas.SchedulerStatusResponse:
    status = await SchedulerStatusService(db).get_status(
        current_user.organization_id
    )
    return schemas.SchedulerStatusResponse.model_validate(status)


@router.get(
    "/drafts/current",
    response_model=schemas.ScheduleDraftSummaryResponse,
    responses={404: {"description": "No pending draft"}},
)
async def get_current_draft_summary(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)],
) -> schemas.ScheduleDraftSummaryResponse:
    try:
        summary = await SchedulerDraftService(db).current_summary(
            current_user.organization_id
        )
    except SchedulerDraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return schemas.ScheduleDraftSummaryResponse.model_validate(summary)


@router.get(
    "/drafts/{draft_id}",
    response_model=schemas.ScheduleDraftSummaryResponse,
    responses={404: {"description": "Draft not found"}},
)
async def get_draft_summary(
    draft_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)],
) -> schemas.ScheduleDraftSummaryResponse:
    try:
        summary = await SchedulerDraftService(db).summary(
            current_user.organization_id,
            draft_id,
        )
    except SchedulerDraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return schemas.ScheduleDraftSummaryResponse.model_validate(summary)


@router.get(
    "/drafts/{draft_id}/diff",
    response_model=list[schemas.ScheduleDraftDiffEntryResponse],
    responses={404: {"description": "Draft not found"}},
)
async def get_draft_diff(
    draft_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)],
) -> list[schemas.ScheduleDraftDiffEntryResponse]:
    rows = await SchedulerDiffService(db).list_diff(
        current_user.organization_id,
        draft_id,
    )
    if rows is None:
        raise HTTPException(status_code=404, detail="Schedule draft was not found.")
    return [
        schemas.ScheduleDraftDiffEntryResponse.model_validate(row)
        for row in rows
    ]


@router.post(
    "/drafts/{draft_id}/approve",
    response_model=schemas.ScheduleDraftApprovalResponse,
    responses={404: {"description": "Draft not found"}, 409: {"description": "Draft cannot be approved"}},
)
async def approve_draft(
    draft_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
) -> schemas.ScheduleDraftApprovalResponse:
    try:
        result = await SchedulerApprovalService(db).approve(
            current_user.organization_id,
            draft_id,
            decided_by_user_id=current_user.id,
        )
    except DraftApprovalNotFoundError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DraftApprovalConflictError as exc:
        # Only stale/invalid transitions intentionally persist an audit state.
        if exc.draft_state in (
            models.ScheduleDraftState.STALE,
            models.ScheduleDraftState.INVALIDATED,
        ):
            await db.commit()
        else:
            await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "draft_state": exc.draft_state.value},
        ) from exc
    except Exception:
        await db.rollback()
        raise
    await db.commit()
    return schemas.ScheduleDraftApprovalResponse.model_validate(result)


@router.post(
    "/drafts/{draft_id}/reject",
    response_model=schemas.ScheduleDraftRejectionResponse,
    responses={404: {"description": "Draft not found"}, 409: {"description": "Draft cannot be rejected"}},
)
async def reject_draft(
    draft_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
) -> schemas.ScheduleDraftRejectionResponse:
    try:
        result = await SchedulerLifecycleService(db).reject_draft(
            current_user.organization_id,
            draft_id,
            decided_by_user_id=current_user.id,
        )
    except SchedulerLifecycleNotFoundError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SchedulerLifecycleConflictError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    return schemas.ScheduleDraftRejectionResponse.model_validate(result)


@router.post(
    "/reset-year",
    response_model=schemas.SchedulerResetYearResponse,
    responses={404: {"description": "School year not found"}, 409: {"description": "Reset confirmation required"}},
)
async def reset_scheduler_year(
    payload: schemas.SchedulerResetYearRequest,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
) -> schemas.SchedulerResetYearResponse:
    try:
        result = await SchedulerLifecycleService(db).reset_year(
            current_user.organization_id,
            reset_by_user_id=current_user.id,
            confirmed=payload.confirmed,
        )
    except SchedulerLifecycleNotFoundError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SchedulerLifecycleConflictError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    return schemas.SchedulerResetYearResponse.model_validate(result)
