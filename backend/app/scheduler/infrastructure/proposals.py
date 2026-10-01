"""Atomic proposal persistence, approval and rejection for scheduler v1.

Finalization and approval own their transactions: either the whole version,
its lessons, slices, reservations and the clock commit together, or nothing
changes. Staleness is an audited decision: a proposal that no longer matches
the current data is marked STALE and never approved silently.
"""

from __future__ import annotations

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


async def _active_version_id(
    db: AsyncSession, organization_id: int, school_year_id: int
) -> int | None:
    return await db.scalar(
        select(SchedulerVersionV1.id).where(
            SchedulerVersionV1.organization_id == organization_id,
            SchedulerVersionV1.school_year_id == school_year_id,
            SchedulerVersionV1.status == "ACTIVE",
        )
    )


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
    # Revalidate the candidate with the current clock under the state lock. A
    # midnight crossing, a new execution or a new version invalidates the
    # proposal; the renewal clock must not move in that case.
    try:
        fresh = await load_snapshot(
            db,
            organization_id,
            strategy=SchedulingStrategy(job.strategy),
            now_utc=now_utc,
            school_year_id=job_reference.school_year_id,
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
    lesson_db_ids: dict[int, int] = {}
    lesson_assignments: dict[int, int] = {}
    for lesson in candidate.lessons:
        source_db_id = None
        if lesson.source_lesson_id is not None:
            source_db_id = bundle.base_lesson_ids.get(lesson.source_lesson_id)
        elif lesson.lesson_id in bundle.base_lesson_ids:
            source_db_id = bundle.base_lesson_ids[lesson.lesson_id]
        row = SchedulerLessonV1(
            organization_id=organization_id,
            school_year_id=state.school_year_id,
            version_id=version.id,
            assignment_id=lesson.assignment_id,
            stable_key=str(lesson.lesson_id),
            school_date=lesson.period.school_date,
            starts_at=lesson.period.start_utc,
            ends_at=lesson.period.end_utc,
            room_id=lesson.room_id,
            physical_minutes=lesson.period.duration_minutes,
            credit_minutes=lesson.credit_minutes,
            source_lesson_id=source_db_id,
        )
        db.add(row)
        await db.flush()
        lesson_db_ids[lesson.lesson_id] = row.id
        lesson_assignments[lesson.lesson_id] = lesson.assignment_id
    for lesson in candidate.lessons:
        for slice_ in lesson.slices:
            db.add(
                SchedulerLessonSliceV1(
                    organization_id=organization_id,
                    school_year_id=state.school_year_id,
                    lesson_id=lesson_db_ids[lesson.lesson_id],
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
        candidate_identities=set(lesson_db_ids),
        assignments={row.assignment_id: row for row in bundle.snapshot.assignments},
        executed=bundle.snapshot.executed_minutes,
        zone=ZoneInfo(bundle.snapshot.timezone_name),
        lesson_db_ids=lesson_db_ids,
        lesson_assignments=lesson_assignments,
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
    for allocation in plan_recovery_allocations(
        bundle.snapshot, candidate, claim_order=claim_order
    ):
        lesson_db_id = lesson_db_ids.get(allocation.lesson_id)
        if lesson_db_id is None:
            raise ValueError("A recovery reservation lost its lesson during persistence.")
        db.add(
            SchedulerRecoveryReservationV1(
                organization_id=organization_id,
                school_year_id=state.school_year_id,
                version_id=version.id,
                assignment_id=lesson_assignments[allocation.lesson_id],
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
    current_active = await _active_version_id(db, organization_id, proposal.school_year_id)
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
    lessons, _, _ = await load_version_lessons(
        db,
        organization_id,
        proposal.school_year_id,
        version,
        ZoneInfo(bundle.snapshot.timezone_name),
    )
    try:
        consumed, plannable = await split_version_history(
            db,
            organization_id,
            proposal.school_year_id,
            version,
            lessons,
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
    assignments,
    executed,
    zone: ZoneInfo,
    lesson_db_ids: dict[int, int],
    lesson_assignments: dict[int, int],
    now_utc: datetime,
) -> None:
    """Copy executed and missed history under the stable identity.

    Logged history stays outside planned credit. The new version retains its
    physical positions, original slices and operational logs.
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
    lessons, _, _ = await load_version_lessons(db, organization_id, school_year_id, previous, zone)
    consumed, _ = await split_version_history(
        db,
        organization_id,
        school_year_id,
        previous,
        lessons,
        assignments,
        executed,
        now_utc=now_utc,
    )
    old_db_ids = {
        row.stable_key: row.id
        for row in (
            await db.scalars(
                select(SchedulerLessonV1).where(
                    SchedulerLessonV1.organization_id == organization_id,
                    SchedulerLessonV1.school_year_id == school_year_id,
                    SchedulerLessonV1.version_id == previous_version_id,
                )
            )
        ).all()
    }
    for lesson in consumed:
        if lesson.lesson_id in candidate_identities:
            continue
        row = SchedulerLessonV1(
            organization_id=organization_id,
            school_year_id=school_year_id,
            version_id=new_version_id,
            assignment_id=lesson.assignment_id,
            stable_key=str(lesson.lesson_id),
            school_date=lesson.period.school_date,
            starts_at=lesson.period.start_utc,
            ends_at=lesson.period.end_utc,
            room_id=lesson.room_id,
            physical_minutes=lesson.period.duration_minutes,
            credit_minutes=lesson.credit_minutes,
            source_lesson_id=old_db_ids.get(str(lesson.lesson_id)),
        )
        db.add(row)
        await db.flush()
        lesson_db_ids[lesson.lesson_id] = row.id
        lesson_assignments[lesson.lesson_id] = lesson.assignment_id
        for slice_ in lesson.slices:
            db.add(
                SchedulerLessonSliceV1(
                    organization_id=organization_id,
                    school_year_id=school_year_id,
                    lesson_id=row.id,
                    module_id=slice_.module_id,
                    offset_minutes=slice_.offset_minutes,
                    minutes=slice_.credit_minutes,
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
    previous_lessons, _, _ = await load_version_lessons(
        db, organization_id, school_year_id, previous, zone
    )
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
            ).where(
                SchedulerLessonV1.organization_id == organization_id,
                SchedulerLessonV1.school_year_id == school_year_id,
                SchedulerLessonV1.version_id.in_((previous_version_id, new_version_id)),
            )
        )
    ).all()
    previous: dict[str, int] = {}
    current: dict[str, int] = {}
    for lesson_id, version_id, stable_key in rows:
        if version_id == previous_version_id:
            previous[stable_key] = lesson_id
        else:
            current[stable_key] = lesson_id
    moved = 0
    for stable_key, new_id in current.items():
        old_id = previous.get(stable_key)
        if old_id is None or old_id == new_id:
            continue
        result = await db.execute(
            update(SchedulerLessonLogV1)
            .where(
                SchedulerLessonLogV1.organization_id == organization_id,
                SchedulerLessonLogV1.school_year_id == school_year_id,
                SchedulerLessonLogV1.lesson_id == old_id,
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
