"""Atomic proposal persistence, approval and rejection for scheduler v1.

Finalization and approval own their transactions: either the whole version,
its lessons, slices, reservations and the clock commit together, or nothing
changes. Staleness is an audited decision: a proposal that no longer matches
the current data is marked STALE and never approved silently.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.scheduler.application.publishing import ProposalPayload, plan_recovery_allocations
from app.scheduler.domain.candidate import (
    CandidateSchedule,
    SchedulingStrategy,
)
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.infrastructure.models import (
    CurricularDebt,
    SchedulerJobV1,
    SchedulerLessonLogV1,
    SchedulerLessonSliceV1,
    SchedulerLessonV1,
    SchedulerProposalV1,
    SchedulerRecoveryReservationV1,
    SchedulerVersionV1,
)
from app.scheduler.infrastructure.progress import load_active_version_id
from app.scheduler.infrastructure.snapshot import (
    SnapshotBundle,
    SnapshotConfigurationError,
    load_snapshot,
    load_version_lessons,
    split_version_history,
)


class ProposalConflict(Exception):
    """The proposal cannot be approved as requested; the state stays audited."""

    def __init__(self, code: str, message: str, *, context: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.context = context or {}


@dataclass(frozen=True)
class PersistOutcome:
    proposal_id: int | None
    refused: str | None = None


@dataclass(frozen=True)
class ApprovalResult:
    proposal_id: int
    active_version_id: int
    approved_at: datetime


@dataclass(frozen=True)
class RejectionResult:
    proposal_id: int
    rejected_at: datetime


async def _reject_pending_grid_version(
    db: AsyncSession,
    organization_id: int,
    job: SchedulerJobV1 | None,
) -> None:
    """Reject the pending grid version pinned by a failed or rejected job."""
    if job is None or job.grid_version_id is None:
        return
    version = await db.scalar(
        select(models.GridVersion)
        .where(
            models.GridVersion.organization_id == organization_id,
            models.GridVersion.id == job.grid_version_id,
        )
        .with_for_update()
    )
    if version is not None and version.state == models.GridVersionState.PENDING:
        version.state = models.GridVersionState.REJECTED
        await db.flush()


async def _mark_stale(
    db: AsyncSession,
    organization_id: int,
    proposal: SchedulerProposalV1,
    *,
    reason: str,
    now_utc: datetime,
    job: SchedulerJobV1 | None = None,
) -> None:
    proposal.status = "STALE"
    proposal.reason = reason
    proposal.decided_at = now_utc
    await _reject_pending_grid_version(db, organization_id, job)


async def _fresh_proposal_snapshot(db, organization_id, job, state, bundle, candidate, now_utc):
    # Revalidate the candidate with the current clock under the state lock. A
    # midnight crossing, a new execution or a new version invalidates the
    # proposal; the renewal clock must not move in that case.
    try:
        fresh = await load_snapshot(
            db,
            organization_id,
            strategy=SchedulingStrategy(job.strategy),
            now_utc=now_utc,
            school_year_id=job.school_year_id,
            grid_version_id=job.grid_version_id,
        )
    except SnapshotConfigurationError:
        fresh = None
    if (
        fresh is None
        or fresh.digest != job.snapshot_digest
        or fresh.base_version_id != job.base_version_id
        or fresh.input_revision != job.input_revision_used
        or fresh.planning_revision != job.planning_revision_used
        or state.input_revision != job.input_revision_used
        or state.planning_revision != job.planning_revision_used
    ):
        job.status = "STALE"
        job.result_code = "STALE"
        job.stop_reason = "INPUT_CHANGED"
        job.finished_at = now_utc
        await _reject_pending_grid_version(db, organization_id, job)
        await db.commit()
        return PersistOutcome(None, "STALE")
    # Revalidate against the generation clock, not the persist clock. A long
    # job can cross a grid period boundary; the current clock would then protect
    # a lesson that was future when the candidate was built. Data freshness is
    # already enforced by the digest and revision comparison above, and a change
    # of school day still invalidates the proposal.
    generation_now = bundle.snapshot.now_utc
    zone = ZoneInfo(fresh.snapshot.timezone_name)
    if fresh.snapshot.now_utc.astimezone(zone).date() != generation_now.astimezone(zone).date():
        job.status = "STALE"
        job.result_code = "STALE"
        job.stop_reason = "INPUT_CHANGED"
        job.finished_at = now_utc
        await _reject_pending_grid_version(db, organization_id, job)
        await db.commit()
        return PersistOutcome(None, "STALE")
    report = validate_candidate(replace(fresh.snapshot, now_utc=generation_now), candidate)
    if not report.valid:
        job.status = "STALE"
        job.result_code = "STALE"
        job.stop_reason = "REVALIDATION_FAILED"
        job.finished_at = now_utc
        await _reject_pending_grid_version(db, organization_id, job)
        await db.commit()
        return PersistOutcome(None, "STALE")
    return fresh


async def persist_proposal(
    db: AsyncSession,
    *,
    organization_id: int,
    job_id: int,
    attempt_token: int,
    bundle: SnapshotBundle,
    candidate: CandidateSchedule,
    payload: ProposalPayload,
    policy_version: str,
    now_utc: datetime,
) -> PersistOutcome:
    """Store the validated proposal and reset the renewal clock atomically."""
    job_reference = await db.scalar(
        select(SchedulerJobV1).where(
            SchedulerJobV1.id == job_id,
            SchedulerJobV1.organization_id == organization_id,
        )
    )
    if job_reference is None:
        return PersistOutcome(None, "LOST")
    state = await db.scalar(
        select(models.SchedulerSchoolYearState)
        .where(
            models.SchedulerSchoolYearState.organization_id == organization_id,
            models.SchedulerSchoolYearState.school_year_id == job_reference.school_year_id,
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
        state is None
        or job is None
        or job.attempt_token != attempt_token
        or job.status not in ("RUNNING", "VALIDATING")
    ):
        return PersistOutcome(None, "LOST")
    if job.cancellation_requested_at is not None:
        job.status = "CANCELLED"
        job.result_code = "CANCELLED"
        job.stop_reason = "CANCELLED"
        job.finished_at = now_utc
        await _reject_pending_grid_version(db, organization_id, job)
        await db.commit()
        return PersistOutcome(None, "CANCELLED")
    fresh = await _fresh_proposal_snapshot(
        db, organization_id, job, state, bundle, candidate, now_utc
    )
    if isinstance(fresh, PersistOutcome):
        return fresh
    bundle = fresh
    version = SchedulerVersionV1(
        organization_id=organization_id,
        school_year_id=state.school_year_id,
        origin=f"job:{job_id}",
        status="CANDIDATE",
        snapshot_digest=bundle.digest,
        previous_version_id=job.base_version_id,
        created_at=now_utc,
    )
    db.add(version)
    await db.flush()
    unit_key_by_id = {unit_id: key for key, unit_id in bundle.unit_keys.items()}
    accounting_by_unit_class = {
        (unit_id, bundle.accounting_classes[payer]): payer
        for unit_id, payers in bundle.unit_accounting.items()
        for payer in payers
        if payer in bundle.accounting_classes
    }
    # One persisted row per accounting (per-class) assignment. A joint unit
    # writes one sister per member class, all sharing the stable key, the unit
    # key, the physical interval and the slices (WBS 3.8.1). No synthetic unit
    # id is ever written as an assignment foreign key.
    lesson_rows: dict[tuple[int, int | None], int] = {}
    for lesson in candidate.lessons:
        accounting_ids = bundle.unit_accounting.get(lesson.assignment_id) or (lesson.assignment_id,)
        unit_key = unit_key_by_id.get(lesson.assignment_id)
        if unit_key is None:
            raise ValueError("A candidate lesson lost its teaching-unit key during persistence.")
        source_identity = (
            lesson.source_lesson_id if lesson.source_lesson_id is not None else lesson.lesson_id
        )
        for accounting_id in accounting_ids:
            class_id = bundle.accounting_classes.get(accounting_id)
            row = SchedulerLessonV1(
                organization_id=organization_id,
                school_year_id=state.school_year_id,
                version_id=version.id,
                assignment_id=accounting_id,
                stable_key=str(lesson.lesson_id),
                school_date=lesson.period.school_date,
                starts_at=lesson.period.start_utc,
                ends_at=lesson.period.end_utc,
                room_id=lesson.room_id,
                physical_minutes=lesson.period.duration_minutes,
                credit_minutes=lesson.credit_minutes,
                source_lesson_id=bundle.base_lesson_classes.get(source_identity, {}).get(class_id),
                teaching_unit_key=unit_key,
            )
            db.add(row)
            await db.flush()
            lesson_rows[(lesson.lesson_id, class_id)] = row.id
    for lesson in candidate.lessons:
        for (identity, _class_id), row_id in lesson_rows.items():
            if identity != lesson.lesson_id:
                continue
            for slice_ in lesson.slices:
                db.add(
                    SchedulerLessonSliceV1(
                        organization_id=organization_id,
                        school_year_id=state.school_year_id,
                        lesson_id=row_id,
                        module_id=slice_.module_id,
                        offset_minutes=slice_.offset_minutes,
                        minutes=slice_.credit_minutes,
                    )
                )
    await _carry_consumed_lessons(
        db,
        organization_id=organization_id,
        school_year_id=state.school_year_id,
        previous_version_id=job.base_version_id,
        new_version_id=version.id,
        candidate_identities={identity for identity, _class_id in lesson_rows},
        bundle=bundle,
        zone=ZoneInfo(bundle.snapshot.timezone_name),
        lesson_rows=lesson_rows,
        now_utc=now_utc,
    )
    claim_ids = sorted(bundle.snapshot.open_debt_minutes)
    claim_order: list[int] = []
    if claim_ids:
        claim_order = list(
            (
                await db.scalars(
                    select(CurricularDebt.id)
                    .where(
                        CurricularDebt.organization_id == organization_id,
                        CurricularDebt.id.in_(claim_ids),
                    )
                    .order_by(CurricularDebt.origin_date, CurricularDebt.id)
                )
            ).all()
        )
    candidate_by_lesson = {lesson.lesson_id: lesson for lesson in candidate.lessons}
    for allocation in plan_recovery_allocations(
        bundle.snapshot, candidate, claim_order=claim_order
    ):
        candidate_lesson = candidate_by_lesson.get(allocation.lesson_id)
        if candidate_lesson is None:
            raise ValueError("A recovery reservation lost its lesson during persistence.")
        unit_id = candidate_lesson.assignment_id
        claim_class = bundle.snapshot.claim_classes.get(allocation.claim_id)
        if claim_class is None:
            unit = next(
                (row for row in bundle.snapshot.assignments if row.assignment_id == unit_id),
                None,
            )
            if unit is not None and len(unit.class_ids) == 1:
                claim_class = unit.class_ids[0]
        if claim_class is None:
            raise ValueError("A joint recovery reservation needs its claim class.")
        lesson_db_id = lesson_rows.get((allocation.lesson_id, claim_class))
        accounting_id = accounting_by_unit_class.get((unit_id, claim_class))
        if lesson_db_id is None or accounting_id is None:
            raise ValueError("A recovery reservation lost its lesson during persistence.")
        db.add(
            SchedulerRecoveryReservationV1(
                organization_id=organization_id,
                school_year_id=state.school_year_id,
                version_id=version.id,
                assignment_id=accounting_id,
                lesson_id=lesson_db_id,
                debt_id=allocation.claim_id,
                minutes=allocation.minutes,
            )
        )
    pending = await db.scalar(
        select(SchedulerProposalV1)
        .where(
            SchedulerProposalV1.organization_id == organization_id,
            SchedulerProposalV1.school_year_id == state.school_year_id,
            SchedulerProposalV1.status == "PENDING",
        )
        .with_for_update()
    )
    if pending is not None:
        pending.status = "SUPERSEDED"
        pending.decided_at = now_utc
    storage_metrics = dict(payload.metrics)
    storage_metrics["policy_version"] = policy_version
    proposal = SchedulerProposalV1(
        organization_id=organization_id,
        school_year_id=state.school_year_id,
        job_id=job_id,
        version_id=version.id,
        base_version_id=job.base_version_id,
        status="PENDING",
        snapshot_digest=bundle.digest,
        policy_version=policy_version,
        input_revision_used=job.input_revision_used or 0,
        planning_revision_used=job.planning_revision_used or 0,
        metrics_json=storage_metrics,
        diff_json=dict(payload.diff),
        created_at=now_utc,
    )
    db.add(proposal)
    state.last_completed_planning_revision = job.planning_revision_used
    state.last_successful_generation_at = now_utc
    stop_reason = payload.metrics.get("stop_reason")
    job.status = "SUCCEEDED"
    job.result_code = "COMPLETE"
    job.stop_reason = stop_reason if isinstance(stop_reason, str) else None
    job.finished_at = now_utc
    await db.flush()
    proposal_id = proposal.id
    await db.commit()
    return PersistOutcome(proposal_id, None)


async def _previous_approval(db, organization_id, proposal, state, now_utc):
    if proposal.status == "APPROVED":
        approved_version = await db.scalar(
            select(SchedulerVersionV1).where(
                SchedulerVersionV1.id == proposal.version_id,
                SchedulerVersionV1.organization_id == organization_id,
                SchedulerVersionV1.school_year_id == proposal.school_year_id,
            )
        )
        if (
            approved_version is not None
            and approved_version.status == "ACTIVE"
            and state.active_schedule_version_id == str(approved_version.id)
        ):
            # A repeated approval command returns the original activation.
            result = ApprovalResult(
                proposal_id=proposal.id,
                active_version_id=approved_version.id,
                approved_at=proposal.decided_at or now_utc,
            )
            await db.commit()
            return result
        raise ProposalConflict(
            "proposal_superseded",
            "Esta proposta foi substituída por uma versão mais recente.",
            context={"proposal_status": proposal.status},
        )
    return None


async def _validate_pending_grid(db, organization_id, job, proposal, now_utc):
    if job.grid_version_id is not None:
        grid_version = await db.scalar(
            select(models.GridVersion)
            .where(
                models.GridVersion.organization_id == organization_id,
                models.GridVersion.id == job.grid_version_id,
            )
            .with_for_update()
        )
        if grid_version is None or grid_version.state != models.GridVersionState.PENDING:
            await _mark_stale(
                db,
                organization_id,
                proposal,
                reason="GRID_VERSION_CHANGED",
                now_utc=now_utc,
                job=job,
            )
            await db.commit()
            raise ProposalConflict(
                "proposal_stale",
                "A grelha proposta foi alterada entretanto. Gere uma nova proposta.",
                context={"proposal_status": "STALE"},
            )


def _unit_context(bundle: SnapshotBundle) -> dict:
    """Unit-key/class/accounting maps that collapse published sister rows."""
    return {
        "unit_keys": bundle.unit_keys,
        "class_ids_by_unit": {
            row.assignment_id: row.class_ids for row in bundle.snapshot.assignments
        },
        "accounting_classes": bundle.accounting_classes,
    }


async def _validate_approval_candidate(
    db, organization_id, proposal, job, version, now_utc, current_active
):
    try:
        bundle = await load_snapshot(
            db,
            organization_id,
            strategy=SchedulingStrategy(job.strategy),
            now_utc=now_utc,
            school_year_id=proposal.school_year_id,
            grid_version_id=job.grid_version_id,
        )
    except SnapshotConfigurationError as exc:
        await _mark_stale(db, organization_id, proposal, reason=exc.code, now_utc=now_utc, job=job)
        await db.commit()
        raise ProposalConflict(
            "proposal_stale",
            "As condições do horário mudaram. Gere uma nova proposta.",
            context={"proposal_status": "STALE", "configuration_code": exc.code},
        ) from exc
    context = _unit_context(bundle)
    version_lessons = await load_version_lessons(
        db,
        organization_id,
        proposal.school_year_id,
        version,
        ZoneInfo(bundle.snapshot.timezone_name),
        **context,
    )
    try:
        consumed, plannable = await split_version_history(
            db,
            organization_id,
            proposal.school_year_id,
            version,
            version_lessons.lessons,
            {row.assignment_id: row for row in bundle.snapshot.assignments},
            bundle.snapshot.executed_minutes,
            now_utc=now_utc,
        )
    except ValueError as exc:
        await _mark_stale(
            db, organization_id, proposal, reason="VALIDATION_FAILED", now_utc=now_utc, job=job
        )
        await db.commit()
        raise ProposalConflict(
            "proposal_stale",
            "A proposta já não cumpre as condições atuais. Gere uma nova proposta.",
            context={"proposal_status": "STALE"},
        ) from exc
    await _check_consumed_history(
        db,
        organization_id,
        proposal.school_year_id,
        previous_version_id=current_active,
        consumed=consumed,
        zone=ZoneInfo(bundle.snapshot.timezone_name),
        **context,
    )
    report = validate_candidate(bundle.snapshot, CandidateSchedule(plannable))
    if not report.valid:
        await _mark_stale(
            db, organization_id, proposal, reason="VALIDATION_FAILED", now_utc=now_utc, job=job
        )
        await db.commit()
        raise ProposalConflict(
            "proposal_stale",
            "A proposta já não cumpre as condições atuais. Gere uma nova proposta.",
            context={
                "proposal_status": "STALE",
                "violations": [violation.code.value for violation in report.violations[:5]],
            },
        )
    return bundle


async def approve_proposal(
    db: AsyncSession,
    *,
    organization_id: int,
    proposal_id: int,
    decided_by_membership_id: int | None,
    now_utc: datetime,
    expected_input_revision: int | None = None,
) -> ApprovalResult:
    """Revalidate and activate one pending proposal in a single transaction."""
    proposal = await db.scalar(
        select(SchedulerProposalV1).where(
            SchedulerProposalV1.id == proposal_id,
            SchedulerProposalV1.organization_id == organization_id,
        )
    )
    if proposal is None:
        raise LookupError("Scheduler proposal was not found.")
    state = await db.scalar(
        select(models.SchedulerSchoolYearState)
        .where(
            models.SchedulerSchoolYearState.organization_id == organization_id,
            models.SchedulerSchoolYearState.school_year_id == proposal.school_year_id,
        )
        .with_for_update()
    )
    proposal = await db.scalar(
        select(SchedulerProposalV1)
        .where(
            SchedulerProposalV1.id == proposal_id,
            SchedulerProposalV1.organization_id == organization_id,
        )
        .with_for_update()
    )
    if state is None:
        raise LookupError("Scheduler school-year state was not found.")
    job = await db.scalar(
        select(SchedulerJobV1).where(
            SchedulerJobV1.id == proposal.job_id,
            SchedulerJobV1.organization_id == organization_id,
        )
    )
    if job is None:
        raise LookupError("Scheduler job was not found.")
    previous_approval = await _previous_approval(db, organization_id, proposal, state, now_utc)
    if previous_approval is not None:
        return previous_approval
    if proposal.status != "PENDING":
        raise ProposalConflict(
            "proposal_not_pending",
            "Esta proposta já não está pendente.",
            context={"proposal_status": proposal.status},
        )
    if expected_input_revision is not None and expected_input_revision != state.input_revision:
        raise ProposalConflict(
            "scheduler_state_changed",
            "O horário foi alterado entretanto. Atualize a página e volte a tentar.",
            context={"input_revision": state.input_revision},
        )
    if (
        state.input_revision != proposal.input_revision_used
        or state.planning_revision != proposal.planning_revision_used
    ):
        await _mark_stale(
            db, organization_id, proposal, reason="REVISIONS_CHANGED", now_utc=now_utc, job=job
        )
        await db.commit()
        raise ProposalConflict(
            "proposal_stale",
            "Existem alterações mais recentes. Gere uma nova proposta.",
            context={"proposal_status": "STALE"},
        )
    current_active = await load_active_version_id(db, organization_id, proposal.school_year_id)
    if current_active != proposal.base_version_id:
        await _mark_stale(
            db, organization_id, proposal, reason="BASE_VERSION_CHANGED", now_utc=now_utc, job=job
        )
        await db.commit()
        raise ProposalConflict(
            "proposal_stale",
            "O horário publicado foi alterado entretanto. Gere uma nova proposta.",
            context={"proposal_status": "STALE"},
        )
    version = await db.scalar(
        select(SchedulerVersionV1).where(
            SchedulerVersionV1.id == proposal.version_id,
            SchedulerVersionV1.organization_id == organization_id,
            SchedulerVersionV1.school_year_id == proposal.school_year_id,
        )
    )
    if version is None:
        raise LookupError("Scheduler version was not found.")
    await _validate_pending_grid(db, organization_id, job, proposal, now_utc)
    await _validate_approval_candidate(
        db, organization_id, proposal, job, version, now_utc, current_active
    )
    await _repoint_lesson_logs(
        db,
        organization_id,
        proposal.school_year_id,
        previous_version_id=current_active,
        new_version_id=version.id,
    )
    if current_active is not None:
        active = await db.scalar(
            select(SchedulerVersionV1)
            .where(
                SchedulerVersionV1.id == current_active,
                SchedulerVersionV1.organization_id == organization_id,
            )
            .with_for_update()
        )
        if active is not None:
            active.status = "SUPERSEDED"
    version.status = "ACTIVE"
    version.approved_at = now_utc
    if job.grid_version_id is not None:
        # The pinned version was locked and verified as PENDING above: the
        # schedule and its grid are published in the same transaction.
        grid_version = await db.scalar(
            select(models.GridVersion).where(
                models.GridVersion.organization_id == organization_id,
                models.GridVersion.id == job.grid_version_id,
            )
        )
        if grid_version is None:
            raise LookupError("Scheduler grid version was not found.")
        grid_version.state = models.GridVersionState.ACTIVE
    state.active_schedule_version_id = str(version.id)
    state.school_year_publication_state = models.SchoolYearPublicationState.PUBLISHED
    state.lock_version += 1
    proposal.status = "APPROVED"
    proposal.decided_at = now_utc
    proposal.decided_by_membership_id = decided_by_membership_id
    organization = await db.scalar(
        select(models.Organization).where(models.Organization.id == organization_id)
    )
    if (
        organization is not None
        and organization.first_real_schedule_approved_at is None
        and organization.foundation_status == models.OrganizationFoundationStatus.COMPLETED
    ):
        organization.first_real_schedule_approved_at = now_utc
    await db.flush()
    result = ApprovalResult(
        proposal_id=proposal.id,
        active_version_id=version.id,
        approved_at=now_utc,
    )
    await db.commit()
    return result


async def _carry_consumed_lessons(
    db: AsyncSession,
    *,
    organization_id: int,
    school_year_id: int,
    previous_version_id: int | None,
    new_version_id: int,
    candidate_identities: set[int],
    bundle: SnapshotBundle,
    zone: ZoneInfo,
    lesson_rows: dict[tuple[int, int | None], int],
    now_utc: datetime,
) -> None:
    """Copy executed and missed history under the stable identity.

    Logged history stays outside planned credit. Every row of a joint sister
    set is copied as its own row so the whole group keeps all its classes'
    occupancy, even when the classes logged different states.
    """
    if previous_version_id is None:
        return
    previous = await db.scalar(
        select(SchedulerVersionV1).where(
            SchedulerVersionV1.id == previous_version_id,
            SchedulerVersionV1.organization_id == organization_id,
            SchedulerVersionV1.school_year_id == school_year_id,
        )
    )
    if previous is None:
        return
    context = _unit_context(bundle)
    version_lessons = await load_version_lessons(
        db, organization_id, school_year_id, previous, zone, **context
    )
    consumed, _ = await split_version_history(
        db,
        organization_id,
        school_year_id,
        previous,
        version_lessons.lessons,
        {row.assignment_id: row for row in bundle.snapshot.assignments},
        bundle.snapshot.executed_minutes,
        now_utc=now_utc,
    )
    consumed_identities = {
        lesson.lesson_id for lesson in consumed if lesson.lesson_id not in candidate_identities
    }
    if not consumed_identities:
        return
    previous_rows = (
        await db.scalars(
            select(SchedulerLessonV1)
            .where(
                SchedulerLessonV1.organization_id == organization_id,
                SchedulerLessonV1.school_year_id == school_year_id,
                SchedulerLessonV1.version_id == previous_version_id,
            )
            .order_by(SchedulerLessonV1.id)
        )
    ).all()
    previous_ids = [row.id for row in previous_rows]
    slices_by_db_id: dict[int, list[SchedulerLessonSliceV1]] = defaultdict(list)
    if previous_ids:
        for slice_row in (
            await db.scalars(
                select(SchedulerLessonSliceV1)
                .where(
                    SchedulerLessonSliceV1.organization_id == organization_id,
                    SchedulerLessonSliceV1.school_year_id == school_year_id,
                    SchedulerLessonSliceV1.lesson_id.in_(previous_ids),
                )
                .order_by(SchedulerLessonSliceV1.id)
            )
        ).all():
            slices_by_db_id[slice_row.lesson_id].append(slice_row)
    for row in previous_rows:
        identity = version_lessons.identity_by_db_id.get(row.id)
        if identity is None or identity not in consumed_identities:
            continue
        new_row = SchedulerLessonV1(
            organization_id=organization_id,
            school_year_id=school_year_id,
            version_id=new_version_id,
            assignment_id=row.assignment_id,
            stable_key=row.stable_key,
            school_date=row.school_date,
            starts_at=row.starts_at,
            ends_at=row.ends_at,
            room_id=row.room_id,
            physical_minutes=row.physical_minutes,
            credit_minutes=row.credit_minutes,
            source_lesson_id=row.id,
            teaching_unit_key=row.teaching_unit_key,
        )
        db.add(new_row)
        await db.flush()
        lesson_rows[(identity, bundle.accounting_classes.get(row.assignment_id))] = new_row.id
        for slice_row in slices_by_db_id.get(row.id, ()):
            db.add(
                SchedulerLessonSliceV1(
                    organization_id=organization_id,
                    school_year_id=school_year_id,
                    lesson_id=new_row.id,
                    module_id=slice_row.module_id,
                    offset_minutes=slice_row.offset_minutes,
                    minutes=slice_row.minutes,
                )
            )


async def _check_consumed_history(
    db: AsyncSession,
    organization_id: int,
    school_year_id: int,
    *,
    previous_version_id: int | None,
    consumed,
    zone: ZoneInfo,
    unit_keys=None,
    class_ids_by_unit=None,
    accounting_classes=None,
) -> None:
    """Operational history must match the previous version exactly.

    A consumed lesson is frozen: same identity, period, room, credit and
    slices. Any divergence means the persisted history was rewritten.
    """
    if not consumed:
        return
    if previous_version_id is None:
        raise ProposalConflict(
            "proposal_history_mismatch",
            "A proposta contém histórico sem versão publicada anterior.",
            context={"proposal_status": "STALE"},
        )
    previous = await db.scalar(
        select(SchedulerVersionV1).where(
            SchedulerVersionV1.id == previous_version_id,
            SchedulerVersionV1.organization_id == organization_id,
            SchedulerVersionV1.school_year_id == school_year_id,
        )
    )
    if previous is None:
        raise ProposalConflict(
            "proposal_history_mismatch",
            "A versão publicada anterior desapareceu.",
            context={"proposal_status": "STALE"},
        )
    previous_lessons = (
        await load_version_lessons(
            db,
            organization_id,
            school_year_id,
            previous,
            zone,
            unit_keys=unit_keys,
            class_ids_by_unit=class_ids_by_unit,
            accounting_classes=accounting_classes,
        )
    ).lessons
    previous_by_identity = {lesson.lesson_id: lesson for lesson in previous_lessons}

    def _slices(lesson) -> tuple:
        return tuple(
            sorted((row.module_id, row.offset_minutes, row.credit_minutes) for row in lesson.slices)
        )

    for lesson in consumed:
        original = previous_by_identity.get(lesson.lesson_id)
        if (
            original is None
            or original.period.start_utc != lesson.period.start_utc
            or original.period.end_utc != lesson.period.end_utc
            or original.room_id != lesson.room_id
            or original.credit_minutes != lesson.credit_minutes
            or _slices(original) != _slices(lesson)
        ):
            raise ProposalConflict(
                "proposal_history_mismatch",
                "O histórico executado da proposta foi alterado.",
                context={"proposal_status": "STALE", "lesson_id": lesson.lesson_id},
            )


async def _repoint_lesson_logs(
    db: AsyncSession,
    organization_id: int,
    school_year_id: int,
    *,
    previous_version_id: int | None,
    new_version_id: int,
) -> int:
    """Move operational logs to the new version through the stable identity.

    A protected or executed lesson keeps its identity across versions, so its
    log, summary and credited execution follow it. Re-registering the lesson
    stays idempotent because the ledger origin uses the same identity.
    """
    if previous_version_id is None:
        return 0
    rows = (
        await db.execute(
            select(
                SchedulerLessonV1.id,
                SchedulerLessonV1.version_id,
                SchedulerLessonV1.stable_key,
                SchedulerLessonV1.assignment_id,
            ).where(
                SchedulerLessonV1.organization_id == organization_id,
                SchedulerLessonV1.school_year_id == school_year_id,
                SchedulerLessonV1.version_id.in_((previous_version_id, new_version_id)),
            )
        )
    ).all()
    previous: dict[tuple[str, int], int] = {}
    current: dict[tuple[str, int], int] = {}
    for lesson_id, version_id, stable_key, assignment_id in rows:
        if version_id == previous_version_id:
            previous.setdefault((stable_key, assignment_id), lesson_id)
        else:
            current[(stable_key, assignment_id)] = lesson_id
    moved = 0
    for key, new_id in current.items():
        old_id = previous.get(key)
        if old_id is None or old_id == new_id:
            continue
        # A withdrawn lesson (internship flow) never comes back, so its log stays on
        # the version that withdrew it instead of following the key to a new lesson.
        result = await db.execute(
            update(SchedulerLessonLogV1)
            .where(
                SchedulerLessonLogV1.organization_id == organization_id,
                SchedulerLessonLogV1.school_year_id == school_year_id,
                SchedulerLessonLogV1.lesson_id == old_id,
                SchedulerLessonLogV1.withdrawn_at.is_(None),
            )
            .values(lesson_id=new_id)
        )
        moved += result.rowcount or 0
    return moved


async def reject_proposal(
    db: AsyncSession,
    *,
    organization_id: int,
    proposal_id: int,
    decided_by_membership_id: int | None,
    reason: str | None,
    now_utc: datetime,
) -> RejectionResult:
    """Audited rejection; it does not unlock an arbitrary reroll."""
    proposal = await db.scalar(
        select(SchedulerProposalV1)
        .where(
            SchedulerProposalV1.id == proposal_id,
            SchedulerProposalV1.organization_id == organization_id,
        )
        .with_for_update()
    )
    if proposal is None:
        raise LookupError("Scheduler proposal was not found.")
    if proposal.status not in ("PENDING", "STALE"):
        raise ProposalConflict(
            "proposal_not_rejectable",
            "Esta proposta já não pode ser rejeitada.",
            context={"proposal_status": proposal.status},
        )
    proposal.status = "REJECTED"
    proposal.decided_at = now_utc
    proposal.decided_by_membership_id = decided_by_membership_id
    if reason:
        proposal.reason = reason
    job = await db.scalar(
        select(SchedulerJobV1).where(
            SchedulerJobV1.id == proposal.job_id,
            SchedulerJobV1.organization_id == organization_id,
        )
    )
    await _reject_pending_grid_version(db, organization_id, job)
    await db.flush()
    result = RejectionResult(proposal_id=proposal.id, rejected_at=now_utc)
    await db.commit()
    return result
