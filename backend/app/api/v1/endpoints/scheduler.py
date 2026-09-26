from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.api import deps
from app.core.exceptions import AppError
from app.core.ratelimit import limiter
from app.scheduler.application.contracts import SchedulerTaskDispatcher
from app.scheduler.infrastructure import queries
from app.scheduler.infrastructure.jobs import (
    GenerationUnavailable,
    enqueue_generation,
    request_cancellation,
)
from app.scheduler.infrastructure.proposals import (
    ProposalConflict,
    approve_proposal,
    reject_proposal,
)
from app.scheduler.infrastructure.snapshot import SnapshotConfigurationError

logger = structlog.get_logger(__name__)

router = APIRouter()


def _now() -> datetime:
    return datetime.now(UTC)


def _raise_scheduler_error(
    *, kind: str, code: str, detail: str, public_context: dict | None = None
) -> None:
    raise AppError(
        kind=kind,
        code=code,
        detail=detail,
        public_context=public_context,
    )


async def _job_payload(db: AsyncSession, organization_id: int, job_id: int) -> dict:
    job = await queries.get_job(db, organization_id, job_id)
    if job is None:
        _raise_scheduler_error(
            kind="not_found",
            code="scheduler_job_not_found",
            detail="Generation job was not found.",
        )
    return job


@router.get("/status", response_model=schemas.SchedulerV1StatusRead)
async def get_scheduler_status(
    db: deps.DbSession,
    current_user: deps.ActiveActor,
) -> dict:
    """Read the current state, eligibility reasons and pending proposal."""
    return await queries.scheduler_status(db, current_user.organization_id, now_utc=_now())


@router.post(
    "/generate",
    response_model=schemas.SchedulerV1GenerateResponse,
    status_code=202,
)
@limiter.limit("5/minute")
async def generate_schedule(
    request: Request,
    payload: schemas.SchedulerV1GenerateRequest,
    db: deps.DbSession,
    current_user: deps.AdminActor,
    dispatcher: Annotated[SchedulerTaskDispatcher, Depends(deps.get_scheduler_task_dispatcher)],
) -> dict:
    """Admit one manual, idempotent generation request into the global queue."""
    try:
        outcome = await enqueue_generation(
            db,
            current_user.organization_id,
            idempotency_key=payload.idempotency_key,
            requested_by_membership_id=current_user.membership_id,
            now_utc=_now(),
            expected_input_revision=payload.expected_input_revision,
        )
    except SnapshotConfigurationError as exc:
        raise AppError(kind="validation", code=exc.code, detail=str(exc)) from exc
    except GenerationUnavailable as exc:
        raise AppError(
            kind="conflict",
            code=exc.code,
            detail=str(exc),
            public_context={
                "reasons": [reason.value for reason in exc.reasons],
                "blocker": exc.blocker.value if exc.blocker is not None else None,
                "job_id": exc.job_id,
            },
        ) from exc
    job = await _job_payload(db, current_user.organization_id, outcome.job.id)
    if outcome.created or job["status"] == "QUEUED":
        try:
            dispatcher.dispatch(
                organization_id=current_user.organization_id,
                job_id=outcome.job.id,
                task_id=f"scheduler-v1-job-{outcome.job.id}",
            )
        except Exception as dispatch_error:
            logger.exception(
                "scheduler_v1_dispatch_failed",
                organization_id=current_user.organization_id,
                job_id=outcome.job.id,
            )
            raise AppError(
                kind="unavailable",
                code="generation_dispatch_failed",
                detail="O pedido ficou em fila e será retomado automaticamente.",
                public_context={"job_id": outcome.job.id},
                public_retryable=True,
                diagnostic_metadata={"job_id": outcome.job.id},
            ) from dispatch_error
    return {"job": job}


@router.get(
    "/jobs/{job_id}",
    response_model=schemas.SchedulerV1JobRead,
    responses={404: {"description": "Generation job not found"}},
)
async def get_generation_job(
    job_id: int,
    db: deps.DbSession,
    current_user: deps.ActiveActor,
) -> dict:
    """Phase, result and summary of one generation request."""
    return await _job_payload(db, current_user.organization_id, job_id)


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=schemas.SchedulerV1CancelResponse,
    responses={404: {"description": "Generation job not found"}},
)
async def cancel_generation_job(
    job_id: int,
    db: deps.DbSession,
    current_user: deps.AdminActor,
) -> dict:
    """Request cancellation; repeated requests are idempotent."""
    try:
        await request_cancellation(db, current_user.organization_id, job_id, now_utc=_now())
    except LookupError as exc:
        _raise_scheduler_error(kind="not_found", code="scheduler_job_not_found", detail=str(exc))
    job = await _job_payload(db, current_user.organization_id, job_id)
    return {"job": job}


