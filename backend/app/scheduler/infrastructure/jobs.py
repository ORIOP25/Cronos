"""Global scheduler v1 queue: admission, FIFO claims, heartbeat and recovery.

One solver runs globally. Requests wait in a database-backed FIFO; the executor
holds an advisory lock on a dedicated connection during the whole solve, picks
the oldest eligible request and stamps an attempt token on every write. The
global visibility is limited to the operational metadata returned by
``app_security.list_scheduler_v1_jobs_for_executor``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from app import models
from app.db.tenant import set_async_tenant_context
from app.scheduler.domain.candidate import SchedulingStrategy
from app.scheduler.domain.eligibility import (
    EligibilityFacts,
    EligibilityReason,
    generation_eligibility,
)
from app.scheduler.infrastructure.curriculum import sync_curricular_projection
from app.scheduler.infrastructure.models import (
    JOB_ACTIVE_STATUSES,
    JOB_TERMINAL_STATUSES,
    SchedulerJobV1,
    SchedulerProposalV1,
)
from app.scheduler.infrastructure.progress import load_active_version_id
from app.scheduler.infrastructure.snapshot import load_snapshot

EXECUTOR_LOCK_KEY = 109_438_846_303_891  # "cronos" as a bigint
QUEUE_METADATA_SQL = text(
    "SELECT job_id, organization_id, school_year_id, status, queued_at, "
    "heartbeat_at, attempt_token FROM app_security.list_scheduler_v1_jobs_for_executor()"
)
QUEUE_POSITION_SQL = text("SELECT app_security.scheduler_v1_queue_position(:job_id)")


class GenerationUnavailable(Exception):
    """The request is valid but the current state does not allow generation."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        reasons: tuple[EligibilityReason, ...] = (),
        blocker: EligibilityReason | None = None,
        job_id: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.reasons = reasons
        self.blocker = blocker
        self.job_id = job_id


class AttemptState(StrEnum):
    CONTINUE = "CONTINUE"
    CANCEL = "CANCEL"
    LOST = "LOST"


@dataclass(frozen=True)
class EnqueueOutcome:
    job: SchedulerJobV1
    created: bool
    queue_position: int
    digest: str


@dataclass(frozen=True)
class JobClaim:
    job_id: int
    organization_id: int
    school_year_id: int
    strategy: SchedulingStrategy
    attempt_token: int
    grid_version_id: int | None = None


def _normalise_key(value: str) -> str:
    if type(value) is not str:
        raise ValueError("The idempotency key must be a string.")
    key = value.strip()
    if not key or len(key) > 160:
        raise ValueError("The idempotency key must be between 1 and 160 characters.")
    return key


async def _active_year(
    db: AsyncSession, organization_id: int, *, for_update_state: bool
) -> tuple[models.SchedulerSchoolYear, models.SchedulerSchoolYearState]:
    year = await db.scalar(
        select(models.SchedulerSchoolYear).where(
            models.SchedulerSchoolYear.organization_id == organization_id,
            models.SchedulerSchoolYear.is_active.is_(True),
        )
    )
    if year is None:
        raise GenerationUnavailable(
            "scheduler_year_missing", "O ano letivo ativo não está configurado."
        )
    query = select(models.SchedulerSchoolYearState).where(
        models.SchedulerSchoolYearState.organization_id == organization_id,
        models.SchedulerSchoolYearState.school_year_id == year.id,
    )
    state = await db.scalar(query.with_for_update() if for_update_state else query)
    if state is None:
        raise GenerationUnavailable(
            "scheduler_year_missing", "O estado de planeamento do ano letivo não existe."
        )
    return year, state


