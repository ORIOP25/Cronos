import time as perf_time
from datetime import date, time, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app import models, schemas
from app.api.v1.endpoints import schedule as schedule_endpoint
from app.models import LessonOccurrenceStatus
from app.services import occurrence_service
from app.services.operational_seed_service import REFERENCE_DATE, seed_operational_scenarios_sync
from tests.conftest import create_org_and_user, mock_clerk_payload
from unittest.mock import patch


def _auth_headers(email: str) -> dict[str, str]:
        return {"Authorization": "Bearer mock_admin_token"}


async def _get_first_org_id(db_session) -> int:
    org = (await db_session.execute(select(models.Organization))).scalars().first()
    assert org is not None
    return org.id


async def _seed_minimal_generation_context(
    db_session,
    *,
    organization_id: int,
    school_start_date: date,
    school_target_end_date: date,
    school_hard_end_date: date | None,
    repair_window_days: int | None,
) -> None:
    settings = models.OrganizationSettings(
        organization_id=organization_id,
        school_start_date=school_start_date,
        school_target_end_date=school_target_end_date,
        school_hard_end_date=school_hard_end_date,
        repair_stability_window_days=repair_window_days,
    )
    db_session.add(settings)

    holiday = models.SchoolCalendarEvent(
        organization_id=organization_id,
        name="Feriado Nacional",
        start_date=date(2025, 12, 1),
        end_date=date(2025, 12, 1),
        event_type=models.CalendarEventType.national_holiday,
        source=models.CalendarEventSource.auto,
    )
    db_session.add(holiday)

    course = models.Course(name="Curso Alpha", abbreviation="CA", organization_id=organization_id)
    db_session.add(course)
    await db_session.flush()

    klass = models.Class(
        name="CA 25/28",
        size=24,
        start_year=2025,
        end_year=2028,
        grade_level=10,
        course_id=course.id,
        organization_id=organization_id,
    )
    db_session.add(klass)

    teacher = models.Teacher(name="Prof Alpha", organization_id=organization_id)
    db_session.add(teacher)

    subject = models.Subject(name="Disciplina Alpha", organization_id=organization_id)
    db_session.add(subject)
    await db_session.flush()

    module = models.Module(
        name="Modulo Alpha",
        code="ALPHA-M1",
        hours_total=5,
        order=1,
        subject_id=subject.id,
    )
    db_session.add(module)

    class_subject_link = models.ClassSubjectLink(
        class_id=klass.id,
        subject_id=subject.id,
        grade_level=klass.grade_level,
        teacher_id=teacher.id,
    )
    db_session.add(class_subject_link)

    room = models.Room(
        name="Sala Alpha",
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
        teacher_id=teacher.id,
        timeslot_id=timeslot.id,
        score=models.PreferenceLevel.NEUTRAL.value,
    )
    db_session.add(availability)

    await db_session.commit()


async def _seed_operational(db_session) -> dict:
    return await db_session.run_sync(lambda sync_db: seed_operational_scenarios_sync(sync_db))


async def _create_open_occurrence(
    db_session,
    *,
    runtime: dict,
    target_date: date,
) -> int:
    def _run(sync_db):
        base_occurrence = sync_db.get(models.LessonOccurrence, runtime["multi_eligible_occurrence_id"])
        assert base_occurrence is not None

        base_schedule = sync_db.get(models.ScheduleOutput, base_occurrence.schedule_output_id)
        assert base_schedule is not None

        generated = models.ScheduleOutput(
            organization_id=runtime["org_a_id"],
            lesson_id=base_schedule.lesson_id,
            timeslot_id=base_schedule.timeslot_id,
            room_id=base_schedule.room_id,
            generation_id=f"alpha-gate-{target_date.isoformat()}",
            date=target_date,
            is_draft=False,
        )
        sync_db.add(generated)
        sync_db.commit()

        occurrence, _ = occurrence_service.create_occurrence_from_block_sync(
            sync_db,
            runtime["org_a_id"],
            generated.id,
        )

        return occurrence.id

    return await db_session.run_sync(_run)


