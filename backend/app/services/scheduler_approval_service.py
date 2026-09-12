from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.scheduler.domain.contracts import DraftBlockSpec
from app.services.scheduler_complete_demand import CompleteDemandLedgerBuilder
from app.services.scheduler_curriculum_validation import validate_curriculum_coverage
from app.services.scheduler_debt_service import SchedulerDebtService
from app.services.scheduler_editable_boundary import EditableBoundaryBuilder
from app.services.scheduler_fingerprint_service import SchedulerFingerprintService
from app.services.scheduler_incremental_demand import IncrementalDemandLedgerBuilder
from app.services.scheduler_recovery_service import SchedulerRecoveryService
from app.services.scheduler_recovery_validation import validate_recovery_identity
from app.services.scheduler_target_validator import (
    SchedulerTargetValidationError,
    SchedulerTargetValidator,
)


class SchedulerApprovalError(RuntimeError):
    pass


class DraftApprovalNotFoundError(SchedulerApprovalError):
    pass


class DraftApprovalConflictError(SchedulerApprovalError):
    def __init__(self, message: str, draft_state: models.ScheduleDraftState):
        super().__init__(message)
        self.draft_state = draft_state


@dataclass(frozen=True)
class ApprovalResult:
    draft_id: int
    draft_state: str
    school_year_publication_state: str
    active_schedule_version_id: str
    active_block_count: int


