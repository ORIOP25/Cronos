from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from time import monotonic
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import models
from app.core.exceptions import new_error_reference
from app.core.logging import safe_exception_frames
from app.db.tenant import set_async_tenant_context
from app.scheduler.domain.calendar import blocked_dates_by_class
from app.scheduler.domain.contracts import (
    DraftBlockSpec,
    NoValidGenerationOutput,
    ValidatedGenerationResult,
)
from app.scheduler.domain.validation import GenerationEnvelopeValidator
from app.services import grid_version_service
from app.services.scheduler_complete_demand import CompleteDemandLedgerBuilder
from app.services.scheduler_curriculum_validation import validate_curriculum_coverage
from app.services.scheduler_diff_service import SchedulerDiffService
from app.services.scheduler_editable_boundary import EditableBoundaryBuilder
from app.services.scheduler_fingerprint_service import SchedulerFingerprintService
from app.services.scheduler_incremental_demand import IncrementalDemandLedgerBuilder
from app.services.scheduler_observability import emit_scheduler_job_event
from app.services.scheduler_recovery_service import SchedulerRecoveryService
from app.services.scheduler_recovery_validation import validate_recovery_identity
from app.services.scheduler_target_validator import (
    SchedulerTargetValidationError,
    SchedulerTargetValidator,
)

