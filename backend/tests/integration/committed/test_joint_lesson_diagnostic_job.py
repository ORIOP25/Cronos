"""The worker persists the proven joint diagnosis code on an INFEASIBLE job.

WBS 3.9. A joint group whose member classes never share a free day is isolated;
the real capacity precheck proves it, ``generate_complete`` records
``JOINT_NO_COMMON_TIME`` on ``evidence.stop_reason``, and the worker persists it
on both ``result_code`` and ``stop_reason``. A generic deficit keeps the generic
code, and ``finish_job`` still prefers cancellation and staleness.
"""

from __future__ import annotations

from datetime import datetime

from app import models
from app.scheduler.infrastructure.jobs import (
    claim_next_job,
    enqueue_generation,
    finish_job,
    request_cancellation,
)
from app.scheduler.infrastructure.models import SchedulerJobV1
from app.services.scheduler_state_service import SchedulerStateService
from tests._support.scheduler_v1 import MOMENT, seed_generatable_school, seed_joint_school

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
