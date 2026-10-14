from datetime import UTC, date, datetime, time
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import models
from app.api import deps
from app.main import app
from app.scheduler.infrastructure.models import (
    CurricularAssignment,
    CurricularRequirement,
    SchedulerLessonLogV1,
    SchedulerLessonSliceV1,
)
from tests._support.db_fixtures import accept_current_legal_documents
from tests._support.scheduler_v1 import add_lesson, add_version, lesson_interval

pytestmark = pytest.mark.postgresql

FLOW_START = date(2026, 2, 2)
FLOW_END = date(2026, 2, 13)


@pytest.fixture
def override_auth_actor(db_session):
    async def _get_db():
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    app.dependency_overrides[deps.get_db] = _get_db

    def _override(actor: deps.Actor):
        async def _get_current_user_override():
            return actor

        app.dependency_overrides[deps.get_current_user] = _get_current_user_override

    yield _override
    app.dependency_overrides.pop(deps.get_current_user, None)
    app.dependency_overrides.pop(deps.get_db, None)


async def _prepare_context(db_session):
    org = models.Organization(
        name="Flow API Org",
        clerk_org_id="org_flow_api",
        plan_status=models.OrganizationPlanStatus.active,
        foundation_status=models.OrganizationFoundationStatus.COMPLETED,
        foundation_completed_at=datetime.now(UTC),
    )
    db_session.add(org)
    await db_session.flush()
    user = models.User(
        name="Flow API Admin",
        email="flow_api_admin@test.com",
        clerk_user_id="user_flow_api",
    )
    db_session.add(user)
    await db_session.flush()
    membership = models.OrganizationMembership(
        organization_id=org.id,
        account_id=user.id,
        organization_display_name="Flow API Admin",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.active,
        clerk_membership_id="mem_flow_api",
        can_admin=True,
        can_teach=False,
    )
    db_session.add(membership)
    await db_session.flush()
    await accept_current_legal_documents(
        db_session,
        organization_id=org.id,
        membership_id=membership.id,
    )
    course = models.Course(organization_id=org.id, name="Course", abbreviation="FLW")
    db_session.add(course)
    await db_session.flush()
    class_ = models.Class(
        organization_id=org.id,
        name="10A",
        size=20,
        start_year=2025,
        end_year=2026,
        grade_level=10,
        course_id=course.id,
    )
    subject = models.Subject(
        organization_id=org.id,
        name="Subject",
        required_room_type=models.RoomType.normal,
    )
    room = models.Room(
        organization_id=org.id,
        name="Room",
        type=models.RoomType.normal,
        capacity=30,
    )
    slot = models.Timeslot(
        organization_id=org.id,
        day_of_week=FLOW_START.weekday(),
        start_time=time(9),
        end_time=time(10),
    )
    db_session.add_all([class_, subject, room, slot])
    db_session.add(
        models.OrganizationSettings(
            organization_id=org.id,
            school_start_date=date(2025, 9, 15),
            school_hard_end_date=date(2026, 7, 31),
            repair_stability_window_days=0,
        )
    )
    school_year = models.SchedulerSchoolYear(
        organization_id=org.id,
        label="2025/2026",
        start_date=date(2025, 9, 15),
        hard_end_date=date(2026, 7, 31),
    )
    db_session.add(school_year)
    await db_session.flush()
    db_session.add(
        models.SchedulerSchoolYearState(
            organization_id=org.id,
            school_year_id=school_year.id,
        )
    )
    teacher = models.Teacher(
        organization_id=org.id,
        organization_membership_id=membership.id,
    )
    db_session.add(teacher)
    await db_session.flush()
    db_session.add_all(
        [
            models.Module(
                organization_id=org.id,
                name="Module",
                code="FLW-1",
                hours_total=1,
                order=1,
                subject_id=subject.id,
            ),
            models.ClassSubjectLink(
                organization_id=org.id,
                class_id=class_.id,
                subject_id=subject.id,
                grade_level=10,
                teacher_id=teacher.id,
            ),
        ]
    )
    await db_session.execute(
        models.teacher_subject_link.insert().values(
            organization_id=org.id,
            teacher_id=teacher.id,
            subject_id=subject.id,
        )
    )
    await db_session.commit()
    actor = deps.Actor(
        account_id=user.id,
        clerk_user_id=user.clerk_user_id,
        organization_id=org.id,
        membership_id=membership.id,
        can_admin=True,
        can_teach=False,
        teacher_id=None,
    )
    return SimpleNamespace(
        org=org,
        class_=class_,
        subject=subject,
        room=room,
        slot=slot,
        teacher=teacher,
        membership=membership,
        school_year=school_year,
        actor=actor,
    )