@pytest.mark.asyncio
async def test_alpha_regression_generation_full_and_repair_allowed(
    async_client,
    db_session,
    monkeypatch,
):
    org, _ = await create_org_and_user(db_session, clerk_user_id="user_admin_001", role="admin")
    organization_id = await _get_first_org_id(db_session)
    today = date.today()
    await _seed_minimal_generation_context(
        db_session,
        organization_id=organization_id,
        school_start_date=today - timedelta(days=30),
        school_target_end_date=today + timedelta(days=60),
        school_hard_end_date=today + timedelta(days=60),
        repair_window_days=14,
    )

    def fake_delay(_org_id, _mode):
        return SimpleNamespace(id=f"task-{_mode}")

    monkeypatch.setattr(schedule_endpoint.generate_schedule_task, "delay", fake_delay)

    payload = mock_clerk_payload("user_admin_001", org.clerk_org_id, "admin")
    headers = {"Authorization": "Bearer test_admin_token_001"}
    with patch("app.api.deps.get_clerk_payload", return_value=payload):
        full_response = await async_client.post(
            "/api/v1/schedule/generate",
            json={"mode": "full"},
            headers=headers,
        )
    assert full_response.status_code == 200
    assert full_response.json()["task_id"] == "task-full"

    with patch("app.api.deps.get_clerk_payload", return_value=payload):
        repair_response = await async_client.post(
            "/api/v1/schedule/generate",
            json={"mode": "repair"},
            headers=headers,
        )
    assert repair_response.status_code == 200
    assert repair_response.json()["task_id"] == "task-repair"


@pytest.mark.asyncio
async def test_alpha_regression_repair_blocks_near_hard_end(
    async_client,
    db_session,
    monkeypatch,
):
    org, _ = await create_org_and_user(db_session, clerk_user_id="user_admin_001", role="admin")
    organization_id = await _get_first_org_id(db_session)
    today = date.today()
    await _seed_minimal_generation_context(
        db_session,
        organization_id=organization_id,
        school_start_date=today - timedelta(days=30),
        school_target_end_date=today + timedelta(days=5),
        school_hard_end_date=today + timedelta(days=5),
        repair_window_days=14,
    )

    called = {"value": False}

    def fake_delay(_org_id, _mode):
        called["value"] = True
        return SimpleNamespace(id="should-not-run")

    monkeypatch.setattr(schedule_endpoint.generate_schedule_task, "delay", fake_delay)

    payload = mock_clerk_payload("user_admin_001", org.clerk_org_id, "admin")
    with patch("app.api.deps.get_clerk_payload", return_value=payload):
        response = await async_client.post(
            "/api/v1/schedule/generate",
            json={"mode": "repair"},
            headers={"Authorization": "Bearer test_admin_token_001"},
        )

    assert response.status_code == 400
    payload = response.json()
    assert payload["detail"]["error"] == "preflight_failed"
    assert any("janela de estabilidade" in msg.lower() for msg in payload["detail"]["problems"])
    assert called["value"] is False


@pytest.mark.asyncio
@pytest.mark.skip(reason="Needs seed refactoring for Clerk")
async def test_alpha_regression_occurrences_substitutions_auth_and_tenant(
    async_client, db_session, admin_token_headers
):
    payload = await _seed_operational(db_session)
    runtime = payload["runtime"]

    # Criar users admin com clerk_user_id na async session para corresponder ao mock
    admin_a_user = (await db_session.execute(
        select(models.User).where(models.User.email == "admin.operacional.a@seed.pt")
    )).scalar_one_or_none()
    admin_b_user = (await db_session.execute(
        select(models.User).where(models.User.email == "admin.operacional.b@seed.pt")
    )).scalar_one_or_none()
    if admin_a_user:
        admin_a_user.clerk_user_id = "user_admin_001"
    if admin_b_user:
        admin_b_user.clerk_user_id = "user_admin_b"
    await db_session.commit()

    occurrence_id = await _create_open_occurrence(
        db_session,
        runtime=runtime,
        target_date=REFERENCE_DATE + timedelta(days=5),
    )

    def _create_teacher_user(sync_db):
        teacher_user_email = f"teacher.alpha.{uuid4().hex[:8]}@seed.pt"
        teacher_user = models.User(
            email=teacher_user_email,
            clerk_user_id=f"seed_{teacher_user_email}",
            is_active=True,
            role=models.UserRole.teacher,
            organization_id=runtime["org_a_id"],
            teacher_id=runtime["expected_first_recommendation_teacher_id"],
        )
        sync_db.add(teacher_user)
        sync_db.commit()
        return teacher_user_email

    teacher_email = await db_session.run_sync(_create_teacher_user)
    # Sincronizar na async session
    await db_session.commit()

    headers = {"Authorization": "Bearer test_token_admin_001"}

    with patch("app.api.deps.get_clerk_payload", return_value=mock_clerk_payload("user_admin_001", "org_001", "admin")):
        rec_response = await async_client.get(
            f"/api/v1/occurrences/{occurrence_id}/substitutes/recommendations",
            headers=headers,
        )
    assert rec_response.status_code == 200
    recommendations = rec_response.json()
    assert len(recommendations) >= 2

    with patch("app.api.deps.get_clerk_payload", return_value=mock_clerk_payload(f"seed_{teacher_email}", runtime.get("org_a_clerk_id"), "member")):
        teacher_forbidden = await async_client.patch(
            f"/api/v1/occurrences/{occurrence_id}",
            json={"status": "GAP"},
            headers=headers,
        )
    assert teacher_forbidden.status_code == 403

    with patch("app.api.deps.get_clerk_payload", return_value=mock_clerk_payload("user_admin_b", "org_002", "admin")):
        tenant_hidden = await async_client.get(
            f"/api/v1/occurrences/{occurrence_id}/substitutes/recommendations",
            headers=headers,
        )
    assert tenant_hidden.status_code == 404

    top_candidate = recommendations[0]
    with patch("app.api.deps.get_clerk_payload", return_value=mock_clerk_payload("user_admin_001", "org_001", "admin")):
        admin_confirm = await async_client.patch(
            f"/api/v1/occurrences/{occurrence_id}",
            json={
                "status": "SUBSTITUTED",
                "substitute_teacher_id": top_candidate["teacher_id"],
                "substitute_subject_id": top_candidate["subject_id"],
            },
            headers=headers,
        )
    assert admin_confirm.status_code == 200
    body = admin_confirm.json()
    assert body["status"] == "SUBSTITUTED"
    assert body["decided_at"] is not None