async def enqueue_generation(
    db: AsyncSession,
    organization_id: int,
    *,
    idempotency_key: str,
    requested_by_membership_id: int | None,
    now_utc: datetime,
    expected_input_revision: int | None = None,
) -> EnqueueOutcome:
    """Admit one manual generation request into the global FIFO."""
    key = _normalise_key(idempotency_key)
    year, state = await _active_year(db, organization_id, for_update_state=True)
    existing = await db.scalar(
        select(SchedulerJobV1).where(
            SchedulerJobV1.organization_id == organization_id,
            SchedulerJobV1.origin == key,
            SchedulerJobV1.revision == 1,
        )
    )
    if existing is not None:
        position = await queue_position(db, existing.id)
        await db.commit()
        await set_async_tenant_context(db, organization_id)
        return EnqueueOutcome(
            job=existing,
            created=False,
            queue_position=position,
            digest=existing.snapshot_digest or "",
        )
    active_job = await db.scalar(
        select(SchedulerJobV1)
        .where(
            SchedulerJobV1.organization_id == organization_id,
            SchedulerJobV1.school_year_id == year.id,
            SchedulerJobV1.status.in_(JOB_ACTIVE_STATUSES),
        )
        .order_by(SchedulerJobV1.id)
    )
    facts = await _eligibility_facts(db, organization_id, year, state, now_utc=now_utc)
    decision = generation_eligibility(facts)
    if decision.blocker is not None or not decision.can_generate:
        if decision.blocker is EligibilityReason.ACTIVE_JOB and active_job is not None:
            raise GenerationUnavailable(
                "active_job",
                "Já existe um pedido de geração em curso.",
                reasons=decision.reasons,
                blocker=decision.blocker,
                job_id=active_job.id,
            )
        raise GenerationUnavailable(
            "no_generation_reason",
            "Não existem alterações que justifiquem uma nova geração.",
            reasons=decision.reasons,
            blocker=decision.blocker,
        )
    active_version_id = await load_active_version_id(db, organization_id, year.id)
    strategy = (
        SchedulingStrategy.ADAPTIVE_RECOVERY
        if active_version_id is not None
        else SchedulingStrategy.COMPLETE_GENERATION
    )
    await sync_curricular_projection(db, organization_id, year)
    bundle = await load_snapshot(
        db,
        organization_id,
        strategy=strategy,
        now_utc=now_utc,
        school_year_id=year.id,
    )
    if expected_input_revision is not None and expected_input_revision != bundle.input_revision:
        raise GenerationUnavailable(
            "scheduler_state_changed",
            "O horário foi alterado entretanto. Atualize a página e volte a tentar.",
            reasons=decision.reasons,
        )
    job = SchedulerJobV1(
        organization_id=organization_id,
        school_year_id=year.id,
        strategy=strategy.value,
        status="QUEUED",
        origin=key,
        revision=1,
        attempt_token=1,
        requested_by_membership_id=requested_by_membership_id,
        base_version_id=active_version_id,
        input_revision_used=bundle.input_revision,
        planning_revision_used=bundle.planning_revision,
        snapshot_digest=bundle.digest,
        queued_at=now_utc,
    )
    db.add(job)
    await db.flush()
    position = await queue_position(db, job.id)
    await db.commit()
    # The queue row is durable before dispatch; the tenant setting is
    # transaction-local, so it is restored for the caller's next reads.
    await set_async_tenant_context(db, organization_id)
    return EnqueueOutcome(
        job=job,
        created=True,
        queue_position=position,
        digest=bundle.digest,
    )


