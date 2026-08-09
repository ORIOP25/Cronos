from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from time import monotonic
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.db.tenant import set_async_tenant_context
from app.scheduler.domain.contracts import (
    DraftBlockSpec,
    NoValidGenerationOutput,
    ValidatedGenerationResult,
)
from app.scheduler.domain.validation import GenerationEnvelopeValidator
from app.services.scheduler_complete_demand import CompleteDemandLedgerBuilder
from app.services.scheduler_diff_service import SchedulerDiffService
from app.services.scheduler_editable_boundary import EditableBoundaryBuilder
from app.services.scheduler_fingerprint_service import SchedulerFingerprintService
from app.services.scheduler_observability import emit_scheduler_job_event
from app.services.scheduler_recovery_service import SchedulerRecoveryService
from app.services.scheduler_target_validator import (
    SchedulerTargetValidationError,
    SchedulerTargetValidator,
)

GENERATION_CAP_SECONDS = 5 * 60
FINAL_COMMIT_RESERVE_SECONDS = 15

logger = structlog.get_logger(__name__)

FAILURE_CANCELED = "CANCELED"
FAILURE_TIMED_OUT = "TIMED_OUT"
FAILURE_NO_VALID_OUTPUT = "NO_VALID_OUTPUT"
FAILURE_VALIDATION = "FAILED_VALIDATION"
FAILURE_SYSTEM = "SYSTEM_ERROR"
FAILURE_SYSTEM_MESSAGE = "Schedule generation failed unexpectedly."


class GenerationRuntimeError(RuntimeError):
    pass


class GenerationCanceledError(GenerationRuntimeError):
    pass


class GenerationTimedOutError(GenerationRuntimeError):
    pass


class GenerationValidationError(GenerationRuntimeError):
    pass


@dataclass(frozen=True)
class GenerationExecutionContext:
    job_id: int
    organization_id: int
    school_year_id: int
    strategy: models.ScheduleGenerationStrategy
    trigger_type: models.ScheduleGenerationTrigger
    immutable_snapshot: dict[str, Any]
    started_at: datetime
    deadline_at: datetime
    checkpoint: Callable[[], Awaitable[None]] | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    @property
    def solve_deadline_at(self) -> datetime:
        return self.deadline_at - timedelta(seconds=FINAL_COMMIT_RESERVE_SECONDS)

    async def ensure_can_continue(self) -> None:
        if self.checkpoint is not None:
            await self.checkpoint()


GenerationEngine = Callable[
    [GenerationExecutionContext],
    Awaitable[ValidatedGenerationResult | NoValidGenerationOutput | None],
]