GENERATION_CAP_SECONDS = 5 * 60
FINAL_COMMIT_RESERVE_SECONDS = 15
ENGINE_RETURN_RESERVE_SECONDS = 1
CANCELLATION_POLL_SECONDS = 0.05

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
    stop_event: threading.Event = field(
        default_factory=threading.Event,
        repr=False,
        compare=False,
    )
    solver_stop_event: threading.Event = field(
        default_factory=threading.Event,
        repr=False,
        compare=False,
    )

    @property
    def solve_deadline_at(self) -> datetime:
        return self.deadline_at - timedelta(
            seconds=FINAL_COMMIT_RESERVE_SECONDS + ENGINE_RETURN_RESERVE_SECONDS
        )

    async def ensure_can_continue(self) -> None:
        if self.stop_event.is_set():
            raise GenerationCanceledError("Generation work was asked to stop.")
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
        session_factory: Callable[[], AsyncSession] | None = None,
    ):
        self._db = db
        self._clock = clock or (lambda: datetime.now(UTC))
        self._elapsed_clock = elapsed_clock or monotonic
        self._session_factory = session_factory or async_sessionmaker(
            bind=db.bind,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

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
            engine_task = asyncio.create_task(engine(context))
            cancellation_task = asyncio.create_task(self._monitor_cancellation(job_id, context))
            try:
                completed, _ = await asyncio.wait({engine_task}, timeout=solve_seconds)
                if not completed:
                    # Ask solver threads to return without turning a deadline into user cancellation.
                    context.solver_stop_event.set()
                    engine_return_deadline = context.deadline_at - timedelta(
                        seconds=FINAL_COMMIT_RESERVE_SECONDS
                    )
                    cleanup_seconds = max(
                        0.0,
                        (engine_return_deadline - self._aware_now()).total_seconds(),
                    )
                    if cleanup_seconds > 0:
                        try:
                            await asyncio.wait_for(engine_task, timeout=cleanup_seconds)
                        except TimeoutError:
                            pass
                        except Exception as exc:
                            logger.warning(
                                "scheduler_generation_cleanup_failure",
                                job_id=job_id,
                                organization_id=organization_id,
                                error_type=type(exc).__name__,
                                exception_frames=safe_exception_frames(exc),
                            )
                    if not engine_task.done():
                        engine_task.cancel()
                        raise GenerationTimedOutError(
                            "Generation exceeded its solver time budget before an incumbent returned."
                        )
                try:
                    result = engine_task.result()
                except asyncio.CancelledError as exc:
                    raise GenerationTimedOutError(
                        "Generation exceeded its solver time budget before an incumbent returned."
                    ) from exc
            finally:
                cancellation_task.cancel()
                await asyncio.gather(cancellation_task, return_exceptions=True)
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
            validation_started = self._elapsed_clock()
            await self._run_before_deadline(
                lambda: self._validate_result(context, result),
                context.deadline_at,
                "Generation validation exceeded the five-minute deadline.",
            )
            result = replace(
                result,
                metrics={
                    **result.metrics,
                    "independent_validation_duration_ms": self._elapsed_ms(validation_started),
                },
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
            logger.error(
                "scheduler_generation_unexpected_failure",
                job_id=job_id,
                organization_id=organization_id,
                error_type=type(exc).__name__,
                exception_frames=safe_exception_frames(exc),
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
            grid_version_id=job.grid_version_id,
        )
        debt = None
        policy = None
        if job.strategy == models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR:
            debt = await fingerprints.debt_basis_fingerprint(
                job.organization_id,
                job.school_year_id,
            )
        if job.strategy in (
            models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR,
            models.ScheduleGenerationStrategy.GRID_CHANGE,
        ):
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
        policy = context.immutable_snapshot.get("repair_policy")
        try:
            boundary = None if policy is None else EditableBoundaryBuilder().build(snapshot, policy)
        except (KeyError, TypeError, ValueError) as exc:
            raise GenerationValidationError(str(exc)) from exc
        curriculum = IncrementalDemandLedgerBuilder().build(
            snapshot,
            immutable_block_ids=(
                set() if boundary is None else {row["id"] for row in boundary.immutable_blocks}
            ),
        )
        if not curriculum.is_complete:
            raise GenerationValidationError(
                "Adaptive curriculum demand is incomplete: " + " ".join(curriculum.blockers)
            )
        curriculum_items = {(item.class_id, item.subject_id): item for item in curriculum.items}
        slot_starts = {
            row["id"]: str(row.get("start_time", "")) for row in snapshot.get("timetable_grid", [])
        }
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
        blocked_by_class = blocked_dates_by_class(
            snapshot.get("calendar_events", []),
            (block.class_id for block in result.blocks),
        )
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
                or block.date in blocked_by_class.get(block.class_id, ())
            ):
                raise GenerationValidationError(
                    "Adaptive target violates the latest scheduler inputs."
                )
            if block.change_type == models.ScheduleDraftBlockChangeType.ADDED:
                if block.source_active_block_id is not None:
                    raise GenerationValidationError(
                        "Added repair blocks cannot have active lineage."
                    )
                curriculum_item = curriculum_items.get((block.class_id, block.subject_id))
                if not block.is_recovery_block and (
                    curriculum_item is not None or block.reason_code == "NEW_CURRICULUM_DEMAND"
                ):
                    if curriculum_item is None:
                        raise GenerationValidationError(
                            "Curriculum addition references demand outside its snapshot."
                        )
                    if block.reason_code != "NEW_CURRICULUM_DEMAND":
                        raise GenerationValidationError(
                            "Curriculum addition has an invalid reason code."
                        )
                    valid_sequences = {
                        module.sequence
                        for module in curriculum_item.modules
                        if module.required_minutes > 0
                    }
                    if block.module_sequence_index not in valid_sequences:
                        raise GenerationValidationError(
                            "Curriculum addition module sequence is invalid."
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

        debt_rows = {
            (int(row["occurrence_id"]), int(row["occurrence_revision"])): row
            for row in (context.immutable_snapshot.get("debt_basis") or {}).get("items", [])
        }
        debt_items = {
            key: int(row.get("unresolved_debt_minutes", 0)) for key, row in debt_rows.items()
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
            identity_violations = validate_recovery_identity(
                block,
                debt_rows[key],
                assignments,
                qualifications,
            )
            if identity_violations:
                raise GenerationValidationError(identity_violations[0])
            recovered_by_debt[key] = recovered_by_debt.get(key, 0) + block.duration_minutes
        if any(recovered_by_debt.get(key, 0) > minutes for key, minutes in debt_items.items()):
            raise GenerationValidationError("Repair over-recovers an explicit debt entry.")

        curriculum_violations = validate_curriculum_coverage(
            curriculum,
            result.blocks,
            select=lambda block: (
                block.change_type == models.ScheduleDraftBlockChangeType.ADDED
                and not block.is_recovery_block
                and block.reason_code == "NEW_CURRICULUM_DEMAND"
            ),
            slot_start_values=slot_starts,
        )
        if curriculum_violations:
            raise GenerationValidationError(
                "Adaptive target does not exactly satisfy incremental curriculum demand: "
                + curriculum_violations[0].message
            )
        configured_subjects = {
            row.get("subject_id") for row in snapshot.get("module_accounting", [])
        }
        final_ledger = CompleteDemandLedgerBuilder().build_for_assignments(
            snapshot,
            [
                row
                for row in snapshot.get("class_subject_requirements", [])
                if row.get("subject_id") in configured_subjects
            ],
            allow_empty=True,
        )
        if final_ledger.items and not final_ledger.is_complete:
            raise GenerationValidationError(
                "Adaptive final curriculum demand is incomplete: " + " ".join(final_ledger.blockers)
            )
        final_items = {(item.class_id, item.subject_id) for item in final_ledger.items}
        final_coverage_violations = validate_curriculum_coverage(
            final_ledger,
            result.blocks,
            select=lambda block: (
                not block.is_recovery_block
                and (block.class_id, block.subject_id) in final_items
                and (
                    block.source_active_block_id is not None
                    or block.reason_code == "NEW_CURRICULUM_DEMAND"
                )
            ),
            slot_start_values=slot_starts,
        )
        if final_coverage_violations:
            raise GenerationValidationError(
                "Adaptive target does not cover delivered, retained, and added curriculum: "
                + final_coverage_violations[0].message
            )
        scheduled_curriculum_minutes = sum(
            block.duration_minutes
            for block in result.blocks
            if (
                block.change_type == models.ScheduleDraftBlockChangeType.ADDED
                and not block.is_recovery_block
                and block.reason_code == "NEW_CURRICULUM_DEMAND"
            )
        )
        curriculum_metrics = (
            ("required_curriculum_minutes", curriculum.required_minutes),
            ("scheduled_curriculum_minutes", scheduled_curriculum_minutes),
        )
        for name, expected_value in curriculum_metrics:
            summary_value = result.summary.get(name)
            metrics_value = result.metrics.get(name)
            if curriculum.required_minutes > 0 and (
                summary_value != expected_value or metrics_value != expected_value
            ):
                raise GenerationValidationError(
                    "Adaptive curriculum metrics do not match target blocks."
                )
            if summary_value is not None and summary_value != expected_value:
                raise GenerationValidationError(
                    "Adaptive curriculum summary metrics do not match target blocks."
                )
            if metrics_value is not None and metrics_value != expected_value:
                raise GenerationValidationError(
                    "Adaptive curriculum metrics do not match target blocks."
                )
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
        violations = validate_curriculum_coverage(
            ledger,
            blocks,
            slot_start_values={
                row["id"]: str(row.get("start_time", ""))
                for row in snapshot.get("timetable_grid", [])
            },
        )
        if violations:
            raise GenerationValidationError(violations[0].message)

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
        persistence_started = self._elapsed_clock()
        job = await self._locked_job(context.job_id)
        if job.job_status != models.ScheduleGenerationJobStatus.RUNNING:
            if job.job_status in {
                models.ScheduleGenerationJobStatus.CANCEL_REQUESTED,
                models.ScheduleGenerationJobStatus.CANCELED,
            }:
                raise GenerationCanceledError("Generation cancellation was requested.")
            raise GenerationRuntimeError("Generation job is no longer running.")
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
        persistence_duration_ms = self._elapsed_ms(persistence_started)
        draft.metrics_json = {
            **(draft.metrics_json or {}),
            "draft_persistence_duration_ms": persistence_duration_ms,
        }
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
            result=replace(
                result,
                metrics={
                    **result.metrics,
                    "draft_persistence_duration_ms": persistence_duration_ms,
                },
            ),
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
        if job.job_status in {
            models.ScheduleGenerationJobStatus.CANCEL_REQUESTED,
            models.ScheduleGenerationJobStatus.CANCELED,
        }:
            raise GenerationCanceledError("Generation cancellation was requested.")
        if job.job_status != models.ScheduleGenerationJobStatus.RUNNING:
            raise GenerationRuntimeError("Generation job is no longer running.")
        if self._aware_now() >= deadline_at:
            raise GenerationTimedOutError("Generation exceeded its five-minute deadline.")
        if end_transaction and self._organization_id is not None:
            await self._db.rollback()

    async def _monitor_cancellation(
        self,
        job_id: int,
        context: GenerationExecutionContext,
    ) -> None:
        """Poll the durable cancellation flag while solver work runs off-thread."""

        try:
            async with self._session_factory() as monitor_db:
                while not context.stop_event.is_set():
                    await asyncio.sleep(CANCELLATION_POLL_SECONDS)
                    if self._organization_id is not None:
                        await set_async_tenant_context(monitor_db, self._organization_id)
                    job = await monitor_db.get(models.ScheduleGenerationJob, job_id)
                    if job is not None and job.job_status in {
                        models.ScheduleGenerationJobStatus.CANCEL_REQUESTED,
                        models.ScheduleGenerationJobStatus.CANCELED,
                    }:
                        context.stop_event.set()
                        context.solver_stop_event.set()
                        return
                    await monitor_db.rollback()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "scheduler_generation_cancellation_poll_failure",
                job_id=job_id,
                organization_id=self._organization_id,
                error_type=type(exc).__name__,
                exception_frames=safe_exception_frames(exc),
            )

    async def _reject_grid_change_proposal(self, job: models.ScheduleGenerationJob) -> None:
        grid_version_id = getattr(job, "grid_version_id", None)
        if grid_version_id is None:
            return
        await grid_version_service.reject_pending_grid_version(
            self._db, job.organization_id, grid_version_id
        )

    async def _finish_without_output(
        self,
        job_id: int,
        elapsed_start: float,
        result: NoValidGenerationOutput | None = None,
    ) -> models.ScheduleGenerationJob:
        job = await self._locked_job(job_id)
        if job.job_status != models.ScheduleGenerationJobStatus.RUNNING:
            return job
        job.job_status = models.ScheduleGenerationJobStatus.NO_VALID_OUTPUT
        job.result_category = models.ScheduleGenerationResultCategory.NO_VALID_OUTPUT
        job.failure_code = FAILURE_NO_VALID_OUTPUT
        job.failure_reference = job.failure_reference or new_error_reference()
        job.failure_message = (
            "No validated draft could be produced."
            if result is None or not result.blockers
            else " | ".join(result.blockers)[:2000]
        )
        job.finished_at = self._aware_now()
        job.duration_ms = self._elapsed_ms(elapsed_start)
        await self._reject_grid_change_proposal(job)
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
        job.failure_reference = job.failure_reference or new_error_reference()
        job.failure_message = message[:2000]
        if job.started_at is None:
            job.started_at = finished_at
        job.finished_at = finished_at
        job.duration_ms = self._elapsed_ms(elapsed_start)
        await self._reject_grid_change_proposal(job)
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
