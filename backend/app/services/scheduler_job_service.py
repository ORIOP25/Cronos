from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.core.exceptions import new_error_reference
from app.services.scheduler_generation_service import GenerationSelection
from app.services.scheduler_observability import emit_scheduler_job_event
from app.services.scheduler_state_service import SchedulerStateService

ACTIVE_JOB_STATUSES = (
    models.ScheduleGenerationJobStatus.QUEUED,
    models.ScheduleGenerationJobStatus.RUNNING,
    models.ScheduleGenerationJobStatus.CANCEL_REQUESTED,
)


class SchedulerJobError(RuntimeError):
    code = "scheduler_job_error"


class SchedulerJobConflictError(SchedulerJobError):
    code = "generation_job_conflict"


class SchedulerJobIdempotencyConflictError(SchedulerJobError):
    code = "idempotency_key_conflict"


class SchedulerJobNotFoundError(SchedulerJobError):
    code = "generation_job_not_found"


@dataclass(frozen=True)
class GenerationJobHandle:
    job: models.ScheduleGenerationJob
    created: bool


class SchedulerJobService:
    def __init__(self, db: AsyncSession):
        self._db = db
        self._state = SchedulerStateService(db)

    async def create_or_get_job(
        self,
        selection: GenerationSelection,
        *,
        requested_by_membership_id: int,
        idempotency_key: str | None = None,
    ) -> GenerationJobHandle:
        normalized_key = self._normalize_idempotency_key(idempotency_key)
        if normalized_key is not None:
            existing = await self._db.scalar(
                select(models.ScheduleGenerationJob).where(
                    models.ScheduleGenerationJob.organization_id == selection.organization_id,
                    models.ScheduleGenerationJob.school_year_id == selection.school_year_id,
                    models.ScheduleGenerationJob.idempotency_key == normalized_key,
                )
            )
            if existing is not None:
                self._assert_same_request(existing, selection)
                return GenerationJobHandle(existing, created=False)

        state = await self._state.get_state(
            selection.organization_id,
            selection.school_year_id,
            for_update=True,
        )
        if state is None:
            raise SchedulerJobConflictError("Scheduler school-year state no longer exists.")
        if state.scheduler_state_version != selection.scheduler_state_version:
            raise SchedulerJobConflictError(
                "Scheduler inputs changed while the generation request was being prepared."
            )
        if state.pending_draft_id != selection.pending_draft_id:
            raise SchedulerJobConflictError(
                "Pending draft changed while the generation request was being prepared."
            )

        active = await self._db.scalar(
            select(models.ScheduleGenerationJob).where(
                models.ScheduleGenerationJob.organization_id == selection.organization_id,
                models.ScheduleGenerationJob.school_year_id == selection.school_year_id,
                models.ScheduleGenerationJob.job_status.in_(ACTIVE_JOB_STATUSES),
            )
        )
        if active is not None:
            if normalized_key is not None and active.idempotency_key not in (
                None,
                normalized_key,
            ):
                raise SchedulerJobConflictError(
                    "A different generation job is already active for this school year."
                )
            self._assert_same_request(active, selection)
            return GenerationJobHandle(active, created=False)

        job = models.ScheduleGenerationJob(
            organization_id=selection.organization_id,
            school_year_id=selection.school_year_id,
            requested_by_membership_id=requested_by_membership_id,
            strategy=selection.strategy,
            trigger_type=selection.trigger_type,
            scheduler_state_version_used=selection.scheduler_state_version,
            debt_basis_fingerprint=(
                selection.debt_basis.value if selection.debt_basis is not None else None
            ),
            idempotency_key=normalized_key,
            input_snapshot_json={
                "request": {
                    "replace_pending_draft_id": selection.pending_draft_id,
                }
            },
        )
        self._db.add(job)
        await self._db.flush()
        return GenerationJobHandle(job, created=True)

    async def request_cancellation(
        self,
        organization_id: int,
        job_id: int,
    ) -> models.ScheduleGenerationJob:
        job = await self._db.scalar(
            select(models.ScheduleGenerationJob)
            .where(
                models.ScheduleGenerationJob.id == job_id,
                models.ScheduleGenerationJob.organization_id == organization_id,
            )
            .with_for_update()
        )
        if job is None:
            raise SchedulerJobNotFoundError("Generation job was not found.")
        if job.job_status in (
            models.ScheduleGenerationJobStatus.QUEUED,
            models.ScheduleGenerationJobStatus.RUNNING,
        ):
            job.job_status = models.ScheduleGenerationJobStatus.CANCEL_REQUESTED
            job.cancellation_requested_at = datetime.now(UTC)
            await self._db.flush()
        return job

    async def get_job(
        self,
        organization_id: int,
        job_id: int,
    ) -> models.ScheduleGenerationJob:
        job = await self._db.scalar(
            select(models.ScheduleGenerationJob).where(
                models.ScheduleGenerationJob.id == job_id,
                models.ScheduleGenerationJob.organization_id == organization_id,
            )
        )
        if job is None:
            raise SchedulerJobNotFoundError("Generation job was not found.")
        return job

    async def mark_dispatch_failed(
        self,
        organization_id: int,
        job_id: int,
        message: str,
    ) -> models.ScheduleGenerationJob:
        job = await self._db.scalar(
            select(models.ScheduleGenerationJob)
            .where(
                models.ScheduleGenerationJob.id == job_id,
                models.ScheduleGenerationJob.organization_id == organization_id,
            )
            .with_for_update()
        )
        if job is None:
            raise SchedulerJobNotFoundError("Generation job was not found.")
        if job.job_status == models.ScheduleGenerationJobStatus.QUEUED:
            now = datetime.now(UTC)
            job.job_status = models.ScheduleGenerationJobStatus.FAILED
            job.started_at = now
            job.finished_at = now
            job.duration_ms = 0
            job.failure_code = "DISPATCH_STALLED"
            job.failure_message = message[:2000]
            job.failure_reference = new_error_reference()
            await self._db.flush()
        return job

    async def recover_stale_jobs(
        self,
        organization_id: int,
        *,
        now: datetime | None = None,
    ) -> dict[str, int]:
        """Finalize abandoned jobs while holding each row lock."""
        recovered_at = now or datetime.now(UTC)
        running_before = recovered_at - timedelta(seconds=30)
        cancel_before = recovered_at - timedelta(minutes=2)
        result = await self._db.scalars(
            select(models.ScheduleGenerationJob)
            .where(
                models.ScheduleGenerationJob.organization_id == organization_id,
                (
                    (
                        models.ScheduleGenerationJob.job_status
                        == models.ScheduleGenerationJobStatus.RUNNING
                    )
                    & (models.ScheduleGenerationJob.deadline_at <= running_before)
                )
                | (
                    (
                        models.ScheduleGenerationJob.job_status
                        == models.ScheduleGenerationJobStatus.CANCEL_REQUESTED
                    )
                    & (models.ScheduleGenerationJob.cancellation_requested_at <= cancel_before)
                ),
            )
            .with_for_update(skip_locked=True)
        )
        jobs = list(result)
        totals = {"dispatch_stalled": 0, "worker_stalled": 0, "canceled": 0}
        for job in jobs:
            if job.job_status == models.ScheduleGenerationJobStatus.RUNNING:
                job.job_status = models.ScheduleGenerationJobStatus.FAILED
                job.failure_code = "WORKER_STALLED"
                job.failure_message = "The worker did not complete the generation job."
                totals["worker_stalled"] += 1
                event_name = "generation_worker_stalled"
            else:
                job.job_status = models.ScheduleGenerationJobStatus.CANCELED
                job.failure_code = "CANCELED"
                job.failure_message = "The cancellation request was finalized by recovery."
                totals["canceled"] += 1
                event_name = "generation_canceled"
            job.failure_reference = job.failure_reference or new_error_reference()
            started_at = job.started_at or job.queued_at or recovered_at
            job.started_at = started_at
            job.finished_at = recovered_at
            job.duration_ms = max(0, int((recovered_at - started_at).total_seconds() * 1000))
            emit_scheduler_job_event(event_name, job)
        await self._db.flush()
        return totals

    @staticmethod
    def worker_task_id(job_id: int) -> str:
        return f"scheduler-job-{job_id}"

    @staticmethod
    def _normalize_idempotency_key(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise SchedulerJobIdempotencyConflictError("Idempotency key cannot be blank.")
        if len(normalized) > 100:
            raise SchedulerJobIdempotencyConflictError(
                "Idempotency key cannot exceed 100 characters."
            )
        return normalized

    @staticmethod
    def _assert_same_request(
        job: models.ScheduleGenerationJob,
        selection: GenerationSelection,
    ) -> None:
        request_metadata = (job.input_snapshot_json or {}).get("request", {})
        if (
            job.strategy != selection.strategy
            or job.trigger_type != selection.trigger_type
            or request_metadata.get("replace_pending_draft_id") != selection.pending_draft_id
        ):
            raise SchedulerJobIdempotencyConflictError(
                "The existing job key belongs to a different generation request."
            )