async def _publish_block(db_session, ctx, block_date, key):
    if block_date.weekday() != ctx.slot.day_of_week:
        db_session.add(
            models.Timeslot(
                organization_id=ctx.org.id,
                day_of_week=block_date.weekday(),
                start_time=time(9),
                end_time=time(10),
            )
        )
        await db_session.flush()
    if not hasattr(ctx, "assignment"):
        ctx.assignment = CurricularAssignment(
            organization_id=ctx.org.id,
            school_year_id=ctx.school_year.id,
            class_id=ctx.class_.id,
            subject_id=ctx.subject.id,
            teacher_id=ctx.teacher.id,
        )
        db_session.add(ctx.assignment)
        await db_session.flush()
        module_id = await db_session.scalar(
            select(models.Module.id).where(models.Module.organization_id == ctx.org.id)
        )
        db_session.add(
            CurricularRequirement(
                organization_id=ctx.org.id,
                assignment_id=ctx.assignment.id,
                module_id=module_id,
                sequence=1,
                required_minutes=600,
            )
        )
        seed = SimpleNamespace(
            organization=ctx.org, year=ctx.school_year, assignment=ctx.assignment, room=ctx.room
        )
        ctx.version = await add_version(db_session, seed)
    seed = SimpleNamespace(
        organization=ctx.org, year=ctx.school_year, assignment=ctx.assignment, room=ctx.room
    )
    start, end = lesson_interval(block_date, 9)
    lesson = await add_lesson(
        db_session, seed, ctx.version, stable_key=key, school_date=block_date, start=start, end=end
    )
    module_id = await db_session.scalar(
        select(CurricularRequirement.module_id).where(
            CurricularRequirement.assignment_id == ctx.assignment.id
        )
    )
    db_session.add(
        SchedulerLessonSliceV1(
            organization_id=ctx.org.id,
            school_year_id=ctx.school_year.id,
            lesson_id=lesson.id,
            module_id=module_id,
            offset_minutes=0,
            minutes=60,
        )
    )
    await db_session.commit()
    return lesson


async def test_internship_flow_endpoint_lifecycle(db_session, override_auth_actor):
    ctx = await _prepare_context(db_session)
    override_auth_actor(ctx.actor)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        preview = await ac.post(
            "/api/v1/school/calendar-events/preview",
            json={
                "operation": "create",
                "name": "Estágio 10A",
                "start_date": FLOW_START.isoformat(),
                "end_date": FLOW_END.isoformat(),
                "class_ids": [ctx.class_.id],
            },
        )
        assert preview.status_code == 200
        assert preview.json()["requires_confirmation"] is False

        created = await ac.post(
            "/api/v1/school/calendar-events/",
            json={
                "name": "Estágio 10A",
                "start_date": FLOW_START.isoformat(),
                "end_date": FLOW_END.isoformat(),
                "event_type": "internship_flow",
                "class_ids": [ctx.class_.id],
            },
        )
        assert created.status_code == 200
        assert created.json()["class_ids"] == [ctx.class_.id]
        assert created.json()["school_year_start_year"] == 2025

        listed = await ac.get("/api/v1/school/calendar-events/")
        assert listed.status_code == 200
        assert [row["name"] for row in listed.json()] == ["Estágio 10A"]

        updated = await ac.put(
            f"/api/v1/school/calendar-events/{created.json()['id']}",
            json={
                "name": "Estágio 10A e 10B",
                "start_date": FLOW_START.isoformat(),
                "end_date": FLOW_END.isoformat(),
                "class_ids": [],
            },
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "Estágio 10A e 10B"
        assert updated.json()["class_ids"] == []

        deleted = await ac.delete(f"/api/v1/school/calendar-events/{created.json()['id']}")
        assert deleted.status_code == 200
        assert deleted.json() == {"ok": True}
        assert (await db_session.scalars(select(models.SchoolCalendarEvent))).all() == []


async def test_flow_creation_with_classes_removes_lessons_and_records_absences(
    db_session, override_auth_actor
):
    ctx = await _prepare_context(db_session)
    first = await _publish_block(db_session, ctx, FLOW_START, "flow-api-first")
    second = await _publish_block(db_session, ctx, FLOW_END, "flow-api-second")
    await db_session.commit()
    override_auth_actor(ctx.actor)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        preview = await ac.post(
            "/api/v1/school/calendar-events/preview",
            json={
                "operation": "create",
                "name": "Estágio com aulas",
                "start_date": FLOW_START.isoformat(),
                "end_date": FLOW_END.isoformat(),
                "class_ids": [ctx.class_.id],
            },
        )
        assert preview.status_code == 200
        body = preview.json()
        assert body["requires_confirmation"] is True
        assert len(body["affected_lessons"]) == 2

        created = await ac.post(
            "/api/v1/school/calendar-events/",
            json={
                "name": "Estágio com aulas",
                "start_date": FLOW_START.isoformat(),
                "end_date": FLOW_END.isoformat(),
                "event_type": "internship_flow",
                "class_ids": [ctx.class_.id],
                "confirmation_fingerprint": body["confirmation_fingerprint"],
            },
        )
        assert created.status_code == 200

    logs = (
        await db_session.scalars(
            select(SchedulerLessonLogV1).where(
                SchedulerLessonLogV1.lesson_id.in_([first.id, second.id])
            )
        )
    ).all()
    assert len(logs) == 2
    assert all(log.status == "OCCURRENCE" and log.decision == "GAP" for log in logs)


async def test_flow_endpoint_maps_validation_and_missing_event(db_session, override_auth_actor):
    ctx = await _prepare_context(db_session)
    override_auth_actor(ctx.actor)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        outside = await ac.post(
            "/api/v1/school/calendar-events/",
            json={
                "name": "Fora do período",
                "start_date": "2025-01-01",
                "end_date": "2025-01-05",
                "event_type": "internship_flow",
                "class_ids": [ctx.class_.id],
            },
        )
        assert outside.status_code == 400
        assert outside.json()["detail"]["code"] == "INTERNSHIP_FLOW_INVALID"

        missing = await ac.put(
            "/api/v1/school/calendar-events/9999",
            json={
                "name": "Inexistente",
                "start_date": FLOW_START.isoformat(),
                "end_date": FLOW_END.isoformat(),
                "class_ids": [],
            },
        )
        assert missing.status_code == 400
        assert missing.json()["detail"]["code"] == "INTERNSHIP_FLOW_INVALID"