async def enqueue_grid_change(
    db: AsyncSession,
    organization_id: int,
    *,
    grid_version_id: int,
    idempotency_key: str,
    requested_by_membership_id: int | None,
    now_utc: datetime,
) -> EnqueueOutcome:
    """Admit one grid-change generation pinned to a pending grid version.

    A grid change requires a published schedule, no other active job and no
    pending proposal. The pinned version only resolves inside this job; the
    approval transaction activates it together with the new schedule.
    """
    key = _normalise_key(idempotency_key)
    year, _state = await _active_year(db, organization_id, for_update_state=True)
    existing = await db.scalar(
        select(SchedulerJobV1).where(
            SchedulerJobV1.organization_id == organization_id,
            SchedulerJobV1.origin == key,
            SchedulerJobV1.revision == 1,
        )
    )
    if existing is not None:
        position = await queue_position(db, existing.id)
        await db.commit()
        await set_async_tenant_context(db, organization_id)
        return EnqueueOutcome(
            job=existing,
            created=False,
            queue_position=position,
            digest=existing.snapshot_digest or "",
        )
    version = await db.scalar(
        select(models.GridVersion).where(
            models.GridVersion.organization_id == organization_id,
            models.GridVersion.id == grid_version_id,
        )
    )
    if version is None or version.state != models.GridVersionState.PENDING:
        raise GenerationUnavailable(
            "grid_change_unavailable", "A proposta de grelha já não está pendente."
        )
    active_job = await db.scalar(
        select(SchedulerJobV1)
        .where(
            SchedulerJobV1.organization_id == organization_id,
            SchedulerJobV1.school_year_id == year.id,
            SchedulerJobV1.status.in_(JOB_ACTIVE_STATUSES),
        )
        .order_by(SchedulerJobV1.id)
    )
    if active_job is not None:
        raise GenerationUnavailable(
            "active_job",
            "Já existe um pedido de geração em curso.",
            job_id=active_job.id,
        )
    active_version_id = await load_active_version_id(db, organization_id, year.id)
    if active_version_id is None:
        raise GenerationUnavailable(
            "grid_change_requires_published_schedule",
            "A alteração da grelha exige um horário publicado.",
        )
    pending_proposal = await db.scalar(
        select(SchedulerProposalV1.id).where(
            SchedulerProposalV1.organization_id == organization_id,
            SchedulerProposalV1.school_year_id == year.id,
            SchedulerProposalV1.status == "PENDING",
        )
    )
    if pending_proposal is not None:
        raise GenerationUnavailable(
            "pending_draft_replacement_required",
            "Existe uma proposta pendente. Reveja-a ou rejeite-a antes de alterar a grelha.",
        )
    await sync_curricular_projection(db, organization_id, year)
    bundle = await load_snapshot(
        db,
        organization_id,
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        now_utc=now_utc,
        school_year_id=year.id,
        grid_version_id=version.id,
    )
    job = SchedulerJobV1(
        organization_id=organization_id,
        school_year_id=year.id,
        strategy=SchedulingStrategy.COMPLETE_GENERATION.value,
        status="QUEUED",
        origin=key,
        revision=1,
        attempt_token=1,
        requested_by_membership_id=requested_by_membership_id,
        base_version_id=active_version_id,
        grid_version_id=version.id,
        input_revision_used=bundle.input_revision,
        planning_revision_used=bundle.planning_revision,
        snapshot_digest=bundle.digest,
        queued_at=now_utc,
    )
    db.add(job)
    await db.flush()
    position = await queue_position(db, job.id)
    await db.commit()
    await set_async_tenant_context(db, organization_id)
    return EnqueueOutcome(
        job=job,
        created=True,
        queue_position=position,
        digest=bundle.digest,
    )


async def _grid_version_pending(
    db: AsyncSession, organization_id: int, grid_version_id: int | None
) -> bool:
    """A pinned grid version must still be pending when a job is processed."""
    if grid_version_id is None:
        return True
    state = await db.scalar(
        select(models.GridVersion.state).where(
            models.GridVersion.organization_id == organization_id,
            models.GridVersion.id == grid_version_id,
        )
    )
    return state == models.GridVersionState.PENDING


async def reject_grid_version_for_job(
    db: AsyncSession, organization_id: int, grid_version_id: int | None
) -> None:
    """Reject a still-pending grid version whose job will not publish it."""
    if grid_version_id is None:
        return
    version = await db.scalar(
        select(models.GridVersion)
        .where(
            models.GridVersion.organization_id == organization_id,
            models.GridVersion.id == grid_version_id,
        )
        .with_for_update()
    )
    if version is not None and version.state == models.GridVersionState.PENDING:
        version.state = models.GridVersionState.REJECTED
        await db.flush()


