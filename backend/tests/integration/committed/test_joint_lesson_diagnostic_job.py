"""The worker persists the proven joint diagnosis code on an INFEASIBLE job.

WBS 3.9. A joint group whose member classes never share a free day is isolated;
the real capacity precheck proves it, ``generate_complete`` records
``JOINT_NO_COMMON_TIME`` on ``evidence.stop_reason``, and the worker persists it
on both ``result_code`` and ``stop_reason``. A generic deficit keeps the generic
code, and ``finish_job`` still prefers cancellation and staleness.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app import models
from app.scheduler.infrastructure.jobs import (
    claim_next_job,
    enqueue_generation,
    finish_job,
    request_cancellation,
)
from app.scheduler.infrastructure.models import SchedulerJobV1, SchedulerLessonV1
from app.scheduler.infrastructure.proposals import approve_proposal
from app.scheduler.infrastructure.queries import current_proposal, get_job
from app.services.scheduler_state_service import SchedulerStateService
from tests._support.scheduler_v1 import (
    MOMENT,
    run_generation,
    seed_generatable_school,
    seed_joint_school,
)

JOINT_CODE = "JOINT_NO_COMMON_TIME"


async def _isolate_first_class(db_session, seed) -> None:
    """An internship flow blocks the first class on every school day (J18)."""
    event = models.SchoolCalendarEvent(
        organization_id=seed.base.organization.id,
        name="Estágio turma A",
        start_date=seed.base.year.start_date,
        end_date=seed.base.year.preferred_end_date,
        event_type=models.CalendarEventType.internship_flow,
        source=models.CalendarEventSource.manual,
    )
    db_session.add(event)
    await db_session.flush()
    db_session.add(
        models.SchoolCalendarEventClass(
            organization_id=seed.base.organization.id,
            calendar_event_id=event.id,
            class_id=seed.base.class_.id,
        )
    )
    await db_session.flush()


async def _enqueue(db_session, base, *, key: str):
    queued = await enqueue_generation(
        db_session,
        base.organization.id,
        idempotency_key=key,
        requested_by_membership_id=base.membership.id,
        now_utc=MOMENT,
    )
    await db_session.commit()
    return queued


async def _run_worker(monkeypatch, now: datetime = MOMENT) -> None:
    from app import scheduler_v1_worker as worker
    from tests._support.db_fixtures import TestingSessionLocal, test_engine

    monkeypatch.setattr(worker, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(worker, "engine_async", test_engine)
    monkeypatch.setattr(worker, "_now", lambda: now)
    monkeypatch.setattr(worker, "RECOVERY_ASSESSMENT_SECONDS", 0.0)
    await worker.process_next_jobs()


async def test_an_isolated_joint_unit_persists_the_joint_diagnosis_code(db_session, monkeypatch):
    seed = await seed_joint_school(db_session)
    await _isolate_first_class(db_session, seed)
    queued = await _enqueue(db_session, seed.base, key="joint-diagnostic")

    await _run_worker(monkeypatch)

    job = await db_session.get(SchedulerJobV1, queued.job.id)
    await db_session.refresh(job)
    assert job.status == "INFEASIBLE"
    assert job.result_code == "JOINT_NO_COMMON_TIME"
    assert job.stop_reason == "JOINT_NO_COMMON_TIME"
    assert job.finished_at is not None


async def test_an_isolated_joint_unit_persists_class_and_subject_ids(db_session, monkeypatch):
    seed = await seed_joint_school(db_session)
    await _isolate_first_class(db_session, seed)
    queued = await _enqueue(db_session, seed.base, key="joint-structured")

    await _run_worker(monkeypatch)

    job = await db_session.get(SchedulerJobV1, queued.job.id)
    await db_session.refresh(job)
    assert job.status == "INFEASIBLE"
    joint = [row for row in (job.diagnostics_json or []) if row["code"] == JOINT_CODE]
    assert len(joint) == 1
    assert set(joint[0]["affected_class_ids"]) == {seed.base.class_.id, seed.second_class.id}
    assert joint[0]["affected_subject_id"] == seed.base.subject.id

    payload = await get_job(db_session, seed.base.organization.id, queued.job.id)

    diagnostics = payload["diagnostics"]
    assert {row["code"] for row in diagnostics} == {JOINT_CODE}
    assert {row["class_name"] for row in diagnostics} == {"A", "B"}
    assert {row["class_id"] for row in diagnostics} == {
        seed.base.class_.id,
        seed.second_class.id,
    }
    assert all(row["subject_name"] == seed.base.subject.name for row in diagnostics)


async def test_protected_class_availability_conflict_releases_the_joint_lesson(
    db_session, monkeypatch
):
    seed = await seed_joint_school(db_session)
    organization_id = seed.base.organization.id
    settings = await db_session.scalar(
        select(models.OrganizationSettings).where(
            models.OrganizationSettings.organization_id == organization_id
        )
    )
    if settings is None:
        settings = models.OrganizationSettings(organization_id=organization_id)
        db_session.add(settings)
    settings.repair_stability_window_days = 10
    await run_generation(db_session, monkeypatch, seed.base, key="protected-publish")
    version_id = int(seed.base.state.active_schedule_version_id)
    first = await db_session.scalar(
        select(SchedulerLessonV1)
        .where(
            SchedulerLessonV1.organization_id == organization_id,
            SchedulerLessonV1.version_id == version_id,
        )
        .order_by(SchedulerLessonV1.starts_at)
        .limit(1)
    )
    released_key = first.stable_key
    slot = await db_session.scalar(
        select(models.Timeslot).where(
            models.Timeslot.organization_id == organization_id,
            models.Timeslot.day_of_week
            == first.starts_at.astimezone(ZoneInfo("Europe/Lisbon")).weekday(),
        )
    )
    db_session.add(
        models.ClassAvailability(
            organization_id=organization_id,
            class_id=seed.second_class.id,
            timeslot_id=slot.id,
            score=models.PreferenceLevel.IMPOSSIBLE.value,
        )
    )
    seed.base.state.input_revision += 1
    seed.base.state.planning_revision += 1
    queued = await _enqueue(db_session, seed.base, key="protected-repair")

    await _run_worker(monkeypatch)

    await db_session.refresh(queued.job)
    payload = await get_job(db_session, organization_id, queued.job.id)
    assert payload["status"] == "SUCCEEDED"
    proposal = await current_proposal(db_session, organization_id)
    await approve_proposal(
        db_session,
        organization_id=organization_id,
        proposal_id=proposal["proposal_id"],
        decided_by_membership_id=seed.base.membership.id,
        now_utc=MOMENT,
    )
    await db_session.refresh(seed.base.state)
    assert int(seed.base.state.active_schedule_version_id) != version_id
    replaced = await db_session.scalars(
        select(SchedulerLessonV1.stable_key).where(
            SchedulerLessonV1.organization_id == organization_id,
            SchedulerLessonV1.version_id == int(seed.base.state.active_schedule_version_id),
        )
    )
    assert released_key not in set(replaced.all())


async def test_a_generic_deficit_keeps_the_generic_job_code(db_session, monkeypatch):
    seed = await seed_generatable_school(db_session, module_minutes=100000)
    queued = await _enqueue(db_session, seed, key="generic-deficit")

    await _run_worker(monkeypatch)

    job = await db_session.get(SchedulerJobV1, queued.job.id)
    await db_session.refresh(job)
    assert job.status == "INFEASIBLE"
    assert job.result_code == "INFEASIBLE"
    assert job.stop_reason == "INFEASIBLE"


async def _claim(db_session, queued):
    claim = await claim_next_job(db_session, now_utc=MOMENT)
    assert claim is not None
    assert claim.job_id == queued.job.id
    return claim


async def test_joint_diagnostics_never_resolve_a_foreign_organization(db_session):
    seed = await seed_joint_school(db_session)
    foreign = await seed_generatable_school(
        db_session, clerk_user_id="foreign_joint", clerk_org_id="foreign_joint_org"
    )
    queued = await _enqueue(db_session, seed.base, key="joint-foreign")
    claim = await _claim(db_session, queued)

    await finish_job(
        db_session,
        organization_id=seed.base.organization.id,
        job_id=queued.job.id,
        attempt_token=claim.attempt_token,
        status="INFEASIBLE",
        result_code=JOINT_CODE,
        stop_reason=JOINT_CODE,
        diagnostics=[
            {
                "code": JOINT_CODE,
                "minimum_missing_minutes": None,
                "affected_class_ids": [foreign.class_.id],
                "affected_subject_id": foreign.subject.id,
            }
        ],
        now_utc=MOMENT,
    )
    await db_session.commit()

    payload = await get_job(db_session, seed.base.organization.id, queued.job.id)

    assert payload["diagnostics"] == [
        {
            "code": JOINT_CODE,
            "minimum_missing_minutes": None,
            "class_id": foreign.class_.id,
            "class_name": None,
            "course_id": None,
            "subject_name": None,
        }
    ]


async def test_finish_job_still_prefers_cancellation_over_the_joint_code(db_session):
    seed = await seed_joint_school(db_session)
    queued = await _enqueue(db_session, seed.base, key="joint-cancel")
    claim = await _claim(db_session, queued)

    await request_cancellation(db_session, seed.base.organization.id, queued.job.id, now_utc=MOMENT)
    written = await finish_job(
        db_session,
        organization_id=seed.base.organization.id,
        job_id=queued.job.id,
        attempt_token=claim.attempt_token,
        status="INFEASIBLE",
        result_code=JOINT_CODE,
        stop_reason=JOINT_CODE,
        now_utc=MOMENT,
    )
    await db_session.commit()

    assert written == "CANCELLED"
    job = await db_session.get(SchedulerJobV1, queued.job.id)
    await db_session.refresh(job)
    assert job.result_code == "CANCELLED"


async def test_finish_job_still_prefers_staleness_over_the_joint_code(db_session):
    seed = await seed_joint_school(db_session)
    queued = await _enqueue(db_session, seed.base, key="joint-stale")
    claim = await _claim(db_session, queued)

    state = await SchedulerStateService(db_session).get_state(
        seed.base.organization.id, seed.base.year.id
    )
    await db_session.refresh(state)
    state.input_revision += 1
    await db_session.commit()

    written = await finish_job(
        db_session,
        organization_id=seed.base.organization.id,
        job_id=queued.job.id,
        attempt_token=claim.attempt_token,
        status="INFEASIBLE",
        result_code=JOINT_CODE,
        stop_reason=JOINT_CODE,
        now_utc=MOMENT,
    )
    await db_session.commit()

    assert written == "STALE"
    job = await db_session.get(SchedulerJobV1, queued.job.id)
    await db_session.refresh(job)
    assert job.result_code == "STALE"


async def test_http_poll_reads_the_joint_class_names_and_subject(
    async_client, db_session, monkeypatch
):
    seed = await seed_joint_school(db_session)
    await _isolate_first_class(db_session, seed)
    queued = await _enqueue(db_session, seed.base, key="joint-http")

    await _run_worker(monkeypatch)

    response = await async_client.get(
        f"/api/v1/scheduler/jobs/{queued.job.id}",
        headers={"Authorization": "Bearer v1_admin"},
    )

    assert response.status_code == 200
    diagnostics = response.json()["diagnostics"]
    assert {row["code"] for row in diagnostics} == {JOINT_CODE}
    assert {row["class_name"] for row in diagnostics} == {"A", "B"}
    assert all(row["subject_name"] == seed.base.subject.name for row in diagnostics)
