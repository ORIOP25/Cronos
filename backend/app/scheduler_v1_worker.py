"""Celery entry point for the scheduler v1 global executor.

The message only wakes the executor. The database decides the next eligible
request, the advisory lock guarantees a single global solve, and a separate
connection keeps the heartbeat and the cancellation checks alive while the
search runs in a worker thread.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
from datetime import UTC, datetime

import structlog

from app.celery_worker import celery_app
from app.config import settings
from app.db.database import SessionLocal, engine_async
from app.db.tenant import set_async_tenant_context
from app.scheduler.application.publishing import (
    initial_proposal_payload,
    recovery_proposal_payload,
)
from app.scheduler.composition import generate_schedule, repair_published_schedule
from app.scheduler.domain.candidate import SchedulingStrategy
from app.scheduler.domain.quality import QUALITY_POLICY_VERSION
from app.scheduler.domain.results import (
    OUTCOME_CANCELLED,
    OUTCOME_COMPLETE,
    OUTCOME_FAILED,
    OUTCOME_INCONCLUSIVE,
    OUTCOME_INFEASIBLE,
    OUTCOME_INVALID_INPUT,
)
from app.scheduler.infrastructure.jobs import (
    AttemptState,
    JobClaim,
    claim_next_job,
    executor_lock_alive,
    finish_job,
    heartbeat_and_poll,
    reconcile_abandoned,
    release_executor_lock,
    try_acquire_executor_lock,
)
from app.scheduler.infrastructure.proposals import persist_proposal
from app.scheduler.infrastructure.snapshot import (
    SnapshotConfigurationError,
    load_snapshot,
)

logger = structlog.get_logger(__name__)

TASK_NAME = "scheduler.v1.run_next_job"
RECOVERY_ASSESSMENT_SECONDS = 20.0

_TERMINAL_BY_OUTCOME = {
    OUTCOME_CANCELLED: ("CANCELLED", "CANCELLED", "CANCELLED"),
    OUTCOME_INFEASIBLE: ("INFEASIBLE", "INFEASIBLE", "INFEASIBLE"),
    OUTCOME_INCONCLUSIVE: ("INCONCLUSIVE", "INCONCLUSIVE", "SEARCH_STOPPED"),
    OUTCOME_FAILED: ("FAILED", "FAILED", "FAILED"),
    OUTCOME_INVALID_INPUT: ("FAILED", "INVALID_INPUT", "INVALID_INPUT"),
}


def _now() -> datetime:
    return datetime.now(UTC)


async def process_next_jobs() -> dict[str, object]:
    """Acquire the global executor lock and drain the eligible queue."""
    lock = await try_acquire_executor_lock(engine_async)
    if lock is None:
        return {"status": "busy"}
    try:
        reconciled = 0
        async with SessionLocal() as db:
            reconciled = await reconcile_abandoned(
                db,
                stale_after_seconds=settings.SCHEDULER_V1_ABANDONED_SECONDS,
                now_utc=_now(),
            )
        processed: list[dict[str, object]] = []
        while True:
            async with SessionLocal() as db:
                claim = await claim_next_job(db, now_utc=_now())
            if claim is None:
                break
            processed.append(await _execute_claim(claim, lock))
        return {"status": "ok", "reconciled": reconciled, "processed": processed}
    finally:
        with contextlib.suppress(Exception):
            await release_executor_lock(lock)


async def _execute_claim(claim: JobClaim, lock_connection=None) -> dict[str, object]:
    try:
        async with SessionLocal() as db:
            await set_async_tenant_context(db, claim.organization_id)
            bundle = await load_snapshot(
                db,
                claim.organization_id,
                strategy=claim.strategy,
                now_utc=_now(),
                school_year_id=claim.school_year_id,
            )
    except SnapshotConfigurationError as exc:
        written = await _finish(claim, "FAILED", "INVALID_INPUT", exc.code)
        return {"job_id": claim.job_id, "status": written, "code": exc.code}
    cancel_event = threading.Event()
    monitor = asyncio.create_task(_monitor_attempt(claim, cancel_event, lock_connection))
    try:
        result = await asyncio.to_thread(
            _run_search,
            claim,
            bundle,
            cancel_event,
        )
    finally:
        monitor.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await monitor
    if result.outcome == OUTCOME_COMPLETE and result.candidate is not None:
        payload = _build_payload(claim, bundle, result)
        async with SessionLocal() as db:
            await set_async_tenant_context(db, claim.organization_id)
            outcome = await persist_proposal(
                db,
                organization_id=claim.organization_id,
                job_id=claim.job_id,
                attempt_token=claim.attempt_token,
                bundle=bundle,
                candidate=result.candidate,
                payload=payload,
                policy_version=_policy_version(claim, bundle),
                now_utc=_now(),
            )
        if outcome.proposal_id is not None:
            return {
                "job_id": claim.job_id,
                "status": "SUCCEEDED",
                "proposal_id": outcome.proposal_id,
            }
        return {"job_id": claim.job_id, "status": outcome.refused or "LOST"}
    status, result_code, stop_reason = _TERMINAL_BY_OUTCOME.get(
        result.outcome, ("FAILED", "SYSTEM_ERROR", "FAILED")
    )
    written = await _finish(claim, status, result_code, stop_reason)
    return {"job_id": claim.job_id, "status": written, "calculated": status}


def _run_search(claim: JobClaim, bundle, cancel_event: threading.Event):
    settings_values = {
        "time_limit_seconds": float(settings.SCHEDULER_V1_JOB_TIMEOUT_SECONDS),
        "num_workers": int(settings.SCHEDULER_V1_NUM_WORKERS),
        "random_seed": claim.job_id,
    }
    if claim.strategy is SchedulingStrategy.COMPLETE_GENERATION:
        return generate_schedule(
            bundle.snapshot,
            bundle.periods,
            assess_recovery=True,
            should_cancel=cancel_event.is_set,
            recovery_time_limit_seconds=RECOVERY_ASSESSMENT_SECONDS,
            **settings_values,
        )
    if bundle.policy is None or bundle.baseline is None:
        raise SnapshotConfigurationError(
            "ACTIVE_VERSION_REQUIRED", "Não existe horário publicado para reparar."
        )
    return repair_published_schedule(
        bundle.snapshot,
        bundle.periods,
        bundle.baseline,
        bundle.policy,
        should_cancel=cancel_event.is_set,
        **settings_values,
    )


def _build_payload(claim: JobClaim, bundle, result):
    if claim.strategy is SchedulingStrategy.ADAPTIVE_RECOVERY:
        return recovery_proposal_payload(
            bundle.snapshot,
            result.candidate,
            quality=result.quality,
            report=result.report,
            evidence=result.evidence,
            diagnoses=result.diagnoses,
        )
    return initial_proposal_payload(
        bundle.snapshot,
        result.candidate,
        quality=result.quality,
        report=result.report,
        evidence=result.evidence,
        recovery_status=(
            result.completion.recovery.status if result.completion is not None else "NOT_ASSESSED"
        ),
        recovery_message=(
            result.completion.recovery.message if result.completion is not None else ""
        ),
    )


def _policy_version(claim: JobClaim, bundle) -> str:
    if claim.strategy is SchedulingStrategy.ADAPTIVE_RECOVERY and bundle.policy is not None:
        return bundle.policy.version
    return QUALITY_POLICY_VERSION


async def _monitor_attempt(
    claim: JobClaim, cancel_event: threading.Event, lock_connection=None
) -> None:
    interval = max(0.5, float(settings.SCHEDULER_V1_HEARTBEAT_SECONDS))
    while True:
        await asyncio.sleep(interval)
        if lock_connection is not None and not await executor_lock_alive(lock_connection):
            # Losing the lock must stop the calculation and free the job. The
            # write is token-guarded, so a takeover is never overwritten.
            logger.error("scheduler_v1_lock_lost", job_id=claim.job_id)
            cancel_event.set()
            await _finish(claim, "FAILED", "LOCK_LOST", "LOCK_LOST")
            return
        try:
            async with SessionLocal() as db:
                await set_async_tenant_context(db, claim.organization_id)
                attempt = await heartbeat_and_poll(
                    db,
                    organization_id=claim.organization_id,
                    job_id=claim.job_id,
                    attempt_token=claim.attempt_token,
                    now_utc=_now(),
                )
                await db.commit()
        except Exception:
            logger.exception("scheduler_v1_heartbeat_failed", job_id=claim.job_id)
            cancel_event.set()
            return
        if attempt is not AttemptState.CONTINUE:
            cancel_event.set()
            return


async def _finish(claim: JobClaim, status: str, result_code: str, stop_reason: str | None) -> str:
    async with SessionLocal() as db:
        await set_async_tenant_context(db, claim.organization_id)
        written = await finish_job(
            db,
            organization_id=claim.organization_id,
            job_id=claim.job_id,
            attempt_token=claim.attempt_token,
            status=status,
            result_code=result_code,
            stop_reason=stop_reason,
            now_utc=_now(),
        )
        await db.commit()
        return written


@celery_app.task(name=TASK_NAME)
def run_next_scheduler_job_task() -> dict[str, object]:
    return asyncio.run(process_next_jobs())