async def _eligibility_facts(
    db: AsyncSession,
    organization_id: int,
    year: models.SchedulerSchoolYear,
    state: models.SchedulerSchoolYearState,
    *,
    now_utc: datetime,
) -> EligibilityFacts:
    latest_terminal = await db.scalar(
        select(SchedulerJobV1)
        .where(
            SchedulerJobV1.organization_id == organization_id,
            SchedulerJobV1.school_year_id == year.id,
            SchedulerJobV1.status.in_(JOB_TERMINAL_STATUSES),
        )
        .order_by(SchedulerJobV1.id.desc())
    )
    active = await db.scalar(
        select(SchedulerJobV1.id).where(
            SchedulerJobV1.organization_id == organization_id,
            SchedulerJobV1.school_year_id == year.id,
            SchedulerJobV1.status.in_(JOB_ACTIVE_STATUSES),
        )
    )
    last_success_at = state.last_successful_generation_at
    zone = ZoneInfo(year.timezone)
    return EligibilityFacts(
        school_today=now_utc.astimezone(zone).date(),
        planning_revision=state.planning_revision,
        last_completed_planning_revision=state.last_completed_planning_revision,
        last_successful_generation_date=(
            None if last_success_at is None else last_success_at.astimezone(zone).date()
        ),
        last_attempt_incomplete=(
            latest_terminal is not None and latest_terminal.status != "SUCCEEDED"
        ),
        active_job=active is not None,
    )


async def queue_position(db: AsyncSession, job_id: int) -> int:
    position = await db.scalar(QUEUE_POSITION_SQL, {"job_id": job_id})
    return int(position or 1)


async def queue_metadata(db: AsyncSession) -> list[dict]:
    rows = (await db.execute(QUEUE_METADATA_SQL)).all()
    return [
        {
            "job_id": row[0],
            "organization_id": row[1],
            "school_year_id": row[2],
            "status": row[3],
            "queued_at": row[4],
            "heartbeat_at": row[5],
            "attempt_token": row[6],
        }
        for row in rows
    ]


async def has_queued_jobs(db: AsyncSession) -> bool:
    return any(row["status"] == "QUEUED" for row in await queue_metadata(db))


async def has_running_job(db: AsyncSession) -> bool:
    return any(row["status"] in ("RUNNING", "VALIDATING") for row in await queue_metadata(db))


async def claim_next_job(db: AsyncSession, *, now_utc: datetime) -> JobClaim | None:
    """Claim the oldest request that is still current, or nothing.

    Returns ``None`` when another execution is running or the queue is empty.
    Stale requests are marked and skipped; the loop keeps the transaction
    boundaries explicit.
    """
    while True:
        rows = await queue_metadata(db)
        if any(row["status"] in ("RUNNING", "VALIDATING") for row in rows):
            return None
        queued = sorted(
            (row for row in rows if row["status"] == "QUEUED"),
            key=lambda row: (row["queued_at"], row["job_id"]),
        )
        if not queued:
            return None
        candidate = queued[0]
        await set_async_tenant_context(db, candidate["organization_id"])
        job = await db.scalar(
            select(SchedulerJobV1)
            .where(
                SchedulerJobV1.id == candidate["job_id"],
                SchedulerJobV1.organization_id == candidate["organization_id"],
            )
            .with_for_update()
        )
        if job is None or job.status != "QUEUED":
            await db.rollback()
            continue
        state = await db.scalar(
            select(models.SchedulerSchoolYearState).where(
                models.SchedulerSchoolYearState.organization_id == job.organization_id,
                models.SchedulerSchoolYearState.school_year_id == job.school_year_id,
            )
        )
        active_version = await load_active_version_id(db, job.organization_id, job.school_year_id)
        if (
            state is None
            or state.input_revision != job.input_revision_used
            or state.planning_revision != job.planning_revision_used
            or active_version != job.base_version_id
            or not await _grid_version_pending(db, job.organization_id, job.grid_version_id)
        ):
            job.status = "STALE"
            job.result_code = "STALE"
            job.stop_reason = "INPUT_CHANGED"
            job.finished_at = now_utc
            await reject_grid_version_for_job(db, job.organization_id, job.grid_version_id)
            await db.commit()
            continue
        job.status = "RUNNING"
        job.started_at = now_utc
        job.heartbeat_at = now_utc
        job.attempt_token += 1
        await db.commit()
        return JobClaim(
            job_id=job.id,
            organization_id=job.organization_id,
            school_year_id=job.school_year_id,
            strategy=SchedulingStrategy(job.strategy),
            attempt_token=job.attempt_token,
            grid_version_id=job.grid_version_id,
        )


