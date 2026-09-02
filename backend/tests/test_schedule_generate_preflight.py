import asyncio
import os
from datetime import date, time, timedelta

import pytest
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.engine import make_url

from app import models
from app.api import deps
from app.main import app
from app.services import settings_service
from tests.conftest import create_teacher_profile


def _issue_codes(response):
    return {issue["code"] for issue in response.json()["detail"]["issues"]}


@pytest.fixture
def dispatched_tasks():
    calls = []

    class RecordingDispatcher:
        def dispatch(self, *, organization_id, job_id, task_id):
            calls.append((organization_id, job_id, task_id))

    app.dependency_overrides[deps.get_scheduler_task_dispatcher] = RecordingDispatcher
    try:
        yield calls
    finally:
        app.dependency_overrides.pop(deps.get_scheduler_task_dispatcher, None)


async def _get_org_id(db_session):
    org = (await db_session.execute(select(models.Organization))).scalars().first()
    if org is None:
        org = models.Organization(name="Org Teste Preflight", plan_status="active")
        db_session.add(org)
        await db_session.commit()
        await db_session.refresh(org)
    return org.id


async def _seed_minimal_generation_data(db_session, organization_id: int):
    await _seed_minimal_generation_data_with_settings(
        db_session,
        organization_id,
        school_start_date=date(2025, 9, 15),
        school_hard_end_date=date(2026, 7, 31),
        repair_window_days=None,
    )


async def _seed_minimal_generation_data_with_settings(
    db_session,
    organization_id: int,
    *,
    school_start_date: date,
    school_hard_end_date: date | None,
    repair_window_days: int | None,
):
    settings = models.OrganizationSettings(
        organization_id=organization_id,
        school_start_date=school_start_date,
        school_hard_end_date=school_hard_end_date,
        repair_stability_window_days=repair_window_days,
    )
    db_session.add(settings)
    if school_hard_end_date is not None:
        school_year = models.SchedulerSchoolYear(
            organization_id=organization_id,
            label=f"{school_start_date.year}/{school_hard_end_date.year}",
            start_date=school_start_date,
            hard_end_date=school_hard_end_date,
            timezone="Europe/Lisbon",
        )
        db_session.add(school_year)
        await db_session.flush()
        db_session.add(
            models.SchedulerSchoolYearState(
                organization_id=organization_id,
                school_year_id=school_year.id,
            )
        )

    holiday = models.SchoolCalendarEvent(
        organization_id=organization_id,
        name="Feriado Nacional",
        start_date=date(2025, 12, 1),
        end_date=date(2025, 12, 1),
        event_type=models.CalendarEventType.national_holiday,
        source=models.CalendarEventSource.auto,
    )
    db_session.add(holiday)

    course = models.Course(name="Curso Teste", abbreviation="CT", organization_id=organization_id)
    db_session.add(course)
    await db_session.flush()

    class_ = models.Class(
        name="CT 25/28",
        size=24,
        start_year=2025,
        end_year=2028,
        grade_level=10,
        course_id=course.id,
        organization_id=organization_id,
    )
    db_session.add(class_)

    teacher = await create_teacher_profile(
        db_session,
        name="Prof. Teste",
        organization_id=organization_id,
    )

    subject = models.Subject(name="Disciplina Teste", organization_id=organization_id)
    db_session.add(subject)
    await db_session.flush()

    module = models.Module(
        organization_id=organization_id,
        name="Modulo 1",
        code="M1",
        hours_total=25,
        order=1,
        subject_id=subject.id,
    )
    db_session.add(module)

    link = models.ClassSubjectLink(
        organization_id=organization_id,
        class_id=class_.id,
        subject_id=subject.id,
        grade_level=class_.grade_level,
        teacher_id=teacher.id,
    )
    db_session.add(link)

    room = models.Room(
        name="Sala 101",
        capacity=30,
        type=models.RoomType.normal,
        organization_id=organization_id,
    )
    db_session.add(room)

    timeslot = models.Timeslot(
        day_of_week=0,
        start_time=time(9, 0),
        end_time=time(10, 0),
        organization_id=organization_id,
    )
    db_session.add(timeslot)
    await db_session.flush()

    availability = models.Availability(
        organization_id=organization_id,
        teacher_id=teacher.id,
        timeslot_id=timeslot.id,
        score=1,
    )
    db_session.add(availability)

    await db_session.commit()


