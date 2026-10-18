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
from time import monotonic

import structlog

# The default-queue worker executes these periodic tasks, so it registers them.
# Beat must not import them.
from app import member_reconciliation_worker, privacy_maintenance_worker  # noqa: F401
from app.celery_worker import celery_app
from app.config import settings
from app.db.database import SessionLocal, engine_async
from app.db.tenant import set_async_tenant_context
from app.scheduler.application.publishing import (
    diagnostics_summary,
    initial_proposal_payload,
    recovery_proposal_payload,
)
from app.scheduler.composition import generate_schedule, repair_published_schedule
from app.scheduler.domain.candidate import SchedulingStrategy
from app.scheduler.domain.diagnostics import Diagnosis, DiagnosisCode, EvidenceKind
from app.scheduler.domain.quality import QUALITY_POLICY_VERSION
from app.scheduler.domain.results import (
    OUTCOME_CANCELLED,
    OUTCOME_COMPLETE,
    OUTCOME_FAILED,
    OUTCOME_INCONCLUSIVE,
    OUTCOME_INFEASIBLE,
    OUTCOME_INVALID_INPUT,
)
from app.scheduler.infrastructure import diagnostics
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


def _diagnosis_value(value) -> str:
    return str(getattr(value, "value", value))


_JOINT_NO_COMMON_TIME = DiagnosisCode.JOINT_NO_COMMON_TIME.value


def _proven_diagnosis_code(result) -> str | None:
    """The single recognized joint diagnosis code of an INFEASIBLE result.

    Only ``JOINT_NO_COMMON_TIME`` is propagated: complete generation records it
    verbatim on ``evidence.stop_reason``; adaptive recovery records it as a
    ``PROVEN_SCOPE`` diagnosis. Every other stop reason or diagnosis code keeps
    the generic ``INFEASIBLE`` code, so a school without joints is unchanged.
    """
    stop_reason = getattr(getattr(result, "evidence", None), "stop_reason", None)
    if stop_reason == _JOINT_NO_COMMON_TIME:
        return _JOINT_NO_COMMON_TIME
    for diagnosis in getattr(result, "diagnoses", ()) or ():
        code = _diagnosis_value(diagnosis.code)
        kind = getattr(diagnosis, "evidence_kind", None)
        if code == _JOINT_NO_COMMON_TIME and (
            kind is None or _diagnosis_value(kind) == EvidenceKind.PROVEN_SCOPE.value
        ):
            return _JOINT_NO_COMMON_TIME
    return None


def _terminal_finish(result) -> tuple[str, str, str]:
    """Map a non-complete result to its persisted status, code and stop reason.

    Only a proven ``INFEASIBLE`` diagnosis changes the generic code, so a school
    without joints keeps exactly today's values. Cancellation and staleness still
    override the result inside ``finish_job``.
    """
    status, result_code, stop_reason = _TERMINAL_BY_OUTCOME.get(
        result.outcome, ("FAILED", "SYSTEM_ERROR", "FAILED")
    )
    if result.outcome == OUTCOME_INFEASIBLE:
        proven_code = _proven_diagnosis_code(result)
        if proven_code is not None:
            result_code = proven_code
            stop_reason = proven_code
    return status, result_code, stop_reason


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
                grid_version_id=claim.grid_version_id,
            )
    except SnapshotConfigurationError as exc:
        written = await _finish(claim, "FAILED", "INVALID_INPUT", exc.code)
        return {"job_id": claim.job_id, "status": written, "code": exc.code}
    cancel_event = threading.Event()
    monitor = asyncio.create_task(_monitor_attempt(claim, cancel_event, lock_connection))
    with structlog.contextvars.bound_contextvars(
        job_id=claim.job_id,
        organization_id=claim.organization_id,
        strategy=claim.strategy.value,
    ):
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
        _log_search_outcome(claim, result)
        if result.outcome == OUTCOME_COMPLETE and result.candidate is not None:
            payload = _build_payload(claim, bundle, result)
            diagnostics.phase_started("PERSISTENCE")
            persist_start = monotonic()
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
                diagnostics.phase_finished(
                    "PERSISTENCE", started_at=persist_start, status="PERSISTED"
                )
                return {
                    "job_id": claim.job_id,
                    "status": "SUCCEEDED",
                    "proposal_id": outcome.proposal_id,
                }
            diagnostics.phase_finished(
                "PERSISTENCE", started_at=persist_start, status=outcome.refused or "LOST"
            )
            return {"job_id": claim.job_id, "status": outcome.refused or "LOST"}
        status, result_code, stop_reason = _terminal_finish(result)
        written = await _finish(claim, status, result_code, stop_reason, diagnoses=result.diagnoses)
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
            stop_at_first_complete=bool(settings.SCHEDULER_V1_STOP_AT_FIRST_COMPLETE),
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
        stop_at_first_complete=bool(settings.SCHEDULER_V1_STOP_AT_FIRST_COMPLETE),
        **settings_values,
    )


def _log_search_outcome(claim: JobClaim, result) -> None:
    """Emit one structured line per job so a failed search stays diagnosable."""
    evidence = getattr(result, "evidence", None)
    logger.info(
        "scheduler_v1_search_finished",
        job_id=claim.job_id,
        organization_id=claim.organization_id,
        strategy=claim.strategy.value,
        outcome=result.outcome,
        stop_reason=getattr(evidence, "stop_reason", None),
        rounds=getattr(evidence, "rounds", None),
        certified_stages=getattr(evidence, "certified_stages", None),
        proposals_excluded=getattr(evidence, "proposals_excluded", None),
        search_seconds=round(float(getattr(result, "search_seconds", 0.0)), 3),
        statistics={
            key: int(value) for key, value in (getattr(result, "statistics", None) or {}).items()
        },
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


async def _finish(
    claim: JobClaim,
    status: str,
    result_code: str,
    stop_reason: str | None,
    *,
    diagnoses: tuple[Diagnosis, ...] = (),
) -> str:
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
            diagnostics=diagnostics_summary(diagnoses),
            now_utc=_now(),
        )
        await db.commit()
        return written


@celery_app.task(name=TASK_NAME)
def run_next_scheduler_job_task() -> dict[str, object]:
    return asyncio.run(process_next_jobs())