class SchedulerApprovalService:
    def __init__(self, db: AsyncSession):
        self._db = db
        self._fingerprints = SchedulerFingerprintService(db)

    async def approve(
        self,
        organization_id: int,
        draft_id: int,
        *,
        decided_by_membership_id: int,
        now: datetime | None = None,
    ) -> ApprovalResult:
        instant = now or datetime.now(UTC)
        draft = await self.validate_preconditions(
            organization_id,
            draft_id,
            decided_by_membership_id=decided_by_membership_id,
            now=instant,
        )
        if draft.strategy == models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR:
            return await self._approve_repair(
                organization_id,
                draft,
                decided_by_membership_id,
                instant,
            )
        state = await self._locked_state(organization_id, draft.school_year_id)
        existing = list(
            await self._db.scalars(
                select(models.ActiveScheduleBlock.id).where(
                    models.ActiveScheduleBlock.organization_id == organization_id,
                    models.ActiveScheduleBlock.school_year_id == draft.school_year_id,
                    models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
                )
            )
        )
        if existing:
            raise DraftApprovalConflictError(
                "A complete first schedule cannot overwrite an active schedule.",
                draft.draft_state,
            )
        blocks = await self._draft_blocks(organization_id, draft)
        current = await self._fingerprints.generation_input_fingerprint(
            organization_id,
            draft.school_year_id,
            draft.strategy,
        )
        specs = self._specs(blocks)
        self._validate_target(current.snapshot, specs, complete=True, draft=draft)
        await self._validate_recovery_link_consistency(
            organization_id,
            draft,
            blocks,
        )
        version_id = f"draft-{draft.id}"
        for block in blocks:
            self._db.add(
                models.ActiveScheduleBlock(
                    organization_id=organization_id,
                    school_year_id=draft.school_year_id,
                    schedule_version_id=version_id,
                    stable_block_key=block.stable_block_key,
                    class_id=block.class_id,
                    subject_id=block.subject_id,
                    teacher_id=block.teacher_id,
                    room_id=block.room_id,
                    date=block.date,
                    timeslot_id=block.timeslot_id,
                    duration_minutes=block.duration_minutes,
                    source_draft_block_id=block.id,
                    is_recovery_block=block.is_recovery_block,
                    status=models.ActiveScheduleBlockStatus.ACTIVE,
                )
            )
        draft.draft_state = models.ScheduleDraftState.APPROVED
        draft.decided_by_membership_id = decided_by_membership_id
        draft.decided_at = instant
        org_stmt = (
            select(models.Organization)
            .where(models.Organization.id == organization_id)
            .with_for_update()
        )
        org_result = await self._db.execute(org_stmt)
        org = org_result.scalar_one_or_none()
        if org and org.first_real_schedule_approved_at is None:
            org.first_real_schedule_approved_at = instant
        state.pending_draft_id = None
        state.school_year_publication_state = models.SchoolYearPublicationState.PUBLISHED
        state.active_schedule_version_id = version_id
        state.approved_scheduler_state_version = state.scheduler_state_version
        state.lock_version += 1
        await self._db.flush()
        return ApprovalResult(
            draft_id=draft.id,
            draft_state=draft.draft_state.value,
            school_year_publication_state=state.school_year_publication_state.value,
            active_schedule_version_id=version_id,
            active_block_count=len(blocks),
        )

    async def _approve_repair(
        self,
        organization_id: int,
        draft: models.ScheduleDraft,
        decided_by_membership_id: int,
        instant: datetime,
    ) -> ApprovalResult:
        state = await self._locked_state(organization_id, draft.school_year_id)
        blocks = await self._draft_blocks(organization_id, draft)
        current = await self._fingerprints.generation_input_fingerprint(
            organization_id,
            draft.school_year_id,
            draft.strategy,
        )
        specs = self._specs(blocks)
        boundary = EditableBoundaryBuilder().build(
            current.snapshot,
            draft.repair_policy_snapshot_json,
        )
        self._validate_target(
            current.snapshot,
            specs,
            complete=False,
            draft=draft,
            boundary=boundary,
        )
        await self._validate_recovery_link_consistency(
            organization_id,
            draft,
            blocks,
        )
        active_rows = list(
            await self._db.scalars(
                select(models.ActiveScheduleBlock)
                .where(
                    models.ActiveScheduleBlock.organization_id == organization_id,
                    models.ActiveScheduleBlock.school_year_id == draft.school_year_id,
                    models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
                )
                .order_by(models.ActiveScheduleBlock.id)
                .with_for_update()
            )
        )
        active = {row.id: row for row in active_rows}
        target_by_source: dict[int, tuple[models.ScheduleDraftBlock, DraftBlockSpec]] = {}
        for block, spec in zip(blocks, specs, strict=True):
            if spec.source_active_block_id is None:
                if spec.change_type != models.ScheduleDraftBlockChangeType.ADDED:
                    raise DraftApprovalConflictError(
                        "A repair target block has no active lineage.",
                        draft.draft_state,
                    )
                continue
            if (
                spec.source_active_block_id not in active
                or spec.source_active_block_id in target_by_source
                or spec.change_type == models.ScheduleDraftBlockChangeType.ADDED
            ):
                raise DraftApprovalConflictError(
                    "Repair target active lineage is invalid or duplicated.",
                    draft.draft_state,
                )
            target_by_source[spec.source_active_block_id] = (block, spec)
        for immutable in boundary.immutable_blocks:
            target = target_by_source.get(immutable["id"])
            if target is None or not self._same_active_and_spec(active[immutable["id"]], target[1]):
                raise DraftApprovalConflictError(
                    "The repair target changes or omits an immutable active block.",
                    draft.draft_state,
                )
            if target[1].change_type != models.ScheduleDraftBlockChangeType.UNCHANGED:
                raise DraftApprovalConflictError(
                    "Immutable active blocks must remain unchanged.",
                    draft.draft_state,
                )

        version_id = f"draft-{draft.id}"
        removed_ids: set[int] = set()
        replacement_sources: dict[int, models.ActiveScheduleBlock] = {}
        active_by_draft_block: dict[int, int] = {}
        new_pairs: list[tuple[models.ScheduleDraftBlock, models.ActiveScheduleBlock]] = []
        for active_id, row in active.items():
            target = target_by_source.get(active_id)
            if target is None:
                row.status = models.ActiveScheduleBlockStatus.REMOVED
                removed_ids.add(active_id)
                continue
            target_block, spec = target
            if spec.change_type == models.ScheduleDraftBlockChangeType.UNCHANGED:
                if not self._same_active_and_spec(row, spec):
                    raise DraftApprovalConflictError(
                        "An unchanged repair target differs from its active source.",
                        draft.draft_state,
                    )
                row.schedule_version_id = version_id
                active_by_draft_block[target_block.id] = row.id
                continue
            row.status = models.ActiveScheduleBlockStatus.REMOVED
            removed_ids.add(active_id)
            replacement_sources[active_id] = row
        await self._db.flush()

        for block, spec in zip(blocks, specs, strict=True):
            if spec.change_type == models.ScheduleDraftBlockChangeType.UNCHANGED:
                continue
            active_block = models.ActiveScheduleBlock(
                organization_id=organization_id,
                school_year_id=draft.school_year_id,
                schedule_version_id=version_id,
                stable_block_key=spec.stable_block_key,
                class_id=spec.class_id,
                subject_id=spec.subject_id,
                teacher_id=spec.teacher_id,
                room_id=spec.room_id,
                date=spec.date,
                timeslot_id=spec.timeslot_id,
                duration_minutes=spec.duration_minutes,
                source_draft_block_id=block.id,
                is_recovery_block=spec.is_recovery_block,
                status=models.ActiveScheduleBlockStatus.ACTIVE,
            )
            self._db.add(active_block)
            new_pairs.append((block, active_block))
        await self._db.flush()
        for block, active_block in new_pairs:
            active_by_draft_block[block.id] = active_block.id
        replacements = {
            source_id: active_by_draft_block[target_by_source[source_id][0].id]
            for source_id in replacement_sources
        }
        recovery = SchedulerRecoveryService(self._db)
        await recovery.reconcile_active_recovery_links(
            organization_id,
            draft.school_year_id,
            replacements,
            removed_ids - set(replacements),
        )
        await recovery.reconcile_approved_recovery_links(
            organization_id,
            draft.school_year_id,
            draft.id,
            active_by_draft_block,
        )
        draft.draft_state = models.ScheduleDraftState.APPROVED
        draft.decided_by_membership_id = decided_by_membership_id
        draft.decided_at = instant
        state.pending_draft_id = None
        state.active_schedule_version_id = version_id
        state.approved_scheduler_state_version = state.scheduler_state_version
        state.lock_version += 1
        await self._db.flush()
        return ApprovalResult(
            draft_id=draft.id,
            draft_state=draft.draft_state.value,
            school_year_publication_state=state.school_year_publication_state.value,
            active_schedule_version_id=version_id,
            active_block_count=len(blocks),
        )

    async def validate_preconditions(
        self,
        organization_id: int,
        draft_id: int,
        *,
        decided_by_membership_id: int,
        now: datetime | None = None,
    ) -> models.ScheduleDraft:
        instant = now or datetime.now(UTC)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SchedulerApprovalError("Approval time must be timezone-aware.")
        draft = await self._db.scalar(
            select(models.ScheduleDraft)
            .where(
                models.ScheduleDraft.id == draft_id,
                models.ScheduleDraft.organization_id == organization_id,
            )
            .with_for_update()
        )
        if draft is None:
            raise DraftApprovalNotFoundError("Schedule draft was not found.")
        state = await self._db.scalar(
            select(models.SchedulerSchoolYearState)
            .where(
                models.SchedulerSchoolYearState.organization_id == organization_id,
                models.SchedulerSchoolYearState.school_year_id == draft.school_year_id,
            )
            .with_for_update()
        )
        if (
            state is None
            or draft.draft_state != models.ScheduleDraftState.PENDING
            or state.pending_draft_id != draft.id
        ):
            raise DraftApprovalConflictError(
                "Only the current pending draft can be approved.",
                draft.draft_state,
            )

        expected_publication = (
            models.SchoolYearPublicationState.UNPUBLISHED
            if draft.strategy == models.ScheduleGenerationStrategy.COMPLETE_GENERATION
            else models.SchoolYearPublicationState.PUBLISHED
        )
        if state.school_year_publication_state != expected_publication:
            return await self._invalidate(
                draft,
                state,
                "The school-year publication state no longer matches this draft strategy.",
                decided_by_membership_id,
                instant,
            )

        current_generation = await self._fingerprints.generation_input_fingerprint(
            organization_id,
            draft.school_year_id,
            draft.strategy,
        )
        if current_generation.value != draft.generation_input_fingerprint:
            return await self._stale(
                draft,
                state,
                "Schedule conditions changed after this draft was generated.",
                decided_by_membership_id,
                instant,
            )
        if draft.strategy == models.ScheduleGenerationStrategy.COMPLETE_GENERATION:
            return draft

        current_policy = await self._fingerprints.repair_policy_snapshot(
            organization_id,
            draft.school_year_id,
            now=instant,
        )
        if current_policy.value != draft.repair_policy_snapshot_hash:
            return await self._stale(
                draft,
                state,
                "The repair policy changed after this draft was generated.",
                decided_by_membership_id,
                instant,
            )
        uses_debt = draft.trigger_type in (
            models.ScheduleGenerationTrigger.EXPLICIT_DEBT,
            models.ScheduleGenerationTrigger.MIXED,
        )
        uses_change = draft.trigger_type in (
            models.ScheduleGenerationTrigger.SCHEDULER_CHANGE,
            models.ScheduleGenerationTrigger.MIXED,
        )
        if uses_debt:
            current_debt = await self._fingerprints.debt_basis_fingerprint(
                organization_id,
                draft.school_year_id,
            )
            if current_debt is None:
                return await self._invalidate(
                    draft,
                    state,
                    "The explicit-debt trigger no longer exists.",
                    decided_by_membership_id,
                    instant,
                )
            if current_debt.value != draft.debt_basis_fingerprint:
                return await self._stale(
                    draft,
                    state,
                    "The explicit-debt basis changed after this draft was generated.",
                    decided_by_membership_id,
                    instant,
                )
        if uses_change:
            if state.approved_scheduler_state_version is None or (
                state.scheduler_state_version <= state.approved_scheduler_state_version
            ):
                return await self._invalidate(
                    draft,
                    state,
                    "The scheduler-change trigger no longer exists.",
                    decided_by_membership_id,
                    instant,
                )
            if state.scheduler_state_version != draft.scheduler_state_version_used:
                return await self._stale(
                    draft,
                    state,
                    "Scheduler conditions changed after this draft was generated.",
                    decided_by_membership_id,
                    instant,
                )
        return draft

    async def _locked_state(self, organization_id: int, school_year_id: int):
        state = await self._db.scalar(
            select(models.SchedulerSchoolYearState)
            .where(
                models.SchedulerSchoolYearState.organization_id == organization_id,
                models.SchedulerSchoolYearState.school_year_id == school_year_id,
            )
            .with_for_update()
        )
        if state is None:
            raise DraftApprovalConflictError(
                "Scheduler school-year state was not found.",
                models.ScheduleDraftState.INVALIDATED,
            )
        return state

    async def _draft_blocks(self, organization_id: int, draft):
        blocks = list(
            await self._db.scalars(
                select(models.ScheduleDraftBlock)
                .where(
                    models.ScheduleDraftBlock.organization_id == organization_id,
                    models.ScheduleDraftBlock.school_year_id == draft.school_year_id,
                    models.ScheduleDraftBlock.draft_id == draft.id,
                )
                .order_by(models.ScheduleDraftBlock.id)
            )
        )
        if not blocks and draft.strategy == models.ScheduleGenerationStrategy.COMPLETE_GENERATION:
            raise DraftApprovalConflictError(
                "An empty schedule draft cannot be approved.",
                draft.draft_state,
            )
        return blocks

    async def _validate_recovery_link_consistency(
        self,
        organization_id: int,
        draft: models.ScheduleDraft,
        blocks: list[models.ScheduleDraftBlock],
    ) -> None:
        links = list(
            await self._db.scalars(
                select(models.PlannedRecoveryLink)
                .join(
                    models.ScheduleDraftBlock,
                    and_(
                        models.ScheduleDraftBlock.id
                        == models.PlannedRecoveryLink.planned_draft_block_id,
                        models.ScheduleDraftBlock.organization_id
                        == models.PlannedRecoveryLink.organization_id,
                        models.ScheduleDraftBlock.school_year_id
                        == models.PlannedRecoveryLink.school_year_id,
                    ),
                )
                .where(
                    models.PlannedRecoveryLink.organization_id == organization_id,
                    models.PlannedRecoveryLink.school_year_id == draft.school_year_id,
                    models.ScheduleDraftBlock.draft_id == draft.id,
                )
                .with_for_update(of=models.PlannedRecoveryLink)
            )
        )
        expected = {
            block.id: block
            for block in blocks
            if block.is_recovery_block
            and block.change_type == models.ScheduleDraftBlockChangeType.ADDED
        }
        actual = {link.planned_draft_block_id: link for link in links}
        if set(actual) != set(expected):
            raise DraftApprovalConflictError(
                "Draft recovery blocks and planned recovery links are inconsistent.",
                draft.draft_state,
            )

        debt_entries = {}
        if expected:
            debt_entries = {
                (entry.occurrence_id, entry.occurrence_revision): entry
                for entry in (
                    await SchedulerDebtService(self._db).active_debt_ledger(
                        organization_id,
                        draft.school_year_id,
                    )
                ).entries
            }

        recovered_minutes = 0
        for block_id, block in expected.items():
            link = actual[block_id]
            if (
                link.status != models.PlannedRecoveryLinkStatus.PLANNED
                or link.planned_active_block_id is not None
                or link.debt_occurrence_id != block.recovery_source_occurrence_id
                or link.debt_occurrence_revision != block.recovery_source_occurrence_revision
                or link.class_id != block.class_id
                or link.subject_id != block.subject_id
                or link.teacher_id != block.teacher_id
                or link.planned_recovery_minutes <= 0
                or link.planned_recovery_minutes > block.duration_minutes
            ):
                raise DraftApprovalConflictError(
                    "A planned recovery link does not match its draft recovery block.",
                    draft.draft_state,
                )
            debt_entry = debt_entries.get(
                (block.recovery_source_occurrence_id, block.recovery_source_occurrence_revision)
            )
            if debt_entry is None:
                raise DraftApprovalConflictError(
                    "A planned recovery link references debt that is no longer unresolved.",
                    draft.draft_state,
                )
            assigned_teacher = await self._db.scalar(
                select(models.ClassSubjectLink.teacher_id).where(
                    models.ClassSubjectLink.organization_id == organization_id,
                    models.ClassSubjectLink.class_id == block.class_id,
                    models.ClassSubjectLink.subject_id == block.subject_id,
                )
            )
            eligible_teacher = await self._db.scalar(
                select(models.teacher_subject_link.c.teacher_id).where(
                    models.teacher_subject_link.c.organization_id == organization_id,
                    models.teacher_subject_link.c.teacher_id == block.teacher_id,
                    models.teacher_subject_link.c.subject_id == block.subject_id,
                )
            )
            identity_violations = validate_recovery_identity(
                self._specs([block])[0],
                {
                    "occurrence_id": debt_entry.occurrence_id,
                    "occurrence_revision": debt_entry.occurrence_revision,
                    "class_id": debt_entry.class_id,
                    "subject_id": debt_entry.subject_id,
                    "teacher_id": debt_entry.teacher_id,
                    "unresolved_debt_minutes": debt_entry.remaining_minutes,
                },
                {(block.class_id, block.subject_id): assigned_teacher},
                ({(block.teacher_id, block.subject_id)} if eligible_teacher is not None else set()),
                requested_minutes=link.planned_recovery_minutes,
            )
            if identity_violations:
                raise DraftApprovalConflictError(identity_violations[0], draft.draft_state)
            recovered_minutes += link.planned_recovery_minutes

        if draft.strategy != models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR:
            return
        summary = draft.summary_json or {}
        metrics = draft.metrics_json or {}
        remaining = summary.get("remaining_unscheduled_minutes")
        if (
            summary.get("recovered_minutes") != recovered_minutes
            or not isinstance(remaining, int)
            or remaining < 0
            or (
                "recovered_minutes" in metrics and metrics["recovered_minutes"] != recovered_minutes
            )
            or (
                "residual_debt_minutes" in metrics and metrics["residual_debt_minutes"] != remaining
            )
            or (
                draft.result_category == models.ScheduleGenerationResultCategory.PARTIAL_RECOVERY
                and remaining <= 0
            )
            or (
                draft.result_category == models.ScheduleGenerationResultCategory.COMPLETE_SUCCESS
                and remaining != 0
            )
        ):
            raise DraftApprovalConflictError(
                "Draft recovery metrics do not match its planned recovery links.",
                draft.draft_state,
            )

    @staticmethod
    def _specs(blocks) -> tuple[DraftBlockSpec, ...]:
        return tuple(
            DraftBlockSpec(
                stable_block_key=row.stable_block_key,
                source_active_block_id=row.source_active_block_id,
                class_id=row.class_id,
                subject_id=row.subject_id,
                teacher_id=row.teacher_id,
                room_id=row.room_id,
                room_type_id=row.room_type_id,
                date=row.date,
                timeslot_id=row.timeslot_id,
                duration_minutes=row.duration_minutes,
                module_sequence_index=row.module_sequence_index,
                is_recovery_block=row.is_recovery_block,
                recovery_source_occurrence_id=row.recovery_source_occurrence_id,
                recovery_source_occurrence_revision=row.recovery_source_occurrence_revision,
                change_type=row.change_type,
                reason_code=row.reason_code,
            )
            for row in blocks
        )

    @staticmethod
    def _same_active_and_spec(
        active: models.ActiveScheduleBlock,
        spec: DraftBlockSpec,
    ) -> bool:
        return (
            active.stable_block_key == spec.stable_block_key
            and active.class_id == spec.class_id
            and active.subject_id == spec.subject_id
            and active.teacher_id == spec.teacher_id
            and active.room_id == spec.room_id
            and active.date == spec.date
            and active.timeslot_id == spec.timeslot_id
            and active.duration_minutes == spec.duration_minutes
            and active.is_recovery_block == spec.is_recovery_block
        )

    @staticmethod
    def _validate_target(snapshot, specs, *, complete, draft, boundary=None) -> None:
        try:
            SchedulerTargetValidator.validate(snapshot, specs, complete=complete)
        except SchedulerTargetValidationError as exc:
            raise DraftApprovalConflictError(str(exc), draft.draft_state) from exc
        if complete:
            return
        if boundary is None:
            boundary = EditableBoundaryBuilder().build(
                snapshot,
                draft.repair_policy_snapshot_json,
            )
        curriculum = IncrementalDemandLedgerBuilder().build(
            snapshot,
            immutable_block_ids={row["id"] for row in boundary.immutable_blocks},
        )
        if not curriculum.is_complete:
            raise DraftApprovalConflictError(
                "Adaptive curriculum demand is incomplete: " + " ".join(curriculum.blockers),
                draft.draft_state,
            )
        violations = validate_curriculum_coverage(
            curriculum,
            specs,
            select=lambda block: (
                block.change_type == models.ScheduleDraftBlockChangeType.ADDED
                and not block.is_recovery_block
                and block.reason_code == "NEW_CURRICULUM_DEMAND"
            ),
            slot_start_values={
                row["id"]: str(row.get("start_time", ""))
                for row in snapshot.get("timetable_grid", [])
            },
        )
        if violations:
            raise DraftApprovalConflictError(
                "Adaptive target does not exactly satisfy incremental curriculum demand: "
                + violations[0].message,
                draft.draft_state,
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
            raise DraftApprovalConflictError(
                "Adaptive final curriculum demand is incomplete: "
                + " ".join(final_ledger.blockers),
                draft.draft_state,
            )
        final_items = {(item.class_id, item.subject_id) for item in final_ledger.items}
        final_violations = validate_curriculum_coverage(
            final_ledger,
            specs,
            select=lambda block: (
                not block.is_recovery_block
                and (block.class_id, block.subject_id) in final_items
                and (
                    block.source_active_block_id is not None
                    or block.reason_code == "NEW_CURRICULUM_DEMAND"
                )
            ),
            slot_start_values={
                row["id"]: str(row.get("start_time", ""))
                for row in snapshot.get("timetable_grid", [])
            },
        )
        if final_violations:
            raise DraftApprovalConflictError(
                "Adaptive target does not cover delivered, retained, and added curriculum: "
                + final_violations[0].message,
                draft.draft_state,
            )

    async def _stale(
        self,
        draft,
        state,
        reason,
        user_id,
        instant,
    ):
        draft.draft_state = models.ScheduleDraftState.STALE
        draft.stale_reason = reason
        draft.decided_by_membership_id = user_id
        draft.decided_at = instant
        state.pending_draft_id = None
        state.lock_version += 1
        await SchedulerRecoveryService(self._db).cancel_draft_recovery_links(
            draft.organization_id,
            draft.school_year_id,
            draft.id,
        )
        await self._db.flush()
        raise DraftApprovalConflictError(reason, models.ScheduleDraftState.STALE)

    async def _invalidate(
        self,
        draft,
        state,
        reason,
        user_id,
        instant,
    ):
        draft.draft_state = models.ScheduleDraftState.INVALIDATED
        draft.invalidated_reason = reason
        draft.decided_by_membership_id = user_id
        draft.decided_at = instant
        state.pending_draft_id = None
        state.lock_version += 1
        await SchedulerRecoveryService(self._db).cancel_draft_recovery_links(
            draft.organization_id,
            draft.school_year_id,
            draft.id,
        )
        await self._db.flush()
        raise DraftApprovalConflictError(reason, models.ScheduleDraftState.INVALIDATED)