async def _publish_schedule_with_explicit_debt(db_session, organization_id: int):
    state = await db_session.scalar(
        select(models.SchedulerSchoolYearState).where(
            models.SchedulerSchoolYearState.organization_id == organization_id
        )
    )
    assert state is not None
    state.school_year_publication_state = models.SchoolYearPublicationState.PUBLISHED
    state.active_schedule_version_id = "active-v1"
    state.approved_scheduler_state_version = state.scheduler_state_version
    db_session.add(
        models.LessonOccurrence(
            organization_id=organization_id,
            date=date.today(),
            status=models.LessonOccurrenceStatus.GAP,
            revision=1,
            is_active=True,
            planned_hours=1.0,
            hours_given=0,
        )
    )
    await db_session.commit()


async def test_generate_fails_when_settings_missing(async_client, clerk_admin_headers):
    response = await async_client.post(
        "/api/v1/scheduler/generate",
        json={},
        headers=clerk_admin_headers,
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["detail"]["error"] == "preflight_failed"
    assert payload["detail"]["status"] == "BLOCKED"
    assert "MISSING_CALENDAR" in _issue_codes(response)


async def test_generate_does_not_sync_holidays_during_preflight(
    async_client,
    db_session,
    clerk_admin_headers,
    monkeypatch,
):
    organization_id = await _get_org_id(db_session)
    db_session.add(
        models.OrganizationSettings(
            organization_id=organization_id,
            school_start_date=date(2025, 9, 15),
        )
    )
    await db_session.commit()

    called = {"value": False}

    async def fake_sync_holidays(db, organization_id):
        await asyncio.sleep(0)
        called["value"] = True
        return 3

    monkeypatch.setattr(settings_service, "sync_holidays", fake_sync_holidays)

    response = await async_client.post(
        "/api/v1/scheduler/generate",
        json={},
        headers=clerk_admin_headers,
    )

    assert called["value"] is False
    assert response.status_code == 400
    payload = response.json()
    assert payload["detail"]["status"] == "BLOCKED"
    assert "HOLIDAYS_NOT_SYNCHRONIZED" not in _issue_codes(response)


async def test_generate_returns_canonical_job_contract_with_minimal_valid_data(
    async_client,
    db_session,
    clerk_admin_headers,
    dispatched_tasks,
):
    organization_id = await _get_org_id(db_session)
    await _seed_minimal_generation_data(db_session, organization_id)

    response = await async_client.post(
        "/api/v1/scheduler/generate",
        json={},
        headers=clerk_admin_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert dispatched_tasks == [
        (
            organization_id,
            payload["job_id"],
            f"scheduler-job-{payload['job_id']}",
        )
    ]
    assert "task_id" not in payload
    assert "preflight" not in payload
    assert payload["status"] == "QUEUED"
    assert payload["strategy"] == "COMPLETE_GENERATION"
    assert payload["trigger_type"] == "FIRST_GENERATION"


async def test_generate_commits_job_before_dispatch(
    async_client,
    db_session,
    clerk_admin_headers,
):
    organization_id = await _get_org_id(db_session)
    await _seed_minimal_generation_data(db_session, organization_id)
    sync_url = make_url(os.environ["TEST_DATABASE_URL"]).set(drivername="postgresql+psycopg2")
    independent_engine = create_engine(sync_url.render_as_string(hide_password=False))
    observed = {}

    class IndependentSessionDispatcher:
        def dispatch(self, *, organization_id, job_id, task_id):
            with independent_engine.begin() as connection:
                connection.execute(
                    text(
                        "SELECT set_config('app.current_organization_id', :organization_id, true)"
                    ),
                    {"organization_id": str(organization_id)},
                )
                observed["job_id"] = connection.scalar(
                    text("SELECT id FROM schedule_generation_job WHERE id = :job_id"),
                    {"job_id": job_id},
                )
                observed["task_id"] = task_id

    app.dependency_overrides[deps.get_scheduler_task_dispatcher] = IndependentSessionDispatcher
    try:
        response = await async_client.post(
            "/api/v1/scheduler/generate",
            json={},
            headers=clerk_admin_headers,
        )
    finally:
        app.dependency_overrides.pop(deps.get_scheduler_task_dispatcher, None)
        independent_engine.dispose()

    assert response.status_code == 200
    assert observed["job_id"] == response.json()["job_id"]
    assert observed["task_id"] == f"scheduler-job-{response.json()['job_id']}"


async def test_generate_marks_dispatch_failure_after_commit(
    async_client,
    db_session,
    clerk_admin_headers,
):
    organization_id = await _get_org_id(db_session)
    await _seed_minimal_generation_data(db_session, organization_id)

    class FailingDispatcher:
        def dispatch(self, **_kwargs):
            raise RuntimeError("broker unavailable")

    app.dependency_overrides[deps.get_scheduler_task_dispatcher] = FailingDispatcher
    try:
        response = await async_client.post(
            "/api/v1/scheduler/generate",
            json={},
            headers=clerk_admin_headers,
        )
    finally:
        app.dependency_overrides.pop(deps.get_scheduler_task_dispatcher, None)

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "generation_dispatch_failed"
    job = await db_session.scalar(
        select(models.ScheduleGenerationJob)
        .where(models.ScheduleGenerationJob.organization_id == organization_id)
        .order_by(models.ScheduleGenerationJob.id.desc())
    )
    assert job is not None
    assert job.job_status == models.ScheduleGenerationJobStatus.FAILED
    assert job.failure_message == "Could not dispatch generation job: broker unavailable"


async def test_generate_refreshes_selection_after_preflight_imports_holidays(
    async_client,
    db_session,
    clerk_admin_headers,
    dispatched_tasks,
):
    organization_id = await _get_org_id(db_session)
    await _seed_minimal_generation_data(db_session, organization_id)
    await db_session.execute(
        delete(models.SchoolCalendarEvent).where(
            models.SchoolCalendarEvent.organization_id == organization_id,
            models.SchoolCalendarEvent.source == models.CalendarEventSource.auto,
        )
    )
    await db_session.commit()

    response = await async_client.post(
        "/api/v1/scheduler/generate",
        json={},
        headers=clerk_admin_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert dispatched_tasks[0][:2] == (organization_id, payload["job_id"])
    assert payload["strategy"] == "COMPLETE_GENERATION"


async def test_canonical_scheduler_generation_job_and_cancel_contract(
    async_client,
    db_session,
    clerk_admin_headers,
    dispatched_tasks,
):
    organization_id = await _get_org_id(db_session)
    await _seed_minimal_generation_data(db_session, organization_id)
    generated = await async_client.post(
        "/api/v1/scheduler/generate",
        json={"idempotency_key": "canonical-generate"},
        headers=clerk_admin_headers,
    )

    assert generated.status_code == 200
    payload = generated.json()
    assert payload == {
        "job_id": payload["job_id"],
        "strategy": "COMPLETE_GENERATION",
        "trigger_type": "FIRST_GENERATION",
        "status": "QUEUED",
    }
    assert dispatched_tasks[0][:2] == (organization_id, payload["job_id"])
    assert "task_id" not in payload
    assert "solver_version" not in payload
    assert "preflight" not in payload

    job = await async_client.get(
        f"/api/v1/scheduler/jobs/{payload['job_id']}",
        headers=clerk_admin_headers,
    )
    assert job.status_code == 200
    assert job.json()["job_status"] == "QUEUED"

    canceled = await async_client.post(
        f"/api/v1/scheduler/jobs/{payload['job_id']}/cancel",
        headers=clerk_admin_headers,
    )
    assert canceled.status_code == 200
    assert canceled.json() == {
        "job_id": payload["job_id"],
        "job_status": "CANCEL_REQUESTED",
    }


async def test_generate_idempotency_key_dispatches_only_once(
    async_client,
    db_session,
    clerk_admin_headers,
    dispatched_tasks,
):
    organization_id = await _get_org_id(db_session)
    await _seed_minimal_generation_data(db_session, organization_id)
    payload = {"idempotency_key": "same-click"}

    first = await async_client.post(
        "/api/v1/scheduler/generate",
        json=payload,
        headers=clerk_admin_headers,
    )
    retry = await async_client.post(
        "/api/v1/scheduler/generate",
        json=payload,
        headers=clerk_admin_headers,
    )

    assert first.status_code == retry.status_code == 200
    assert first.json()["job_id"] == retry.json()["job_id"]
    expected_task_id = f"scheduler-job-{first.json()['job_id']}"
    assert dispatched_tasks == [
        (
            organization_id,
            first.json()["job_id"],
            expected_task_id,
        )
    ]


async def test_generate_explains_when_published_schedule_has_no_trigger(
    async_client,
    db_session,
    clerk_admin_headers,
):
    organization_id = await _get_org_id(db_session)
    await _seed_minimal_generation_data(db_session, organization_id)
    state = await db_session.scalar(
        select(models.SchedulerSchoolYearState).where(
            models.SchedulerSchoolYearState.organization_id == organization_id
        )
    )
    assert state is not None
    state.school_year_publication_state = models.SchoolYearPublicationState.PUBLISHED
    state.active_schedule_version_id = "active-v1"
    state.approved_scheduler_state_version = state.scheduler_state_version
    await db_session.commit()

    response = await async_client.post(
        "/api/v1/scheduler/generate",
        json={},
        headers=clerk_admin_headers,
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["error"] == "no_operational_trigger"
    assert "no unresolved explicit debt" in detail["message"]


async def test_repair_generate_fails_when_window_blocks_all_future(
    async_client,
    db_session,
    clerk_admin_headers,
    dispatched_tasks,
):
    organization_id = await _get_org_id(db_session)
    today = date.today()
    await _seed_minimal_generation_data_with_settings(
        db_session,
        organization_id,
        school_start_date=today - timedelta(days=30),
        school_hard_end_date=today + timedelta(days=5),
        repair_window_days=14,
    )
    await _publish_schedule_with_explicit_debt(db_session, organization_id)

    response = await async_client.post(
        "/api/v1/scheduler/generate",
        json={},
        headers=clerk_admin_headers,
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["detail"]["error"] == "preflight_failed"
    assert "REPAIR_WINDOW_INFEASIBLE" in _issue_codes(response)
    assert dispatched_tasks == []


async def test_repair_generate_succeeds_when_horizon_exists_outside_window(
    async_client,
    db_session,
    clerk_admin_headers,
    dispatched_tasks,
):
    organization_id = await _get_org_id(db_session)
    today = date.today()
    await _seed_minimal_generation_data_with_settings(
        db_session,
        organization_id,
        school_start_date=today - timedelta(days=30),
        school_hard_end_date=today + timedelta(days=60),
        repair_window_days=14,
    )
    module = await db_session.scalar(
        select(models.Module).where(models.Module.organization_id == organization_id)
    )
    module.required_minutes = 60
    await _publish_schedule_with_explicit_debt(db_session, organization_id)

    response = await async_client.post(
        "/api/v1/scheduler/generate",
        json={},
        headers=clerk_admin_headers,
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert dispatched_tasks == [
        (
            organization_id,
            payload["job_id"],
            f"scheduler-job-{payload['job_id']}",
        )
    ]
    assert payload["strategy"] == "ADAPTIVE_REPAIR"
    assert payload["trigger_type"] == "EXPLICIT_DEBT"
