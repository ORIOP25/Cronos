"""W08 lifecycle: queue, claims, staleness, proposal clock and approval."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app import models
from app.scheduler.infrastructure.jobs import (
    AttemptState,
    GenerationUnavailable,
    claim_next_job,
    enqueue_generation,
    executor_lock_alive,
    finish_job,
    heartbeat_and_poll,
    reconcile_abandoned,
    release_executor_lock,
    request_cancellation,
    try_acquire_executor_lock,
)
from app.scheduler.infrastructure.models import (
    SchedulerJobV1,
    SchedulerLessonV1,
    SchedulerProposalV1,
    SchedulerVersionV1,
)
from app.scheduler.infrastructure.proposals import (
    ProposalConflict,
    approve_proposal,
    reject_proposal,
)
from app.scheduler.infrastructure.queries import current_proposal, scheduler_status
from app.services.dashboard_service import get_dashboard_summary
from app.services.scheduler_state_service import SchedulerStateService
from tests._support.db_fixtures import TestingSessionLocal, test_engine
from tests._support.scheduler_v1 import V1Seed, seed_generatable_school

pytestmark = pytest.mark.postgresql

MOMENT = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)


async def _minimal_school(
    db_session,
    *,
    clerk_user_id: str = "w08_admin",
    clerk_org_id: str = "w08_org",
    module_minutes: int = 100,
) -> V1Seed:
    return await seed_generatable_school(
        db_session,
        clerk_user_id=clerk_user_id,
        clerk_org_id=clerk_org_id,
        module_minutes=module_minutes,
    )


async def _enqueue(db_session, seed: V1Seed, key: str = "first-generation", **kwargs):
    return await enqueue_generation(
        db_session,
        seed.organization.id,
        idempotency_key=key,
        requested_by_membership_id=seed.membership.id,
        now_utc=MOMENT,
        **kwargs,
    )


async def _run_worker(monkeypatch, db_session):
    from app import scheduler_v1_worker as worker

    monkeypatch.setattr(worker, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(worker, "engine_async", test_engine)
    monkeypatch.setattr(worker, "_now", lambda: MOMENT)
    monkeypatch.setattr(worker, "RECOVERY_ASSESSMENT_SECONDS", 0.0)
    return await worker.process_next_jobs()


async def test_enqueue_is_idempotent(db_session):
    seed = await _minimal_school(db_session)
    await db_session.commit()

    first = await _enqueue(db_session, seed)
    await db_session.commit()
    assert first.created is True
    assert first.queue_position == 1
    assert first.job.status == "QUEUED"

    replay = await _enqueue(db_session, seed)
    await db_session.commit()
    assert replay.created is False
    assert replay.job.id == first.job.id


async def test_enqueue_requires_a_reason_after_a_success(db_session, monkeypatch):
    seed = await _minimal_school(db_session)
    await db_session.commit()
    await _enqueue(db_session, seed)
    await db_session.commit()
    await _run_worker(monkeypatch, db_session)
    await db_session.refresh(seed.state)

    with pytest.raises(GenerationUnavailable) as conflict:
        await _enqueue(db_session, seed, key="no-reason")
    assert conflict.value.code == "no_generation_reason"


async def test_a_change_while_queued_marks_the_request_stale(db_session):
    seed = await _minimal_school(db_session)
    await db_session.commit()
    queued = await _enqueue(db_session, seed)
    await db_session.commit()

    state = await SchedulerStateService(db_session).get_state(seed.organization.id, seed.year.id)
    state.input_revision += 1
    await db_session.commit()

    claim = await claim_next_job(db_session, now_utc=MOMENT)
    assert claim is None
    refreshed = await db_session.get(SchedulerJobV1, queued.job.id)
    await db_session.refresh(refreshed)
    assert refreshed.status == "STALE"
    assert refreshed.result_code == "STALE"
    assert refreshed.finished_at is not None


async def test_fifo_claim_is_single_and_global(db_session):
    first = await _minimal_school(db_session, clerk_user_id="w08_a", clerk_org_id="w08_org_a")
    second = await _minimal_school(
        db_session, clerk_user_id="w08_b", clerk_org_id="w08_org_b", module_minutes=50
    )
    await db_session.commit()
    job_a = await _enqueue(db_session, first, key="org-a")
    job_b = await _enqueue(db_session, second, key="org-b")
    await db_session.commit()
    assert job_a.job.queued_at <= job_b.job.queued_at

    claim = await claim_next_job(db_session, now_utc=MOMENT)
    assert claim is not None
    assert claim.job_id == job_a.job.id
    assert claim.organization_id == first.organization.id

    while_busy = await claim_next_job(db_session, now_utc=MOMENT)
    assert while_busy is None

    finished = await finish_job(
        db_session,
        organization_id=claim.organization_id,
        job_id=claim.job_id,
        attempt_token=claim.attempt_token,
        status="FAILED",
        result_code="FAILED",
        now_utc=MOMENT,
    )
    assert finished == "FAILED"
    await db_session.commit()

    next_claim = await claim_next_job(db_session, now_utc=MOMENT)
    assert next_claim is not None
    assert next_claim.job_id == job_b.job.id


async def test_stale_attempt_token_cannot_write(db_session):
    seed = await _minimal_school(db_session)
    await db_session.commit()
    await _enqueue(db_session, seed)
    await db_session.commit()
    claim = await claim_next_job(db_session, now_utc=MOMENT)
    assert claim is not None

    refused = await finish_job(
        db_session,
        organization_id=claim.organization_id,
        job_id=claim.job_id,
        attempt_token=claim.attempt_token + 7,
        status="SUCCEEDED",
        result_code="COMPLETE",
        now_utc=MOMENT,
    )
    assert refused == "LOST"


async def test_finish_prefers_cancellation_and_staleness_over_the_result(db_session):
    seed = await _minimal_school(db_session)
    await db_session.commit()
    queued = await _enqueue(db_session, seed)
    await db_session.commit()
    claim = await claim_next_job(db_session, now_utc=MOMENT)
    assert claim is not None

    await request_cancellation(db_session, seed.organization.id, queued.job.id, now_utc=MOMENT)
    written = await finish_job(
        db_session,
        organization_id=seed.organization.id,
        job_id=queued.job.id,
        attempt_token=claim.attempt_token,
        status="INFEASIBLE",
        result_code="INFEASIBLE",
        stop_reason="INFEASIBLE",
        now_utc=MOMENT,
    )
    await db_session.commit()
    assert written == "CANCELLED"
    cancelled_job = await db_session.get(SchedulerJobV1, queued.job.id)
    await db_session.refresh(cancelled_job)
    assert cancelled_job.result_code == "CANCELLED"

    retry = await _enqueue(db_session, seed, key="after-cancel-result")
    await db_session.commit()
    retry_claim = await claim_next_job(db_session, now_utc=MOMENT)
    assert retry_claim is not None
    state = await SchedulerStateService(db_session).get_state(seed.organization.id, seed.year.id)
    await db_session.refresh(state)
    state.input_revision += 1
    await db_session.commit()
    written = await finish_job(
        db_session,
        organization_id=seed.organization.id,
        job_id=retry.job.id,
        attempt_token=retry_claim.attempt_token,
        status="FAILED",
        result_code="FAILED",
        stop_reason="FAILED",
        now_utc=MOMENT,
    )
    await db_session.commit()
    assert written == "STALE"
    stale_job = await db_session.get(SchedulerJobV1, retry.job.id)
    await db_session.refresh(stale_job)
    assert stale_job.result_code == "STALE"


async def test_abandoned_attempt_is_failed_and_retried(db_session):
    seed = await _minimal_school(db_session)
    await db_session.commit()
    queued = await _enqueue(db_session, seed)
    await db_session.commit()
    claim = await claim_next_job(db_session, now_utc=MOMENT)
    assert claim is not None

    job = await db_session.get(SchedulerJobV1, queued.job.id)
    job.heartbeat_at = MOMENT - timedelta(hours=1)
    await db_session.commit()

    reconciled = await reconcile_abandoned(db_session, stale_after_seconds=60, now_utc=MOMENT)
    assert reconciled == 1
    await db_session.refresh(job)
    assert job.status == "FAILED"
    assert job.result_code == "WORKER_STALLED"

    retry = await _enqueue(db_session, seed, key="retry-after-stall")
    await db_session.commit()
    assert retry.created is True
    assert retry.job.id != queued.job.id


async def test_cancellation_is_idempotent_in_each_phase(db_session):
    seed = await _minimal_school(db_session)
    await db_session.commit()
    queued = await _enqueue(db_session, seed)
    await db_session.commit()

    cancelled = await request_cancellation(
        db_session, seed.organization.id, queued.job.id, now_utc=MOMENT
    )
    await db_session.commit()
    assert cancelled.status == "CANCELLED"
    assert await claim_next_job(db_session, now_utc=MOMENT) is None

    retry = await _enqueue(db_session, seed, key="retry-after-cancel")
    await db_session.commit()
    claim = await claim_next_job(db_session, now_utc=MOMENT)
    assert claim is not None
    await request_cancellation(db_session, seed.organization.id, retry.job.id, now_utc=MOMENT)
    await db_session.commit()
    attempt = await heartbeat_and_poll(
        db_session,
        organization_id=seed.organization.id,
        job_id=retry.job.id,
        attempt_token=claim.attempt_token,
        now_utc=MOMENT,
    )
    await db_session.commit()
    assert attempt is AttemptState.CANCEL


async def test_successful_generation_persists_a_proposal_and_restarts_the_clock(
    db_session, monkeypatch
):
    seed = await _minimal_school(db_session)
    await db_session.commit()
    await _enqueue(db_session, seed)
    await db_session.commit()

    result = await _run_worker(monkeypatch, db_session)
    assert result["status"] == "ok"
    processed = result["processed"]
    assert processed and processed[0]["status"] == "SUCCEEDED"

    proposal = await db_session.scalar(
        select(SchedulerProposalV1).where(
            SchedulerProposalV1.organization_id == seed.organization.id
        )
    )
    assert proposal is not None
    assert proposal.status == "PENDING"
    assert proposal.metrics_json is not None
    assert proposal.metrics_json["policy_version"] == "baseline-v1"
    assert isinstance(proposal.metrics_json.get("evidence"), dict)
    assert isinstance(proposal.metrics_json["evidence"].get("stages"), list)
    assert proposal.diff_json["is_first_generation"] is True
    assert proposal.diff_json["counts"]["added"] >= 1

    lessons = (
        await db_session.scalars(
            select(SchedulerLessonV1).where(
                SchedulerLessonV1.organization_id == seed.organization.id
            )
        )
    ).all()
    assert lessons
    assert sum(lesson.credit_minutes for lesson in lessons) == 100

    state = await SchedulerStateService(db_session).get_state(seed.organization.id, seed.year.id)
    await db_session.refresh(state)
    assert state.last_completed_planning_revision == state.planning_revision
    assert state.last_successful_generation_at is not None

    status = await scheduler_status(db_session, seed.organization.id, now_utc=MOMENT)
    assert status["pending_proposal"]["proposal_id"] == proposal.id
    assert status["pending_proposal"]["can_approve"] is True
    quality = status["pending_proposal"]["quality_summary"]
    assert quality["policy_version"] == "baseline-v1"
    assert quality["total_stages"] >= 1
    assert quality["certified_stages"] <= quality["total_stages"]
    assert isinstance(quality["claims_optimum"], bool)
    assert status["active_job"] is None


async def test_approval_revalidates_and_activates_the_version(db_session, monkeypatch):
    seed = await _minimal_school(db_session)
    await db_session.commit()
    await _enqueue(db_session, seed)
    await db_session.commit()
    await _run_worker(monkeypatch, db_session)
    proposal = await current_proposal(db_session, seed.organization.id, now_utc=MOMENT)
    assert proposal is not None

    conflict_state = await SchedulerStateService(db_session).get_state(
        seed.organization.id, seed.year.id
    )
    conflict_state.input_revision += 1
    conflict_state.planning_revision += 1
    await db_session.commit()
    with pytest.raises(ProposalConflict) as stale:
        await approve_proposal(
            db_session,
            organization_id=seed.organization.id,
            proposal_id=proposal["proposal_id"],
            decided_by_membership_id=seed.membership.id,
            now_utc=MOMENT,
        )
    assert stale.value.code == "proposal_stale"
    refreshed = await db_session.get(SchedulerProposalV1, proposal["proposal_id"])
    await db_session.refresh(refreshed)
    assert refreshed.status == "STALE"

    await _enqueue(db_session, seed, key="after-change")
    await db_session.commit()
    await _run_worker(monkeypatch, db_session)
    fresh = await current_proposal(db_session, seed.organization.id, now_utc=MOMENT)
    assert fresh is not None
    result = await approve_proposal(
        db_session,
        organization_id=seed.organization.id,
        proposal_id=fresh["proposal_id"],
        decided_by_membership_id=seed.membership.id,
        now_utc=MOMENT,
    )
    state = await SchedulerStateService(db_session).get_state(seed.organization.id, seed.year.id)
    await db_session.refresh(state)
    assert state.school_year_publication_state == models.SchoolYearPublicationState.PUBLISHED
    assert state.active_schedule_version_id == str(result.active_version_id)
    version = await db_session.get(SchedulerVersionV1, result.active_version_id)
    assert version.status == "ACTIVE"
    assert version.approved_at is not None

    status = await scheduler_status(db_session, seed.organization.id, now_utc=MOMENT)
    assert status["default_strategy"] == "ADAPTIVE_RECOVERY"
    assert status["active_version_id"] == result.active_version_id


async def test_repeated_approval_returns_the_same_activation(db_session, monkeypatch):
    seed = await _minimal_school(db_session)
    await db_session.commit()
    await _enqueue(db_session, seed)
    await db_session.commit()
    await _run_worker(monkeypatch, db_session)
    proposal = await current_proposal(db_session, seed.organization.id, now_utc=MOMENT)

    first = await approve_proposal(
        db_session,
        organization_id=seed.organization.id,
        proposal_id=proposal["proposal_id"],
        decided_by_membership_id=seed.membership.id,
        now_utc=MOMENT,
    )
    retry = await approve_proposal(
        db_session,
        organization_id=seed.organization.id,
        proposal_id=proposal["proposal_id"],
        decided_by_membership_id=seed.membership.id,
        now_utc=MOMENT,
        expected_input_revision=999,
    )
    assert retry.active_version_id == first.active_version_id
    versions = (
        await db_session.scalars(
            select(SchedulerVersionV1).where(
                SchedulerVersionV1.organization_id == seed.organization.id
            )
        )
    ).all()
    assert [row.status for row in versions].count("ACTIVE") == 1

    state = await SchedulerStateService(db_session).get_state(seed.organization.id, seed.year.id)
    await db_session.refresh(state)
    state.input_revision += 1
    state.planning_revision += 1
    await db_session.commit()
    await _enqueue(db_session, seed, key="second-update")
    await db_session.commit()
    await _run_worker(monkeypatch, db_session)
    second = await current_proposal(db_session, seed.organization.id, now_utc=MOMENT)
    await approve_proposal(
        db_session,
        organization_id=seed.organization.id,
        proposal_id=second["proposal_id"],
        decided_by_membership_id=seed.membership.id,
        now_utc=MOMENT,
    )
    with pytest.raises(ProposalConflict) as superseded:
        await approve_proposal(
            db_session,
            organization_id=seed.organization.id,
            proposal_id=proposal["proposal_id"],
            decided_by_membership_id=seed.membership.id,
            now_utc=MOMENT,
        )
    assert superseded.value.code == "proposal_superseded"


async def test_first_approval_marks_the_organization_operational_once(db_session, monkeypatch):
    seed = await _minimal_school(db_session)
    await db_session.commit()
    await _enqueue(db_session, seed)
    await db_session.commit()
    await _run_worker(monkeypatch, db_session)
    proposal = await current_proposal(db_session, seed.organization.id, now_utc=MOMENT)
    assert proposal is not None

    first = await approve_proposal(
        db_session,
        organization_id=seed.organization.id,
        proposal_id=proposal["proposal_id"],
        decided_by_membership_id=seed.membership.id,
        now_utc=MOMENT,
    )
    organization = await db_session.get(models.Organization, seed.organization.id)
    await db_session.refresh(organization)
    assert organization.first_real_schedule_approved_at == MOMENT

    dashboard = await get_dashboard_summary(db_session, seed.organization.id)
    assert dashboard.mode == "OPERATIONAL"

    repeated = await approve_proposal(
        db_session,
        organization_id=seed.organization.id,
        proposal_id=proposal["proposal_id"],
        decided_by_membership_id=seed.membership.id,
        now_utc=MOMENT,
    )
    assert repeated.active_version_id == first.active_version_id
    await db_session.refresh(organization)
    assert organization.first_real_schedule_approved_at == MOMENT

    state = await SchedulerStateService(db_session).get_state(seed.organization.id, seed.year.id)
    await db_session.refresh(state)
    state.input_revision += 1
    state.planning_revision += 1
    await db_session.commit()
    await _enqueue(db_session, seed, key="operational-update")
    await db_session.commit()
    await _run_worker(monkeypatch, db_session)
    second = await current_proposal(db_session, seed.organization.id, now_utc=MOMENT)
    assert second is not None
    later = MOMENT + timedelta(minutes=5)
    await approve_proposal(
        db_session,
        organization_id=seed.organization.id,
        proposal_id=second["proposal_id"],
        decided_by_membership_id=seed.membership.id,
        now_utc=later,
    )
    await db_session.refresh(organization)
    assert organization.first_real_schedule_approved_at == MOMENT


async def test_the_operational_marker_stays_inside_the_approved_organization(
    db_session, monkeypatch
):
    first = await _minimal_school(db_session, clerk_user_id="w08_m1", clerk_org_id="w08_m_org1")
    second = await _minimal_school(
        db_session, clerk_user_id="w08_m2", clerk_org_id="w08_m_org2", module_minutes=50
    )
    await db_session.commit()
    await _enqueue(db_session, first, key="marker-a")
    await db_session.commit()
    await _run_worker(monkeypatch, db_session)
    proposal = await current_proposal(db_session, first.organization.id, now_utc=MOMENT)
    assert proposal is not None

    await approve_proposal(
        db_session,
        organization_id=first.organization.id,
        proposal_id=proposal["proposal_id"],
        decided_by_membership_id=first.membership.id,
        now_utc=MOMENT,
    )

    other = await db_session.get(models.Organization, second.organization.id)
    await db_session.refresh(other)
    assert other.first_real_schedule_approved_at is None
    other_dashboard = await get_dashboard_summary(db_session, second.organization.id)
    assert other_dashboard.mode == "PREPARATION"


async def test_rejection_keeps_the_clock_and_does_not_unlock_a_reroll(db_session, monkeypatch):
    seed = await _minimal_school(db_session)
    await db_session.commit()
    await _enqueue(db_session, seed)
    await db_session.commit()
    await _run_worker(monkeypatch, db_session)
    state = await SchedulerStateService(db_session).get_state(seed.organization.id, seed.year.id)
    await db_session.refresh(state)
    completed_revision = state.last_completed_planning_revision
    success_at = state.last_successful_generation_at

    proposal = await current_proposal(db_session, seed.organization.id, now_utc=MOMENT)
    await reject_proposal(
        db_session,
        organization_id=seed.organization.id,
        proposal_id=proposal["proposal_id"],
        decided_by_membership_id=seed.membership.id,
        reason="A escola corrigiu os dados.",
        now_utc=MOMENT,
    )
    refreshed_state = await SchedulerStateService(db_session).get_state(
        seed.organization.id, seed.year.id
    )
    await db_session.refresh(refreshed_state)
    assert refreshed_state.last_completed_planning_revision == completed_revision
    assert refreshed_state.last_successful_generation_at == success_at

    with pytest.raises(GenerationUnavailable):
        await _enqueue(db_session, seed, key="reroll")


async def test_periodic_renewal_unlocks_after_28_days(db_session, monkeypatch):
    seed = await _minimal_school(db_session)
    await db_session.commit()
    await _enqueue(db_session, seed)
    await db_session.commit()
    await _run_worker(monkeypatch, db_session)
    state = await SchedulerStateService(db_session).get_state(seed.organization.id, seed.year.id)
    await db_session.refresh(state)
    state.last_successful_generation_at = MOMENT - timedelta(days=28)
    await db_session.commit()

    renewal = await _enqueue(db_session, seed, key="periodic-renewal")
    await db_session.commit()
    assert renewal.created is True
    status = await scheduler_status(db_session, seed.organization.id, now_utc=MOMENT)
    assert "PERIODIC_RENEWAL" in status["eligibility"]["reasons"]


async def test_the_executor_lock_is_exclusive_and_has_a_liveness_proof(db_session):
    first = await try_acquire_executor_lock(test_engine)
    assert first is not None
    second = await try_acquire_executor_lock(test_engine)
    assert second is None
    assert await executor_lock_alive(first) is True

    await release_executor_lock(first)
    assert await executor_lock_alive(first) is False
    third = await try_acquire_executor_lock(test_engine)
    assert third is not None
    await release_executor_lock(third)


async def test_a_lost_lock_fails_the_attempt_and_stops_the_solve(db_session, monkeypatch):
    from app import scheduler_v1_worker as worker

    seed = await _minimal_school(db_session)
    await db_session.commit()
    queued = await _enqueue(db_session, seed)
    await db_session.commit()
    claim = await claim_next_job(db_session, now_utc=MOMENT)
    assert claim is not None

    class _Outcome:
        outcome = "INFEASIBLE"

    def slow_search(_claim, _bundle, _cancel_event):
        time.sleep(1.2)
        return _Outcome()

    async def dead_lock(_connection):
        return False

    monkeypatch.setattr(worker, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(worker, "_now", lambda: MOMENT)
    monkeypatch.setattr(worker, "_run_search", slow_search)
    monkeypatch.setattr(worker, "executor_lock_alive", dead_lock)
    monkeypatch.setattr(worker.settings, "SCHEDULER_V1_HEARTBEAT_SECONDS", 0.5)

    result = await worker._execute_claim(claim, object())
    assert result["status"] in ("LOST", "FAILED")

    job = await db_session.get(SchedulerJobV1, queued.job.id)
    await db_session.refresh(job)
    assert job.status == "FAILED"
    assert job.result_code == "LOCK_LOST"
    proposal = await db_session.scalar(
        select(SchedulerProposalV1).where(SchedulerProposalV1.job_id == queued.job.id)
    )
    assert proposal is None


async def test_finalization_rejects_a_candidate_that_the_current_clock_invalidated(
    db_session,
):
    from app.scheduler.application.publishing import ProposalPayload
    from app.scheduler.composition import generate_schedule
    from app.scheduler.domain.candidate import SchedulingStrategy
    from app.scheduler.infrastructure.proposals import persist_proposal
    from app.scheduler.infrastructure.snapshot import load_snapshot

    seed = await _minimal_school(db_session)
    await db_session.commit()
    bundle = await load_snapshot(
        db_session,
        seed.organization.id,
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        now_utc=MOMENT,
        school_year_id=seed.year.id,
    )
    result = generate_schedule(
        bundle.snapshot,
        bundle.periods,
        assess_recovery=False,
        time_limit_seconds=30.0,
        num_workers=1,
        random_seed=1,
    )
    assert result.outcome == "COMPLETE"
    queued = await _enqueue(db_session, seed)
    await db_session.commit()
    claim = await claim_next_job(db_session, now_utc=MOMENT)
    assert claim is not None

    late = MOMENT + timedelta(days=60)
    outcome = await persist_proposal(
        db_session,
        organization_id=seed.organization.id,
        job_id=queued.job.id,
        attempt_token=claim.attempt_token,
        bundle=bundle,
        candidate=result.candidate,
        payload=ProposalPayload(metrics={"stop_reason": "TEST"}, diff={}),
        policy_version="baseline-v1",
        now_utc=late,
    )
    assert outcome.refused == "STALE"
    assert outcome.proposal_id is None

    job = await db_session.get(SchedulerJobV1, queued.job.id)
    await db_session.refresh(job)
    assert job.status == "STALE"
    assert job.result_code == "STALE"
    state = await SchedulerStateService(db_session).get_state(seed.organization.id, seed.year.id)
    await db_session.refresh(state)
    assert state.last_successful_generation_at is None
    assert state.last_completed_planning_revision is None
    proposal = await db_session.scalar(
        select(SchedulerProposalV1).where(SchedulerProposalV1.job_id == queued.job.id)
    )
    assert proposal is None


async def test_finalization_accepts_a_same_day_clock_advance_across_a_period(db_session):
    from zoneinfo import ZoneInfo

    from app.scheduler.application.publishing import ProposalPayload
    from app.scheduler.composition import generate_schedule
    from app.scheduler.domain.candidate import SchedulingStrategy
    from app.scheduler.infrastructure.proposals import persist_proposal
    from app.scheduler.infrastructure.snapshot import load_snapshot

    seed = await _minimal_school(db_session)
    await db_session.commit()
    # The school year starts on 1 September but its first grid day after the
    # queueing moment is the following Monday. Generate from that day so the
    # first lesson is on the same school day as the generation clock.
    moment = datetime(2026, 9, 7, 7, 0, tzinfo=UTC)
    bundle = await load_snapshot(
        db_session,
        seed.organization.id,
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        now_utc=moment,
        school_year_id=seed.year.id,
    )
    result = generate_schedule(
        bundle.snapshot,
        bundle.periods,
        assess_recovery=False,
        time_limit_seconds=30.0,
        num_workers=1,
        random_seed=1,
    )
    assert result.outcome == "COMPLETE"
    # A long job crosses the first lesson's period boundary. The same-day clock
    # advance must not reject a schedule that was future when it was generated.
    first_start = min(lesson.period.start_utc for lesson in result.candidate.lessons)
    zone = ZoneInfo("Europe/Lisbon")
    late = first_start + timedelta(minutes=1)
    assert late.astimezone(zone).date() == moment.astimezone(zone).date()
    queued = await _enqueue(db_session, seed)
    await db_session.commit()
    claim = await claim_next_job(db_session, now_utc=moment)
    assert claim is not None

    outcome = await persist_proposal(
        db_session,
        organization_id=seed.organization.id,
        job_id=queued.job.id,
        attempt_token=claim.attempt_token,
        bundle=bundle,
        candidate=result.candidate,
        payload=ProposalPayload(metrics={"stop_reason": "TEST"}, diff={}),
        policy_version="baseline-v1",
        now_utc=late,
    )
    assert outcome.refused is None
    assert outcome.proposal_id is not None


async def test_a_failure_during_approval_rolls_everything_back(db_session, monkeypatch):
    from app.scheduler.infrastructure import proposals as proposals_module

    seed = await _minimal_school(db_session)
    await db_session.commit()
    await _enqueue(db_session, seed)
    await db_session.commit()
    await _run_worker(monkeypatch, db_session)
    proposal = await current_proposal(db_session, seed.organization.id, now_utc=MOMENT)
    organization_id = seed.organization.id
    school_year_id = seed.year.id
    membership_id = seed.membership.id
    proposal_id = proposal["proposal_id"]

    async def _boom(*args, **kwargs):
        raise RuntimeError("injected mid-approval failure")

    monkeypatch.setattr(proposals_module, "_repoint_lesson_logs", _boom)
    with pytest.raises(RuntimeError, match="injected mid-approval failure"):
        await approve_proposal(
            db_session,
            organization_id=organization_id,
            proposal_id=proposal_id,
            decided_by_membership_id=membership_id,
            now_utc=MOMENT,
        )
    await db_session.rollback()

    state = await SchedulerStateService(db_session).get_state(organization_id, school_year_id)
    await db_session.refresh(state)
    assert state.active_schedule_version_id is None
    assert state.school_year_publication_state == models.SchoolYearPublicationState.UNPUBLISHED
    organization = await db_session.get(models.Organization, organization_id)
    await db_session.refresh(organization)
    assert organization.first_real_schedule_approved_at is None
    refreshed = await db_session.get(SchedulerProposalV1, proposal_id)
    await db_session.refresh(refreshed)
    assert refreshed.status == "PENDING"
    assert refreshed.decided_at is None
    versions = (
        await db_session.scalars(
            select(SchedulerVersionV1).where(SchedulerVersionV1.organization_id == organization_id)
        )
    ).all()
    assert all(row.status == "CANDIDATE" for row in versions)


async def test_finalization_rejects_a_candidate_after_a_concurrent_data_change(
    db_session,
):
    from app.scheduler.application.publishing import ProposalPayload
    from app.scheduler.composition import generate_schedule
    from app.scheduler.domain.candidate import SchedulingStrategy
    from app.scheduler.infrastructure.proposals import persist_proposal
    from app.scheduler.infrastructure.snapshot import load_snapshot

    seed = await _minimal_school(db_session)
    await db_session.commit()
    bundle = await load_snapshot(
        db_session,
        seed.organization.id,
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        now_utc=MOMENT,
        school_year_id=seed.year.id,
    )
    result = generate_schedule(
        bundle.snapshot,
        bundle.periods,
        assess_recovery=False,
        time_limit_seconds=30.0,
        num_workers=1,
        random_seed=1,
    )
    assert result.outcome == "COMPLETE"
    queued = await _enqueue(db_session, seed)
    await db_session.commit()
    claim = await claim_next_job(db_session, now_utc=MOMENT)
    assert claim is not None

    state = await SchedulerStateService(db_session).get_state(seed.organization.id, seed.year.id)
    await db_session.refresh(state)
    state.input_revision += 1
    state.planning_revision += 1
    await db_session.commit()

    outcome = await persist_proposal(
        db_session,
        organization_id=seed.organization.id,
        job_id=queued.job.id,
        attempt_token=claim.attempt_token,
        bundle=bundle,
        candidate=result.candidate,
        payload=ProposalPayload(metrics={"stop_reason": "TEST"}, diff={}),
        policy_version="baseline-v1",
        now_utc=MOMENT,
    )
    assert outcome.refused == "STALE"
    job = await db_session.get(SchedulerJobV1, queued.job.id)
    await db_session.refresh(job)
    assert job.result_code == "STALE"
    refreshed = await SchedulerStateService(db_session).get_state(
        seed.organization.id, seed.year.id
    )
    await db_session.refresh(refreshed)
    assert refreshed.last_successful_generation_at is None
    assert refreshed.last_completed_planning_revision is None


async def test_a_job_never_leaks_across_organizations(db_session):
    first = await _minimal_school(db_session, clerk_user_id="w08_x", clerk_org_id="w08_org_x")
    second = await _minimal_school(
        db_session, clerk_user_id="w08_y", clerk_org_id="w08_org_y", module_minutes=50
    )
    await db_session.commit()
    await _enqueue(db_session, first, key="x")
    await db_session.commit()

    other_status = await scheduler_status(db_session, second.organization.id, now_utc=MOMENT)
    assert other_status["active_job"] is None
    assert other_status["pending_proposal"] is None