@pytest.mark.asyncio
async def test_alpha_edge_weekly_simulation_and_audit_trail(db_session):
    payload = await _seed_operational(db_session)
    runtime = payload["runtime"]

    def _run_week(sync_db):
        base_occurrence = sync_db.get(models.LessonOccurrence, runtime["multi_eligible_occurrence_id"])
        assert base_occurrence is not None
        base_schedule = sync_db.get(models.ScheduleOutput, base_occurrence.schedule_output_id)
        assert base_schedule is not None

        week_dates = [REFERENCE_DATE + timedelta(days=offset) for offset in range(7)]
        schedule_ids = []

        for index, target_date in enumerate(week_dates):
            generated = models.ScheduleOutput(
                organization_id=runtime["org_a_id"],
                lesson_id=base_schedule.lesson_id,
                timeslot_id=base_schedule.timeslot_id,
                room_id=base_schedule.room_id,
                generation_id=f"alpha-week-{index}",
                date=target_date,
                is_draft=False,
            )
            sync_db.add(generated)
            sync_db.flush()
            schedule_ids.append(generated.id)

        sync_db.commit()

        for schedule_id in schedule_ids:
            occurrence_service.create_occurrence_from_block_sync(
                sync_db,
                runtime["org_a_id"],
                schedule_id,
            )

        week_occurrences = list(
            sync_db.execute(
                select(models.LessonOccurrence)
                .where(
                    models.LessonOccurrence.schedule_output_id.in_(schedule_ids),
                    models.LessonOccurrence.organization_id == runtime["org_a_id"],
                )
                .order_by(models.LessonOccurrence.date.asc(), models.LessonOccurrence.id.asc())
            ).scalars()
        )

        assert len(week_occurrences) == len(week_dates)

        occurrence_service.update_occurrence_sync(
            sync_db,
            week_occurrences[1].id,
            runtime["org_a_id"],
            schemas.LessonOccurrenceUpdate(status=LessonOccurrenceStatus.GAP),
            decided_by_user_id=runtime["org_a_admin_user_id"],
        )

        recommendations = occurrence_service.get_substitute_recommendations_sync(
            sync_db,
            organization_id=runtime["org_a_id"],
            occurrence_id=week_occurrences[2].id,
        )
        assert recommendations

        occurrence_service.update_occurrence_sync(
            sync_db,
            week_occurrences[2].id,
            runtime["org_a_id"],
            schemas.LessonOccurrenceUpdate(
                status=LessonOccurrenceStatus.SUBSTITUTED,
                substitute_teacher_id=recommendations[0].teacher_id,
                substitute_subject_id=recommendations[0].subject_id,
            ),
            decided_by_user_id=runtime["org_a_admin_user_id"],
        )

        sync_db.expire_all()
        refreshed = list(
            sync_db.execute(
                select(models.LessonOccurrence)
                .where(models.LessonOccurrence.id.in_([occ.id for occ in week_occurrences]))
            ).scalars()
        )

        by_id = {item.id: item for item in refreshed}
        gap_item = by_id[week_occurrences[1].id]
        sub_item = by_id[week_occurrences[2].id]

        status_counts: dict[str, int] = {}
        for item in refreshed:
            key = item.status.value if item.status is not None else "OPEN_PENDING"
            status_counts[key] = status_counts.get(key, 0) + 1
            assert item.created_at is not None

        assert gap_item.decided_by_user_id == runtime["org_a_admin_user_id"]
        assert gap_item.decided_at is not None
        assert sub_item.decided_by_user_id == runtime["org_a_admin_user_id"]
        assert sub_item.decided_at is not None

        return status_counts

    status_counts = await db_session.run_sync(_run_week)

    assert status_counts.get("OPEN_PENDING", 0) >= 5
    assert status_counts.get("GAP", 0) >= 1
    assert status_counts.get("SUBSTITUTED", 0) >= 1