class SchedulerJobRuntime:
    def __init__(
        self,
        db: AsyncSession,
        *,
        clock: Callable[[], datetime] | None = None,
        elapsed_clock: Callable[[], float] | None = None,
    ):
        self._db = db
        self._clock = clock or (lambda: datetime.now(UTC))
        self._elapsed_clock = elapsed_clock or monotonic

    async def execute(
        self,
        job_id: int,
        engine: GenerationEngine,
        *,
        organization_id: int | None = None,
    ) -> models.ScheduleGenerationJob:
        self._organization_id = organization_id
        elapsed_start = self._elapsed_clock()
        try:
            context = await self._start_and_snapshot(job_id)
            await self._assert_can_continue(
                job_id,
                context.deadline_at,
                end_transaction=True,
            )
            solve_seconds = (context.solve_deadline_at - self._aware_now()).total_seconds()
            if solve_seconds <= 0:
                raise GenerationTimedOutError(
                    "Generation snapshot exhausted the solver time budget."
                )
            try:
                result = await asyncio.wait_for(
                    engine(context),
                    timeout=solve_seconds,
                )
            except TimeoutError as exc:
                raise GenerationTimedOutError(
                    "Generation exceeded its solver time budget."
                ) from exc
            await self._assert_can_continue(
                job_id,
                context.deadline_at,
                end_transaction=True,
            )
            if result is None or isinstance(result, NoValidGenerationOutput):
                return await self._run_before_deadline(
                    lambda: self._finish_without_output(
                        job_id,
                        elapsed_start,
                        result,
                    ),
                    context.deadline_at,
                    "No-output finalization exceeded the five-minute deadline.",
                )
            await self._run_before_deadline(
                lambda: self._validate_result(context, result),
                context.deadline_at,
                "Generation validation exceeded the five-minute deadline.",
            )
            await self._assert_can_continue(
                job_id,
                context.deadline_at,
                end_transaction=True,
            )
            return await self._run_before_deadline(
                lambda: self._commit_validated_draft(
                    context,
                    result,
                    elapsed_start,
                ),
                context.deadline_at,
                "Draft commit exceeded the five-minute deadline.",
            )
        except GenerationCanceledError as exc:
            return await self._finish_failure(
                job_id,
                models.ScheduleGenerationJobStatus.CANCELED,
                FAILURE_CANCELED,
                str(exc),
                elapsed_start,
            )
        except GenerationTimedOutError as exc:
            return await self._finish_failure(
                job_id,
                models.ScheduleGenerationJobStatus.FAILED,
                FAILURE_TIMED_OUT,
                str(exc),
                elapsed_start,
            )
        except GenerationValidationError as exc:
            return await self._finish_failure(
                job_id,
                models.ScheduleGenerationJobStatus.FAILED,
                FAILURE_VALIDATION,
                str(exc),
                elapsed_start,
            )
        except GenerationRuntimeError:
            await self._db.rollback()
            raise
        except Exception as exc:
            await self._db.rollback()
            logger.exception(
                "scheduler_generation_unexpected_failure",
                job_id=job_id,
                organization_id=organization_id,
                error_type=type(exc).__name__,
            )
            return await self._finish_failure(
                job_id,
                models.ScheduleGenerationJobStatus.FAILED,
                FAILURE_SYSTEM,
                str(exc),
                elapsed_start,
            )

    async def _start_and_snapshot(self, job_id: int) -> GenerationExecutionContext:
        job = await self._locked_job(job_id)
        if job.job_status == models.ScheduleGenerationJobStatus.CANCEL_REQUESTED:
            raise GenerationCanceledError("Generation cancellation was requested before start.")
        if job.job_status != models.ScheduleGenerationJobStatus.QUEUED:
            raise GenerationRuntimeError("Only a queued generation job can start.")
        started_at = self._aware_now()
        deadline_at = started_at + timedelta(seconds=GENERATION_CAP_SECONDS)
        job.job_status = models.ScheduleGenerationJobStatus.RUNNING
        job.started_at = started_at
        job.deadline_at = deadline_at
        await self._db.commit()

        await self._install_tenant_context()
        fingerprints = SchedulerFingerprintService(self._db)
        generation = await fingerprints.generation_input_fingerprint(
            job.organization_id,
            job.school_year_id,
            job.strategy,
        )
        debt = None
        policy = None
        if job.strategy == models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR:
            debt = await fingerprints.debt_basis_fingerprint(
                job.organization_id,
                job.school_year_id,
            )
            policy = await fingerprints.repair_policy_snapshot(
                job.organization_id,
                job.school_year_id,
                now=started_at,
            )

        job = await self._locked_job(job_id)
        request_metadata = (job.input_snapshot_json or {}).get("request", {})
        immutable_snapshot = {
            "generation_input": generation.snapshot,
            "generation_input_fingerprint": generation.value,
            "debt_basis": None if debt is None else debt.snapshot,
            "debt_basis_fingerprint": None if debt is None else debt.value,
            "repair_policy": None if policy is None else policy.snapshot,
            "repair_policy_snapshot_hash": None if policy is None else policy.value,
            "request": request_metadata,
        }
        snapshot_state_version = generation.snapshot.get("scheduler_state_version")
        job.generation_input_fingerprint = generation.value
        if snapshot_state_version is not None:
            job.scheduler_state_version_used = int(snapshot_state_version)
        job.debt_basis_fingerprint = None if debt is None else debt.value
        job.repair_policy_snapshot_hash = None if policy is None else policy.value
        job.input_snapshot_json = immutable_snapshot
        await self._db.commit()
        emit_scheduler_job_event("generation_started", job)
        checkpoint_job_id = job.id

        return GenerationExecutionContext(
            job_id=job.id,
            organization_id=job.organization_id,
            school_year_id=job.school_year_id,
            strategy=job.strategy,
            trigger_type=job.trigger_type,
            immutable_snapshot=immutable_snapshot,
            started_at=started_at,
            deadline_at=deadline_at,
            checkpoint=lambda: self._assert_can_continue(
                checkpoint_job_id,
                deadline_at,
                end_transaction=True,
            ),
        )

    async def _validate_result(
        self,
        context: GenerationExecutionContext,
        result: ValidatedGenerationResult,
    ) -> None:
        if result.result_category == models.ScheduleGenerationResultCategory.NO_VALID_OUTPUT:
            raise GenerationValidationError("No Valid Output cannot be persisted as a draft.")
        generation_input = context.immutable_snapshot["generation_input"]
        hard_end_date = date.fromisoformat(generation_input["hard_end_date"])
        envelope_violations = GenerationEnvelopeValidator.validate(
            context.strategy,
            result,
            hard_end_date,
        )
        if envelope_violations:
            raise GenerationValidationError(envelope_violations[0].message)

        try:
            SchedulerTargetValidator.validate(
                generation_input,
                result.blocks,
                complete=(
                    context.strategy == models.ScheduleGenerationStrategy.COMPLETE_GENERATION
                ),
            )
        except SchedulerTargetValidationError as exc:
            raise GenerationValidationError(str(exc)) from exc

        await self._validate_resource_scope(context, result.blocks)
        if context.strategy == models.ScheduleGenerationStrategy.COMPLETE_GENERATION:
            self._validate_complete_demand(generation_input, result.blocks)
        else:
            self._validate_adaptive_repair(context, result)

    @staticmethod
    def _validate_adaptive_repair(
        context: GenerationExecutionContext,
        result: ValidatedGenerationResult,
    ) -> None:
        if result.result_category not in (
            models.ScheduleGenerationResultCategory.COMPLETE_SUCCESS,
            models.ScheduleGenerationResultCategory.PARTIAL_RECOVERY,
        ):
            raise GenerationValidationError("Adaptive repair result category is invalid.")
        snapshot = context.immutable_snapshot["generation_input"]
        active = {row["id"]: row for row in snapshot.get("active_schedule", [])}
        assignments = {
            (row["class_id"], row["subject_id"]): row.get("teacher_id")
            for row in snapshot.get("class_subject_requirements", [])
        }
        qualifications = {
            (row["teacher_id"], row["subject_id"])
            for row in snapshot.get("teacher_subject_eligibility", [])
        }
        classes = {row["id"]: row for row in snapshot.get("classes", [])}
        subjects = {row["id"]: row for row in snapshot.get("subjects", [])}
        rooms = {row["id"]: row for row in snapshot.get("rooms", [])}
        impossible = {
            (row["teacher_id"], row["timeslot_id"])
            for row in snapshot.get("teacher_availability", [])
            if int(row.get("score", 0)) == -1
        }
        blocked_dates: set[date] = set()
        for event in snapshot.get("calendar_events", []):
            current = date.fromisoformat(event["start_date"])
            event_end = date.fromisoformat(event["end_date"])
            while current <= event_end:
                blocked_dates.add(current)
                current += timedelta(days=1)
        source_ids: set[int] = set()
        for block in result.blocks:
            class_row = classes.get(block.class_id)
            subject_row = subjects.get(block.subject_id)
            room_row = rooms.get(block.room_id)
            required_room_type = (
                None
                if subject_row is None
                else str(
                    getattr(
                        subject_row.get("required_room_type"),
                        "value",
                        subject_row.get("required_room_type"),
                    )
                )
            )
            actual_room_type = (
                None
                if room_row is None
                else str(getattr(room_row.get("type"), "value", room_row.get("type")))
            )
            if (
                class_row is None
                or subject_row is None
                or assignments.get((block.class_id, block.subject_id)) != block.teacher_id
                or (block.teacher_id, block.subject_id) not in qualifications
                or room_row is None
                or int(room_row.get("capacity") or 0) < int(class_row["size"])
                or actual_room_type != required_room_type
                or (block.teacher_id, block.timeslot_id) in impossible
                or block.date in blocked_dates
            ):
                raise GenerationValidationError(
                    "Adaptive target violates the latest scheduler inputs."
                )
            if block.change_type == models.ScheduleDraftBlockChangeType.ADDED:
                if block.source_active_block_id is not None:
                    raise GenerationValidationError(
                        "Added repair blocks cannot have active lineage."
                    )
                continue
            source = active.get(block.source_active_block_id)
            if source is None or block.source_active_block_id in source_ids:
                raise GenerationValidationError(
                    "Repair block active lineage is missing, duplicated, or outside the snapshot."
                )
            source_ids.add(block.source_active_block_id)
            if (
                block.stable_block_key != source["stable_block_key"]
                or block.class_id != source["class_id"]
                or block.subject_id != source["subject_id"]
            ):
                raise GenerationValidationError("Repair block lineage changes stable identity.")

        policy = context.immutable_snapshot.get("repair_policy")
        if policy is None:
            raise GenerationValidationError("Repair policy snapshot is missing.")
        boundary = EditableBoundaryBuilder().build(snapshot, policy)
        by_source = {
            block.source_active_block_id: block
            for block in result.blocks
            if block.source_active_block_id is not None
        }
        for source in boundary.immutable_blocks:
            target = by_source.get(source["id"])
            if target is None or (
                target.stable_block_key != source["stable_block_key"]
                or target.class_id != source["class_id"]
                or target.subject_id != source["subject_id"]
                or target.teacher_id != source["teacher_id"]
                or target.room_id != source["room_id"]
                or target.date.isoformat() != source["date"]
                or target.timeslot_id != source["timeslot_id"]
                or target.duration_minutes != source["duration_minutes"]
                or target.change_type != models.ScheduleDraftBlockChangeType.UNCHANGED
            ):
                raise GenerationValidationError(
                    "Adaptive repair changed or omitted an immutable active block."
                )

        debt_items = {
            (int(row["occurrence_id"]), int(row["occurrence_revision"])): int(
                row.get("unresolved_debt_minutes", 0)
            )
            for row in (context.immutable_snapshot.get("debt_basis") or {}).get("items", [])
        }
        recovered_by_debt: dict[tuple[int, int], int] = {}
        for block in result.blocks:
            if (
                not block.is_recovery_block
                or block.change_type != models.ScheduleDraftBlockChangeType.ADDED
            ):
                continue
            key = (
                int(block.recovery_source_occurrence_id),
                int(block.recovery_source_occurrence_revision),
            )
            if key not in debt_items:
                raise GenerationValidationError(
                    "Recovery block references debt outside its snapshot."
                )
            recovered_by_debt[key] = recovered_by_debt.get(key, 0) + block.duration_minutes
        if any(recovered_by_debt.get(key, 0) > minutes for key, minutes in debt_items.items()):
            raise GenerationValidationError("Repair over-recovers an explicit debt entry.")
        required = sum(debt_items.values())
        recovered = sum(recovered_by_debt.values())
        residual = required - recovered
        if (
            result.summary.get("recovered_minutes") != recovered
            or result.summary.get("remaining_unscheduled_minutes") != residual
            or result.metrics.get("recovered_minutes") != recovered
            or result.metrics.get("residual_debt_minutes") != residual
        ):
            raise GenerationValidationError("Repair debt metrics do not match target blocks.")
        if result.result_category == models.ScheduleGenerationResultCategory.PARTIAL_RECOVERY:
            if (
                required <= 0
                or residual <= 0
                or not result.partial_recovery_blocker_type
                or not result.main_blocker_message
                or not result.recommended_actions
            ):
                raise GenerationValidationError("Partial recovery explanation is incomplete.")
        elif residual != 0:
            raise GenerationValidationError("Complete adaptive repair leaves residual debt.")

    @staticmethod
    def _validate_complete_demand(
        snapshot: dict[str, Any],
        blocks: tuple[DraftBlockSpec, ...],
    ) -> None:
        ledger = CompleteDemandLedgerBuilder().build(snapshot)
        if not ledger.is_complete:
            raise GenerationValidationError(
                "Complete draft was produced from an incomplete demand ledger."
            )
        items = {(item.class_id, item.subject_id): item for item in ledger.items}
        actual: dict[tuple[int, int], int] = {}
        for block in blocks:
            item = items.get((block.class_id, block.subject_id))
            if item is None or item.teacher_id != block.teacher_id:
                raise GenerationValidationError("Draft violates class-subject-teacher assignment.")
            if block.room_id not in item.eligible_room_ids:
                raise GenerationValidationError("Draft uses an ineligible room.")
            if block.module_sequence_index is None or block.module_sequence_index not in {
                module.sequence for module in item.modules
            }:
                raise GenerationValidationError("Draft module sequence is invalid.")
            key = (block.class_id, block.subject_id)
            actual[key] = actual.get(key, 0) + block.duration_minutes
        expected = {
            (item.class_id, item.subject_id): item.required_minutes for item in ledger.items
        }
        if actual != expected:
            raise GenerationValidationError(
                "Complete draft does not exactly satisfy the annual demand ledger."
            )

    async def _validate_resource_scope(
        self,
        context: GenerationExecutionContext,
        blocks: tuple[DraftBlockSpec, ...],
    ) -> None:
        await self._install_tenant_context()
        checks = (
            (models.Class, {block.class_id for block in blocks}),
            (models.Subject, {block.subject_id for block in blocks}),
            (models.Teacher, {block.teacher_id for block in blocks}),
            (models.Room, {block.room_id for block in blocks}),
            (models.Timeslot, {block.timeslot_id for block in blocks}),
        )
        for model, ids in checks:
            found = set(
                await self._db.scalars(
                    select(model.id).where(
                        model.organization_id == context.organization_id,
                        model.id.in_(ids),
                    )
                )
            )
            if found != ids:
                raise GenerationValidationError(
                    f"Draft references a cross-tenant or missing {model.__name__}."
                )

    async def _commit_validated_draft(
        self,
        context: GenerationExecutionContext,
        result: ValidatedGenerationResult,
        elapsed_start: float,
    ) -> models.ScheduleGenerationJob:
        job = await self._locked_job(context.job_id)
        state = await self._db.scalar(
            select(models.SchedulerSchoolYearState)
            .where(
                models.SchedulerSchoolYearState.organization_id == context.organization_id,
                models.SchedulerSchoolYearState.school_year_id == context.school_year_id,
            )
            .with_for_update()
        )
        if state is None:
            raise GenerationValidationError("Scheduler state disappeared before commit.")
        if job.requested_by_membership_id is None:
            raise GenerationValidationError(
                "A user-owned generation job is required to create a draft."
            )
        request_metadata = context.immutable_snapshot.get("request", {})
        replaced_draft_id = request_metadata.get("replace_pending_draft_id")
        if state.pending_draft_id != replaced_draft_id:
            raise GenerationValidationError("Pending draft changed before final commit.")

        now = self._aware_now()
        if replaced_draft_id is not None:
            old_draft = await self._db.scalar(
                select(models.ScheduleDraft)
                .where(
                    models.ScheduleDraft.id == replaced_draft_id,
                    models.ScheduleDraft.organization_id == context.organization_id,
                    models.ScheduleDraft.school_year_id == context.school_year_id,
                    models.ScheduleDraft.draft_state == models.ScheduleDraftState.PENDING,
                )
                .with_for_update()
            )
            if old_draft is None:
                raise GenerationValidationError("Replacement draft is no longer pending.")
            old_draft.draft_state = models.ScheduleDraftState.REPLACED
            old_draft.decided_by_membership_id = job.requested_by_membership_id
            old_draft.decided_at = now
            await SchedulerRecoveryService(self._db).cancel_draft_recovery_links(
                context.organization_id,
                context.school_year_id,
                old_draft.id,
            )
            await self._db.flush()

        policy_snapshot = context.immutable_snapshot.get("repair_policy")
        draft = models.ScheduleDraft(
            organization_id=context.organization_id,
            school_year_id=context.school_year_id,
            generation_job_id=job.id,
            strategy=context.strategy,
            result_category=result.result_category,
            trigger_type=context.trigger_type,
            generation_input_fingerprint=job.generation_input_fingerprint,
            scheduler_state_version_used=job.scheduler_state_version_used,
            debt_basis_fingerprint=job.debt_basis_fingerprint,
            repair_policy_snapshot_json=policy_snapshot,
            repair_policy_snapshot_hash=job.repair_policy_snapshot_hash,
            editable_start_date=(
                None
                if policy_snapshot is None
                else date.fromisoformat(policy_snapshot["editable_start_date"])
            ),
            recovery_escalation_level=result.recovery_escalation_level,
            adaptation_level=result.adaptation_level,
            projected_completion_date=result.projected_completion_date,
            hard_end_date=result.hard_end_date,
            summary_json=result.summary,
            partial_recovery_blocker_type=result.partial_recovery_blocker_type,
            main_blocker_message=result.main_blocker_message,
            recommended_actions_json=list(result.recommended_actions) or None,
            warnings_json=list(result.warnings) or None,
            metrics_json=result.metrics or None,
            created_by_membership_id=job.requested_by_membership_id,
        )
        self._db.add(draft)
        await self._db.flush()

        draft_blocks: list[models.ScheduleDraftBlock] = []
        for spec in result.blocks:
            block = models.ScheduleDraftBlock(
                organization_id=context.organization_id,
                school_year_id=context.school_year_id,
                draft_id=draft.id,
                source_active_block_id=spec.source_active_block_id,
                stable_block_key=spec.stable_block_key,
                class_id=spec.class_id,
                subject_id=spec.subject_id,
                teacher_id=spec.teacher_id,
                room_id=spec.room_id,
                room_type_id=spec.room_type_id,
                date=spec.date,
                timeslot_id=spec.timeslot_id,
                duration_minutes=spec.duration_minutes,
                module_sequence_index=spec.module_sequence_index,
                is_recovery_block=spec.is_recovery_block,
                recovery_source_occurrence_id=spec.recovery_source_occurrence_id,
                recovery_source_occurrence_revision=spec.recovery_source_occurrence_revision,
                change_type=spec.change_type,
                reason_code=spec.reason_code,
            )
            self._db.add(block)
            draft_blocks.append(block)
        await self._db.flush()

        recovery = SchedulerRecoveryService(self._db)
        for block in draft_blocks:
            if (
                block.is_recovery_block
                and block.change_type == models.ScheduleDraftBlockChangeType.ADDED
            ):
                await recovery.plan_draft_recovery(
                    context.organization_id,
                    context.school_year_id,
                    block.id,
                )

        self._db.add_all(
            SchedulerDiffService(self._db).build_entries(
                context,
                draft,
                result.blocks,
                draft_blocks,
            )
        )

        await self._assert_can_continue(context.job_id, context.deadline_at)
        state.pending_draft_id = draft.id
        state.lock_version += 1
        job.job_status = models.ScheduleGenerationJobStatus.SUCCEEDED
        job.result_category = result.result_category
        job.finished_at = now
        job.duration_ms = self._elapsed_ms(elapsed_start)
        await self._db.commit()
        emit_scheduler_job_event(
            "generation_succeeded",
            job,
            result=result,
            draft_id=draft.id,
        )
        return job

    async def _run_before_deadline(
        self,
        operation: Callable[[], Awaitable[Any]],
        deadline_at: datetime,
        timeout_message: str,
    ) -> Any:
        remaining = (deadline_at - self._aware_now()).total_seconds()
        if remaining <= 0:
            raise GenerationTimedOutError(timeout_message)
        try:
            return await asyncio.wait_for(operation(), timeout=remaining)
        except TimeoutError as exc:
            raise GenerationTimedOutError(timeout_message) from exc

    async def _assert_can_continue(
        self,
        job_id: int,
        deadline_at: datetime,
        *,
        end_transaction: bool = False,
    ) -> None:
        await self._install_tenant_context()
        job = await self._db.get(models.ScheduleGenerationJob, job_id)
        if job is None:
            raise GenerationRuntimeError("Generation job no longer exists.")
        await self._db.refresh(job)
        if job.job_status == models.ScheduleGenerationJobStatus.CANCEL_REQUESTED:
            raise GenerationCanceledError("Generation cancellation was requested.")
        if self._aware_now() >= deadline_at:
            raise GenerationTimedOutError("Generation exceeded its five-minute deadline.")
        if end_transaction and self._organization_id is not None:
            await self._db.rollback()

    async def _finish_without_output(
        self,
        job_id: int,
        elapsed_start: float,
        result: NoValidGenerationOutput | None = None,
    ) -> models.ScheduleGenerationJob:
        job = await self._locked_job(job_id)
        job.job_status = models.ScheduleGenerationJobStatus.NO_VALID_OUTPUT
        job.result_category = models.ScheduleGenerationResultCategory.NO_VALID_OUTPUT
        job.failure_code = FAILURE_NO_VALID_OUTPUT
        job.failure_message = (
            "No validated draft could be produced."
            if result is None or not result.blockers
            else " | ".join(result.blockers)[:2000]
        )
        job.finished_at = self._aware_now()
        job.duration_ms = self._elapsed_ms(elapsed_start)
        await self._db.commit()
        emit_scheduler_job_event(
            "generation_no_valid_output",
            job,
            result=result,
            hard_constraint_failures=(0 if result is None else len(result.blockers)),
        )
        return job

    async def _finish_failure(
        self,
        job_id: int,
        status: models.ScheduleGenerationJobStatus,
        code: str,
        message: str,
        elapsed_start: float,
    ) -> models.ScheduleGenerationJob:
        await self._db.rollback()
        job = await self._locked_job(job_id)
        if job.job_status not in (
            models.ScheduleGenerationJobStatus.QUEUED,
            models.ScheduleGenerationJobStatus.RUNNING,
            models.ScheduleGenerationJobStatus.CANCEL_REQUESTED,
        ):
            return job
        finished_at = self._aware_now()
        job.job_status = status
        job.result_category = None
        job.failure_code = code
        job.failure_message = message[:2000]
        if job.started_at is None:
            job.started_at = finished_at
        job.finished_at = finished_at
        job.duration_ms = self._elapsed_ms(elapsed_start)
        await self._db.commit()
        event_name = {
            FAILURE_CANCELED: "generation_canceled",
            FAILURE_TIMED_OUT: "generation_timed_out",
        }.get(code, "generation_failed")
        emit_scheduler_job_event(
            event_name,
            job,
            hard_constraint_failures=(1 if code == FAILURE_VALIDATION else 0),
        )
        return job

    async def _locked_job(self, job_id: int) -> models.ScheduleGenerationJob:
        await self._install_tenant_context()
        job = await self._db.scalar(
            select(models.ScheduleGenerationJob)
            .where(
                models.ScheduleGenerationJob.id == job_id,
                *(
                    (models.ScheduleGenerationJob.organization_id == self._organization_id,)
                    if self._organization_id is not None
                    else ()
                ),
            )
            .with_for_update()
        )
        if job is None:
            raise GenerationRuntimeError("Generation job was not found.")
        return job

    async def _install_tenant_context(self) -> None:
        if self._organization_id is not None:
            await set_async_tenant_context(self._db, self._organization_id)

    def _aware_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise GenerationRuntimeError("Generation runtime clock must be timezone-aware.")
        return value

    def _elapsed_ms(self, started: float) -> int:
        return max(0, int(round((self._elapsed_clock() - started) * 1000)))