async def heartbeat_and_poll(
    db: AsyncSession,
    *,
    organization_id: int,
    job_id: int,
    attempt_token: int,
    now_utc: datetime,
) -> AttemptState:
    """Refresh the heartbeat and report whether this attempt must still run."""
    result = await db.execute(
        update(SchedulerJobV1)
        .where(
            SchedulerJobV1.id == job_id,
            SchedulerJobV1.organization_id == organization_id,
            SchedulerJobV1.attempt_token == attempt_token,
            SchedulerJobV1.status.in_(("RUNNING", "VALIDATING")),
        )
        .values(heartbeat_at=now_utc)
        .returning(SchedulerJobV1.cancellation_requested_at)
    )
    row = result.first()
    if row is None:
        return AttemptState.LOST
    if row[0] is not None:
        return AttemptState.CANCEL
    return AttemptState.CONTINUE


async def finish_job(
    db: AsyncSession,
    *,
    organization_id: int,
    job_id: int,
    attempt_token: int,
    status: str,
    result_code: str,
    stop_reason: str | None = None,
    diagnostics: Sequence[dict] | None = None,
    now_utc: datetime,
) -> str:
    """Terminal write under the state and job locks.

    Cancellation and stale data win over the calculated result, so an old
    ``INFEASIBLE`` never describes freshness it no longer has. Per-class
    diagnostics are stored only when the effective terminal state is a genuine
    ``INFEASIBLE``; a cancelled or stale attempt keeps the column empty.
    Returns the status actually written; ``LOST`` means this attempt no longer
    owns the job.
    """
    if status not in JOB_TERMINAL_STATUSES:
        raise ValueError("A terminal status is required to finish a scheduler job.")
    reference = await db.scalar(
        select(SchedulerJobV1).where(
            SchedulerJobV1.id == job_id,
            SchedulerJobV1.organization_id == organization_id,
        )
    )
    if reference is None:
        return "LOST"
    state = await db.scalar(
        select(models.SchedulerSchoolYearState)
        .where(
            models.SchedulerSchoolYearState.organization_id == organization_id,
            models.SchedulerSchoolYearState.school_year_id == reference.school_year_id,
        )
        .with_for_update()
    )
    job = await db.scalar(
        select(SchedulerJobV1)
        .where(
            SchedulerJobV1.id == job_id,
            SchedulerJobV1.organization_id == organization_id,
        )
        .with_for_update()
    )
    if (
        job is None
        or job.attempt_token != attempt_token
        or job.status not in ("RUNNING", "VALIDATING")
    ):
        return "LOST"
    if job.cancellation_requested_at is not None:
        status, result_code, stop_reason = "CANCELLED", "CANCELLED", "CANCELLED"
    else:
        active_version = await load_active_version_id(db, organization_id, reference.school_year_id)
        if (
            state is None
            or state.input_revision != job.input_revision_used
            or state.planning_revision != job.planning_revision_used
            or active_version != job.base_version_id
            or not await _grid_version_pending(db, job.organization_id, job.grid_version_id)
        ):
            status, result_code, stop_reason = "STALE", "STALE", "INPUT_CHANGED"
    job.status = status
    job.result_code = result_code
    job.stop_reason = stop_reason
    if status == "INFEASIBLE" and diagnostics is not None:
        job.diagnostics_json = list(diagnostics)
    job.finished_at = now_utc
    if status != "SUCCEEDED":
        await reject_grid_version_for_job(db, job.organization_id, job.grid_version_id)
    await db.flush()
    return status