@router.get(
    "/drafts/current",
    response_model=schemas.SchedulerV1ProposalRead,
    responses={404: {"description": "No pending proposal"}},
)
async def get_current_proposal(
    db: deps.DbSession,
    current_user: deps.ActiveActor,
) -> dict:
    """Current pending proposal with product metrics and warnings."""
    proposal = await queries.current_proposal(db, current_user.organization_id, now_utc=_now())
    if proposal is None:
        _raise_scheduler_error(
            kind="not_found",
            code="scheduler_draft_not_found",
            detail="Não existe uma proposta pendente.",
        )
    return proposal


@router.get(
    "/drafts/{proposal_id}/diff",
    response_model=schemas.SchedulerV1ProposalDiffRead,
    responses={404: {"description": "Proposal not found"}},
)
async def get_proposal_diff(
    proposal_id: int,
    db: deps.DbSession,
    current_user: deps.ActiveActor,
) -> dict:
    """Physical changes and modular projection updates, separated."""
    diff = await queries.proposal_diff(db, current_user.organization_id, proposal_id)
    if diff is None:
        _raise_scheduler_error(
            kind="not_found",
            code="scheduler_draft_not_found",
            detail="Schedule proposal was not found.",
        )
    return diff


@router.post(
    "/drafts/{proposal_id}/approve",
    response_model=schemas.SchedulerV1ApproveResponse,
    responses={
        404: {"description": "Proposal not found"},
        409: {"description": "Proposal cannot be approved"},
    },
)
async def approve_proposal_endpoint(
    proposal_id: int,
    db: deps.DbSession,
    current_user: deps.AdminActor,
    payload: schemas.SchedulerV1ApproveRequest | None = None,
) -> dict:
    """Atomic approval with full revalidation of the current data."""
    try:
        result = await approve_proposal(
            db,
            organization_id=current_user.organization_id,
            proposal_id=proposal_id,
            decided_by_membership_id=current_user.membership_id,
            now_utc=_now(),
            expected_input_revision=(
                payload.expected_input_revision if payload is not None else None
            ),
        )
    except LookupError as exc:
        _raise_scheduler_error(kind="not_found", code="scheduler_draft_not_found", detail=str(exc))
    except ProposalConflict as exc:
        _raise_scheduler_error(
            kind="conflict",
            code=exc.code,
            detail=str(exc),
            public_context=exc.context,
        )
    return {
        "proposal_id": result.proposal_id,
        "status": "APPROVED",
        "active_version_id": result.active_version_id,
        "approved_at": result.approved_at,
    }


@router.post(
    "/drafts/{proposal_id}/reject",
    response_model=schemas.SchedulerV1RejectResponse,
    responses={
        404: {"description": "Proposal not found"},
        409: {"description": "Proposal cannot be rejected"},
    },
)
async def reject_proposal_endpoint(
    proposal_id: int,
    db: deps.DbSession,
    current_user: deps.AdminActor,
    payload: schemas.SchedulerV1RejectRequest | None = None,
) -> dict:
    """Audited rejection; it does not unlock an arbitrary reroll."""
    try:
        result = await reject_proposal(
            db,
            organization_id=current_user.organization_id,
            proposal_id=proposal_id,
            decided_by_membership_id=current_user.membership_id,
            reason=payload.reason if payload is not None else None,
            now_utc=_now(),
        )
    except LookupError as exc:
        _raise_scheduler_error(kind="not_found", code="scheduler_draft_not_found", detail=str(exc))
    except ProposalConflict as exc:
        _raise_scheduler_error(
            kind="conflict",
            code=exc.code,
            detail=str(exc),
            public_context=exc.context,
        )
    return {
        "proposal_id": result.proposal_id,
        "status": "REJECTED",
        "rejected_at": result.rejected_at,
    }