@pytest.mark.asyncio
async def test_alpha_edge_moderate_load_critical_window(db_session):
    payload = await _seed_operational(db_session)
    runtime = payload["runtime"]

    def _run_load(sync_db):
        base_occurrence = sync_db.get(models.LessonOccurrence, runtime["multi_eligible_occurrence_id"])
        assert base_occurrence is not None
        base_schedule = sync_db.get(models.ScheduleOutput, base_occurrence.schedule_output_id)
        assert base_schedule is not None

        load_date = REFERENCE_DATE + timedelta(days=10)
        load_count = 120

        for index in range(load_count):
            sync_db.add(models.ScheduleOutput(
                organization_id=runtime["org_a_id"],
                lesson_id=base_schedule.lesson_id,
                timeslot_id=base_schedule.timeslot_id,
                room_id=base_schedule.room_id,
                generation_id=f"alpha-load-{index}",
                date=load_date,
                is_draft=False,
            ))

        sync_db.commit()

        start = perf_time.monotonic()
        created = occurrence_service.auto_confirm_daily_sync(sync_db, runtime["org_a_id"], load_date)
        elapsed = perf_time.monotonic() - start

        total_for_date = sync_db.execute(
            select(models.LessonOccurrence)
            .where(
                models.LessonOccurrence.organization_id == runtime["org_a_id"],
                models.LessonOccurrence.date == load_date,
            )
        ).scalars().all()

        return {
            "created": created,
            "elapsed": elapsed,
            "total": len(total_for_date),
            "expected_minimum": load_count,
        }

    stats = await db_session.run_sync(_run_load)

    assert stats["created"] >= stats["expected_minimum"]
    assert stats["total"] >= stats["expected_minimum"]
    assert stats["elapsed"] < 60


@pytest.mark.asyncio
async def test_alpha_edge_rollback_after_unexpected_error(db_session, monkeypatch):
    payload = await _seed_operational(db_session)
    runtime = payload["runtime"]

    occurrence_id = await _create_open_occurrence(
        db_session,
        runtime=runtime,
        target_date=REFERENCE_DATE + timedelta(days=9),
    )

    original = occurrence_service._apply_state_accounting
    calls = {"count": 0}

    def _explode_on_first_call(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("forced-mid-operation-error")
        return original(*args, **kwargs)

    monkeypatch.setattr(occurrence_service, "_apply_state_accounting", _explode_on_first_call)

    def _run_rollback(sync_db):
        occurrence_before = sync_db.get(models.LessonOccurrence, occurrence_id)
        assert occurrence_before is not None

        schedule_output = sync_db.get(models.ScheduleOutput, occurrence_before.schedule_output_id)
        assert schedule_output is not None
        lesson = sync_db.get(models.Lesson, schedule_output.lesson_id)
        assert lesson is not None

        progress_before = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == lesson.class_id,
                models.ClassProgress.module_id == occurrence_before.planned_module_id,
            )
        ).scalar_one_or_none()

        before_completed = float(progress_before.hours_completed) if progress_before is not None else 0.0
        before_debt = float(progress_before.hours_debt) if progress_before is not None else 0.0

        raised = False
        try:
            occurrence_service.update_occurrence_sync(
                sync_db,
                occurrence_id,
                runtime["org_a_id"],
                schemas.LessonOccurrenceUpdate(status=LessonOccurrenceStatus.GAP),
                decided_by_user_id=runtime["org_a_admin_user_id"],
            )
        except RuntimeError:
            raised = True

        sync_db.expire_all()

        occurrence_after = sync_db.get(models.LessonOccurrence, occurrence_id)
        assert occurrence_after is not None

        progress_after = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == lesson.class_id,
                models.ClassProgress.module_id == occurrence_after.planned_module_id,
            )
        ).scalar_one_or_none()

        after_completed = float(progress_after.hours_completed) if progress_after is not None else 0.0
        after_debt = float(progress_after.hours_debt) if progress_after is not None else 0.0

        return {
            "raised": raised,
            "status": occurrence_after.status.value if occurrence_after.status is not None else None,
            "decided_at": occurrence_after.decided_at,
            "before_hours_completed": before_completed,
            "before_hours_debt": before_debt,
            "after_hours_completed": after_completed,
            "after_hours_debt": after_debt,
        }

    result = await db_session.run_sync(_run_rollback)

    assert result["raised"] is True
    assert result["status"] is None
    assert result["decided_at"] is None
    assert result["after_hours_completed"] == pytest.approx(result["before_hours_completed"])
    assert result["after_hours_debt"] == pytest.approx(result["before_hours_debt"])