async def request_cancellation(
    db: AsyncSession, organization_id: int, job_id: int, *, now_utc: datetime
) -> SchedulerJobV1:
    """Ask for a cooperative cancellation; idempotent and safe at any phase."""
    job = await db.scalar(
        select(SchedulerJobV1)
        .where(
            SchedulerJobV1.id == job_id,
            SchedulerJobV1.organization_id == organization_id,
        )
        .with_for_update()
    )
    if job is None:
        raise LookupError("Scheduler job was not found.")
    if job.status == "QUEUED":
        job.status = "CANCELLED"
        job.result_code = "CANCELLED"
        job.stop_reason = "CANCELLED"
        job.cancellation_requested_at = now_utc
        job.finished_at = now_utc
        await reject_grid_version_for_job(db, organization_id, job.grid_version_id)
    elif job.status in ("RUNNING", "VALIDATING") and job.cancellation_requested_at is None:
        job.cancellation_requested_at = now_utc
    await db.flush()
    await db.commit()
    await set_async_tenant_context(db, organization_id)
    return job


async def reconcile_abandoned(
    db: AsyncSession, *, stale_after_seconds: int, now_utc: datetime
) -> int:
    """Fail attempts whose process stopped without writing a terminal state."""
    if stale_after_seconds <= 0:
        raise ValueError("The abandoned threshold must be positive.")
    threshold = now_utc - timedelta(seconds=stale_after_seconds)
    reconciled = 0
    for row in await queue_metadata(db):
        if row["status"] not in ("RUNNING", "VALIDATING"):
            continue
        heartbeat = row["heartbeat_at"]
        if heartbeat is not None and heartbeat > threshold:
            continue
        await set_async_tenant_context(db, row["organization_id"])
        job = await db.scalar(
            select(SchedulerJobV1)
            .where(
                SchedulerJobV1.id == row["job_id"],
                SchedulerJobV1.organization_id == row["organization_id"],
            )
            .with_for_update()
        )
        if job is None or job.status not in ("RUNNING", "VALIDATING"):
            await db.rollback()
            continue
        if job.heartbeat_at is not None and job.heartbeat_at > threshold:
            await db.rollback()
            continue
        job.status = "FAILED"
        job.result_code = "WORKER_STALLED"
        job.stop_reason = "WORKER_STALLED"
        job.finished_at = now_utc
        await reject_grid_version_for_job(db, job.organization_id, job.grid_version_id)
        await db.commit()
        reconciled += 1
    return reconciled


async def try_acquire_executor_lock(engine: AsyncEngine) -> AsyncConnection | None:
    """Exclusive executor lock on a dedicated connection for the whole solve."""
    connection = await engine.connect()
    acquired = await connection.scalar(
        text("SELECT pg_try_advisory_lock(:key)"), {"key": EXECUTOR_LOCK_KEY}
    )
    if not acquired:
        await connection.close()
        return None
    return connection


EXECUTOR_LOCK_HELD_SQL = text(
    "SELECT 1 FROM pg_locks "
    "WHERE locktype = 'advisory' "
    "AND classid = ((:key)::bigint >> 32) "
    "AND objid = ((:key)::bigint & 4294967295) "
    "AND objsubid = 1 "
    "AND pid = pg_backend_pid() "
    "AND granted "
    "LIMIT 1"
)


async def executor_lock_alive(connection: AsyncConnection) -> bool:
    """True while this backend still owns the global executor lock.

    Connectivity alone is not proof: a reset connection can answer queries on
    a new backend without holding the advisory lock. The check reads ``pg_locks``
    for the current backend, so a lost lock is detected even after a silent
    reconnect. The solve must stop when this returns ``False``.
    """
    try:
        held = await connection.scalar(EXECUTOR_LOCK_HELD_SQL, {"key": EXECUTOR_LOCK_KEY})
    except Exception:
        return False
    return held is not None


async def release_executor_lock(connection: AsyncConnection) -> None:
    try:
        await connection.scalar(text("SELECT pg_advisory_unlock(:key)"), {"key": EXECUTOR_LOCK_KEY})
    finally:
        await connection.close()


def scheduler_now() -> datetime:
    return datetime.now(UTC)
