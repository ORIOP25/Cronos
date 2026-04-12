import asyncio
from datetime import date, time, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app import models
from app.api.v1.endpoints import schedule as schedule_endpoint


async def _get_org_id(db_session):
    org = (await db_session.execute(select(models.Organization))).scalars().first()
    return org.id


async def _seed_minimal_generation_data(db_session, org_id: int):
    await _seed_minimal_generation_data_with_settings(
        db_session,
        org_id,
        school_start_date=date(2025, 9, 15),
        school_target_end_date=date(2026, 6, 15),
        school_hard_end_date=None,
        repair_window_days=None,
    )


async def _seed_minimal_generation_data_with_settings(
    db_session,
    org_id: int,
    *,
    school_start_date: date,
    school_target_end_date: date,
    school_hard_end_date: date | None,
    repair_window_days: int | None,
):
    settings = models.OrganizationSettings(
        org_id=org_id,
        academic_year="2025/2026",
        school_start_date=school_start_date,
        school_target_end_date=school_target_end_date,
        school_hard_end_date=school_hard_end_date,
        repair_stability_window_days=repair_window_days,
        region_code="Lisboa",
    )
    db_session.add(settings)

    holiday = models.SchoolCalendarEvent(
        org_id=org_id,
        academic_year="2025/2026",
        name="Feriado Nacional",
        start_date=date(2025, 12, 1),
        end_date=date(2025, 12, 1),
        event_type=models.CalendarEventType.national_holiday,
        source=models.CalendarEventSource.auto,
    )
    db_session.add(holiday)

    course = models.Course(name="Curso Teste", abbreviation="CT", organization_id=org_id)
    db_session.add(course)
    await db_session.flush()

    class_ = models.Class(
        name="CT 25/28",
        size=24,
        start_year=2025,
        end_year=2028,
        grade_level=10,
        course_id=course.id,
        organization_id=org_id,
    )
    db_session.add(class_)

    teacher = models.Teacher(name="Prof. Teste", organization_id=org_id)
    db_session.add(teacher)

    subject = models.Subject(name="Disciplina Teste", organization_id=org_id)
    db_session.add(subject)
    await db_session.flush()

    module = models.Module(
        name="Modulo 1",
        code="M1",
        hours_total=25,
        order=1,
        subject_id=subject.id,
    )
    db_session.add(module)

    link = models.ClassSubjectLink(
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
        organization_id=org_id,
    )
    db_session.add(room)

    timeslot = models.Timeslot(
        day_of_week=0,
        start_time=time(9, 0),
        end_time=time(10, 0),
        organization_id=org_id,
    )
    db_session.add(timeslot)
    await db_session.flush()

    availability = models.Availability(
        teacher_id=teacher.id,
        timeslot_id=timeslot.id,
        score=1,
    )
    db_session.add(availability)

    await db_session.commit()


@pytest.mark.asyncio
async def test_generate_fails_when_settings_missing(async_client, admin_token_headers):
    response = await async_client.post(
        "/api/v1/schedule/generate",
        json={"mode": "full"},
        headers=admin_token_headers,
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["detail"]["error"] == "preflight_failed"
    assert any("data de início" in msg for msg in payload["detail"]["problems"])


@pytest.mark.asyncio
async def test_generate_auto_sync_holidays_is_attempted(
    async_client,
    db_session,
    admin_token_headers,
    monkeypatch,
):
    org_id = await _get_org_id(db_session)
    db_session.add(
        models.OrganizationSettings(
            org_id=org_id,
            academic_year="2025/2026",
            school_start_date=date(2025, 9, 15),
            school_target_end_date=date(2026, 6, 15),
            region_code="Lisboa",
        )
    )
    await db_session.commit()

    called = {"value": False}

    async def fake_sync_holidays(db, org_id, academic_year, region_code):
        await asyncio.sleep(0)
        called["value"] = True
        return 3

    monkeypatch.setattr(schedule_endpoint.settings_service, "sync_holidays", fake_sync_holidays)

    response = await async_client.post(
        "/api/v1/schedule/generate",
        json={"mode": "full"},
        headers=admin_token_headers,
    )

    assert called["value"] is True
    assert response.status_code == 400
    payload = response.json()
    problems = payload["detail"]["problems"]
    assert not any("feriado" in msg.lower() for msg in problems)


@pytest.mark.asyncio
async def test_generate_returns_task_id_with_minimal_valid_data(
    async_client,
    db_session,
    admin_token_headers,
    monkeypatch,
):
    org_id = await _get_org_id(db_session)
    await _seed_minimal_generation_data(db_session, org_id)

    def fake_delay(_org_id, _mode):
        return SimpleNamespace(id="task-test-123")

    monkeypatch.setattr(schedule_endpoint.generate_schedule_task, "delay", fake_delay)

    response = await async_client.post(
        "/api/v1/schedule/generate",
        json={"mode": "full"},
        headers=admin_token_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == "task-test-123"
    assert payload["status"] == "Processing started"


@pytest.mark.asyncio
async def test_repair_generate_fails_when_window_blocks_all_future(
    async_client,
    db_session,
    admin_token_headers,
    monkeypatch,
):
    org_id = await _get_org_id(db_session)
    today = date.today()
    await _seed_minimal_generation_data_with_settings(
        db_session,
        org_id,
        school_start_date=today - timedelta(days=30),
        school_target_end_date=today + timedelta(days=5),
        school_hard_end_date=today + timedelta(days=5),
        repair_window_days=14,
    )

    called = {"value": False}

    def fake_delay(_org_id, _mode):
        called["value"] = True
        return SimpleNamespace(id="task-should-not-run")

    monkeypatch.setattr(schedule_endpoint.generate_schedule_task, "delay", fake_delay)

    response = await async_client.post(
        "/api/v1/schedule/generate",
        json={"mode": "repair"},
        headers=admin_token_headers,
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["detail"]["error"] == "preflight_failed"
    assert any("janela de estabilidade" in msg.lower() for msg in payload["detail"]["problems"])
    assert called["value"] is False


@pytest.mark.asyncio
async def test_repair_generate_succeeds_when_horizon_exists_outside_window(
    async_client,
    db_session,
    admin_token_headers,
    monkeypatch,
):
    org_id = await _get_org_id(db_session)
    today = date.today()
    await _seed_minimal_generation_data_with_settings(
        db_session,
        org_id,
        school_start_date=today - timedelta(days=30),
        school_target_end_date=today + timedelta(days=60),
        school_hard_end_date=today + timedelta(days=60),
        repair_window_days=14,
    )

    def fake_delay(_org_id, _mode):
        return SimpleNamespace(id="task-repair-allowed")

    monkeypatch.setattr(schedule_endpoint.generate_schedule_task, "delay", fake_delay)

    response = await async_client.post(
        "/api/v1/schedule/generate",
        json={"mode": "repair"},
        headers=admin_token_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == "task-repair-allowed"
