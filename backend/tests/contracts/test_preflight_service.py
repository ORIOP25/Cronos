from datetime import UTC, date, datetime, time, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app import models, schemas
from app.api import deps
from app.main import app
from app.scheduler.domain.candidate import SchedulingStrategy
from app.scheduler.infrastructure.snapshot import SnapshotConfigurationError, load_snapshot
from app.services.preflight_service import (
    PreflightService,
    _validate_room_requirements,
    _validate_subject_requirements,
)
from tests._support.db_fixtures import (
    accept_current_legal_documents,
    create_org_and_user,
    create_teacher_profile,
)
from tests._support.scheduler_v1 import MOMENT, seed_generatable_school

pytestmark = pytest.mark.postgresql


async def _create_org_and_admin(db_session, org_name: str, clerk_org: str):
    org = models.Organization(
        name=org_name,
        clerk_org_id=clerk_org,
        plan_status=models.OrganizationPlanStatus.active,
        foundation_status=models.OrganizationFoundationStatus.COMPLETED,
        foundation_completed_at=datetime.now(UTC),
    )
    db_session.add(org)
    await db_session.flush()

    user = models.User(
        name="Preflight Admin",
        email=f"preflight_{clerk_org}@test.com",
        clerk_user_id=f"user_{clerk_org}",
    )
    db_session.add(user)
    await db_session.flush()

    mem = models.OrganizationMembership(
        organization_id=org.id,
        account_id=user.id,
        organization_display_name="Preflight Admin",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.active,
        clerk_membership_id=f"mem_{clerk_org}",
        can_admin=True,
        can_teach=False,
    )
    db_session.add(mem)
    await db_session.flush()
    await accept_current_legal_documents(
        db_session,
        organization_id=org.id,
        membership_id=mem.id,
    )
    return org, user, mem


@pytest.fixture
def override_auth_actor(db_session):
    async def _get_db():
        yield db_session

    app.dependency_overrides[deps.get_db] = _get_db

    def _override(actor: deps.Actor):
        async def _get_current_user_override():
            return actor

        app.dependency_overrides[deps.get_current_user] = _get_current_user_override

    yield _override
    app.dependency_overrides.pop(deps.get_current_user, None)
    app.dependency_overrides.pop(deps.get_db, None)


async def test_preflight_service_returns_canonical_report(db_session):
    org, user, mem = await _create_org_and_admin(
        db_session, "Preflight Service School", "org_preflight_svc"
    )

    # Add academic year settings
    settings = models.OrganizationSettings(
        organization_id=org.id,
        school_start_date=date(2025, 9, 15),
        school_hard_end_date=date(2026, 7, 31),
    )
    db_session.add(settings)

    # Add timeslot
    ts = models.Timeslot(
        organization_id=org.id,
        day_of_week=0,
        start_time=time(8, 30),
        end_time=time(9, 20),
    )
    db_session.add(ts)
    await db_session.flush()

    service = PreflightService(db_session)
    report = await service.evaluate(organization_id=org.id)

    assert report.status == "BLOCKED"
    issue_codes = {issue.code for issue in report.issues}
    assert "ACTIVE_SCHOOL_YEAR_REQUIRED" in issue_codes
    assert "MISSING_ROOMS" in issue_codes
    assert "MISSING_TEACHERS" in issue_codes


async def _create_repair_org(db_session, org_name: str, clerk_org: str, *, window_days: int):
    org, _user, _mem = await _create_org_and_admin(db_session, org_name, clerk_org)
    today = date.today()
    db_session.add_all(
        [
            models.OrganizationSettings(
                organization_id=org.id,
                school_start_date=today - timedelta(days=30),
                school_hard_end_date=today + timedelta(days=60),
                repair_stability_window_days=window_days,
            ),
            models.SchedulerSchoolYear(
                organization_id=org.id,
                label="2025/2026",
                start_date=today - timedelta(days=30),
                hard_end_date=today + timedelta(days=60),
                timezone="Europe/Lisbon",
            ),
        ]
    )
    await db_session.flush()
    return org


async def test_preflight_repair_without_timeslots_keeps_missing_timeslots(db_session):
    org = await _create_repair_org(
        db_session, "Repair No Grid School", "org_repair_no_grid", window_days=14
    )

    report = await PreflightService(db_session).evaluate(
        organization_id=org.id,
        strategy=models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR,
        resolve_fingerprint=False,
    )

    issue_codes = {issue.code for issue in report.issues}
    assert "MISSING_TIMESLOTS" in issue_codes
    assert "REPAIR_WINDOW_INFEASIBLE" not in issue_codes


async def test_preflight_repair_window_counts_grid_days(db_session):
    org = await _create_repair_org(
        db_session, "Repair Grid School", "org_repair_grid", window_days=5
    )
    school_year = await db_session.scalar(
        select(models.SchedulerSchoolYear).where(
            models.SchedulerSchoolYear.organization_id == org.id
        )
    )
    db_session.add(
        models.Timeslot(
            organization_id=org.id,
            day_of_week=0,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
    )
    await db_session.flush()
    school_year.hard_end_date = date.today() + timedelta(days=7)
    settings = await db_session.scalar(
        select(models.OrganizationSettings).where(
            models.OrganizationSettings.organization_id == org.id
        )
    )
    settings.school_hard_end_date = school_year.hard_end_date
    await db_session.flush()

    blocked = await PreflightService(db_session).evaluate(
        organization_id=org.id,
        school_year_id=school_year.id,
        strategy=models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR,
        resolve_fingerprint=False,
    )
    assert "REPAIR_WINDOW_INFEASIBLE" in {issue.code for issue in blocked.issues}

    school_year.hard_end_date = date.today() + timedelta(days=60)
    settings.school_hard_end_date = school_year.hard_end_date
    await db_session.flush()

    allowed = await PreflightService(db_session).evaluate(
        organization_id=org.id,
        school_year_id=school_year.id,
        strategy=models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR,
        resolve_fingerprint=False,
    )
    assert "REPAIR_WINDOW_INFEASIBLE" not in {issue.code for issue in allowed.issues}


async def test_preflight_endpoint_returns_report(db_session, override_auth_actor):
    org, user, mem = await _create_org_and_admin(
        db_session, "Preflight API School", "org_preflight_api"
    )
    actor = deps.Actor(
        account_id=user.id,
        clerk_user_id=user.clerk_user_id,
        organization_id=org.id,
        membership_id=mem.id,
        can_admin=True,
        can_teach=False,
        teacher_id=None,
    )
    override_auth_actor(actor)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/readiness/prevalidation")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "BLOCKED"
        assert "issues" in data
        assert any(issue["code"] == "ACTIVE_SCHOOL_YEAR_REQUIRED" for issue in data["issues"])


async def test_preflight_rejects_room_that_cannot_fit_assigned_class(db_session):
    org, _ = await create_org_and_user(
        db_session,
        clerk_user_id="preflight-room-user",
        clerk_org_id="preflight-room-org",
    )
    course = models.Course(organization_id=org.id, name="Curso", abbreviation="C")
    subject = models.Subject(
        organization_id=org.id,
        name="Laboratório",
        required_room_type=models.RoomType.lab,
    )
    db_session.add_all([course, subject])
    await db_session.flush()
    school_class = models.Class(
        organization_id=org.id,
        course_id=course.id,
        name="Turma grande",
        size=30,
        grade_level=10,
        start_year=2025,
        end_year=2028,
    )
    db_session.add(school_class)
    await db_session.flush()
    db_session.add(
        models.Module(
            organization_id=org.id,
            subject_id=subject.id,
            name="Módulo",
            required_minutes=60,
            order=0,
        )
    )
    teacher = await create_teacher_profile(
        db_session, organization_id=org.id, subject_ids=[subject.id]
    )
    db_session.add(
        models.ClassSubjectLink(
            organization_id=org.id,
            class_id=school_class.id,
            subject_id=subject.id,
            grade_level=10,
            teacher_id=teacher.id,
        )
    )
    db_session.add(
        models.Room(
            organization_id=org.id,
            name="Lab pequeno",
            type=models.RoomType.lab,
            capacity=20,
        )
    )
    await db_session.flush()

    issues = await _validate_room_requirements(db_session, org.id)

    assert issues and issues[0].code == "NO_ELIGIBLE_ROOM"
    assert issues[0].severity == "BLOCKER"
    assert issues[0].route == "/rooms"
    assert issues[0].context == {
        "class_id": school_class.id,
        "class_name": "Turma grande",
        "subject_id": subject.id,
        "subject_name": "Laboratório",
        "required_room_type": "lab",
        "required_capacity": 30,
        "max_available_capacity": 20,
        "reason": "INSUFFICIENT_CAPACITY",
    }
    assert "30 alunos" in issues[0].message
    assert "20 lugares" in issues[0].message

    assert await _validate_subject_requirements(db_session, org.id, {subject.id}) == []


async def test_preflight_ignores_archived_room(db_session):
    org, _ = await create_org_and_user(
        db_session,
        clerk_user_id="preflight-archived-room-user",
        clerk_org_id="preflight-archived-room-org",
    )
    course = models.Course(organization_id=org.id, name="Curso Sala", abbreviation="CSA")
    subject = models.Subject(
        organization_id=org.id,
        name="Laboratório Arquivado",
        required_room_type=models.RoomType.lab,
    )
    db_session.add_all([course, subject])
    await db_session.flush()
    school_class = models.Class(
        organization_id=org.id,
        course_id=course.id,
        name="Turma média",
        size=20,
        grade_level=10,
        start_year=2025,
        end_year=2028,
    )
    room = models.Room(
        organization_id=org.id,
        name="Lab arquivado",
        type=models.RoomType.lab,
        capacity=30,
        is_archived=True,
    )
    db_session.add_all([school_class, room])
    await db_session.flush()
    db_session.add(
        models.Module(
            organization_id=org.id,
            subject_id=subject.id,
            name="Módulo Sala",
            required_minutes=60,
            order=0,
        )
    )
    teacher = await create_teacher_profile(
        db_session, organization_id=org.id, subject_ids=[subject.id]
    )
    db_session.add(
        models.ClassSubjectLink(
            organization_id=org.id,
            class_id=school_class.id,
            subject_id=subject.id,
            grade_level=10,
            teacher_id=teacher.id,
        )
    )
    await db_session.flush()

    blocked = await _validate_room_requirements(db_session, org.id)
    assert blocked and blocked[0].code == "NO_ELIGIBLE_ROOM"
    assert blocked[0].context["reason"] == "NO_ROOM_OF_TYPE"

    room.is_archived = False
    await db_session.flush()
    allowed = await _validate_room_requirements(db_session, org.id)
    assert allowed == []


async def _create_gym_scenario(
    db_session,
    *,
    suffix: str,
    class_name: str = "TDESP 10",
    size: int = 27,
    gym_capacities: tuple[int, ...] = (25, 26),
):
    org, _ = await create_org_and_user(
        db_session,
        clerk_user_id=f"gym-{suffix}-user",
        clerk_org_id=f"gym-{suffix}-org",
    )
    course = models.Course(organization_id=org.id, name=f"Curso {suffix}", abbreviation="TDESP")
    subject = models.Subject(
        organization_id=org.id,
        name="Treino Desportivo",
        required_room_type=models.RoomType.gym,
    )
    db_session.add_all([course, subject])
    await db_session.flush()
    school_class = models.Class(
        organization_id=org.id,
        course_id=course.id,
        name=class_name,
        size=size,
        grade_level=10,
        start_year=2025,
        end_year=2028,
    )
    db_session.add(school_class)
    await db_session.flush()
    db_session.add(
        models.Module(
            organization_id=org.id,
            subject_id=subject.id,
            name="M1",
            required_minutes=60,
            order=0,
        )
    )
    teacher = await create_teacher_profile(
        db_session, organization_id=org.id, subject_ids=[subject.id]
    )
    db_session.add(
        models.ClassSubjectLink(
            organization_id=org.id,
            class_id=school_class.id,
            subject_id=subject.id,
            grade_level=10,
            teacher_id=teacher.id,
        )
    )
    rooms = []
    for index, capacity in enumerate(gym_capacities):
        room = models.Room(
            organization_id=org.id,
            name=f"G-{index + 1:02d}",
            type=models.RoomType.gym,
            capacity=capacity,
        )
        db_session.add(room)
        rooms.append(room)
    await db_session.flush()
    return org, school_class, subject, rooms


async def test_preflight_reports_the_exact_room_shortage(db_session):
    org, school_class, subject, rooms = await _create_gym_scenario(db_session, suffix="shortage")

    issues = await _validate_room_requirements(db_session, org.id)

    assert len(issues) == 1
    issue = issues[0]
    assert issue.code == "NO_ELIGIBLE_ROOM"
    assert issue.severity == "BLOCKER"
    assert issue.route == "/rooms"
    assert issue.context == {
        "class_id": school_class.id,
        "class_name": "TDESP 10",
        "subject_id": subject.id,
        "subject_name": "Treino Desportivo",
        "required_room_type": "gym",
        "required_capacity": 27,
        "max_available_capacity": 26,
        "reason": "INSUFFICIENT_CAPACITY",
    }

    # Raising the largest room unblocks generation without a restart.
    rooms[1].capacity = 27
    await db_session.flush()

    assert await _validate_room_requirements(db_session, org.id) == []


async def test_preflight_room_issues_are_sorted_and_tenant_scoped(db_session):
    blocked_org, _class, _subject, _rooms = await _create_gym_scenario(db_session, suffix="blocked")
    other_org, _healthy_class, _healthy_subject, _healthy_rooms = await _create_gym_scenario(
        db_session,
        suffix="healthy",
        gym_capacities=(40,),
    )

    issues = await _validate_room_requirements(db_session, blocked_org.id)
    assert len(issues) == 1
    assert issues[0].context["class_name"] == "TDESP 10"

    # A different organization with a compatible room reports nothing.
    assert await _validate_room_requirements(db_session, other_org.id) == []


async def test_load_snapshot_carries_public_room_context(db_session):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="room-snapshot-user",
        clerk_org_id="room-snapshot-org",
    )
    seed.room.capacity = 10
    await db_session.flush()

    with pytest.raises(SnapshotConfigurationError) as error:
        await load_snapshot(
            db_session,
            seed.organization.id,
            strategy=SchedulingStrategy.COMPLETE_GENERATION,
            now_utc=MOMENT,
            school_year_id=seed.year.id,
        )

    assert error.value.code == "NO_ELIGIBLE_ROOM"
    assert error.value.public_context["room_issues"] == [
        {
            "class_id": seed.class_.id,
            "class_name": "A",
            "subject_id": seed.subject.id,
            "subject_name": "Subject",
            "required_room_type": "normal",
            "required_capacity": 20,
            "max_available_capacity": 10,
            "reason": "INSUFFICIENT_CAPACITY",
        }
    ]


async def test_preparation_dashboard_embeds_single_prevalidation_snapshot(
    db_session, override_auth_actor
):
    org, user, mem = await _create_org_and_admin(
        db_session, "Dashboard Preflight School", "org_dashboard_preflight"
    )
    override_auth_actor(
        deps.Actor(
            account_id=user.id,
            clerk_user_id=user.clerk_user_id,
            organization_id=org.id,
            membership_id=mem.id,
            can_admin=True,
            can_teach=False,
            teacher_id=None,
        )
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "PREPARATION"
    assert payload["bases"]["fingerprint"] is None
    assert payload["prevalidation"]["fingerprint"] is None


async def test_preflight_blocks_invalid_teacher_assignment_archived_or_unqualified(db_session):
    org, user, mem = await _create_org_and_admin(
        db_session, "Teacher Preflight School", "org_teacher_preflight"
    )

    school_year = models.SchedulerSchoolYear(
        organization_id=org.id,
        label="2025/2026",
        start_date=date(2025, 9, 1),
        hard_end_date=date(2026, 6, 30),
        is_active=True,
    )
    settings = models.OrganizationSettings(
        organization_id=org.id,
        school_start_date=date(2025, 9, 1),
        school_hard_end_date=date(2026, 6, 30),
    )
    timeslot = models.Timeslot(
        organization_id=org.id,
        day_of_week=0,
        start_time=time(8, 30),
        end_time=time(9, 20),
    )
    course = models.Course(
        organization_id=org.id,
        name="Curso Informática",
        abbreviation="TGPSI",
    )
    subject = models.Subject(
        organization_id=org.id,
        name="Programação",
        required_room_type=models.RoomType.normal,
    )
    subject_without_teacher = models.Subject(
        organization_id=org.id,
        name="Redes",
        required_room_type=models.RoomType.normal,
    )
    room = models.Room(
        organization_id=org.id,
        name="Sala A",
        capacity=30,
        type=models.RoomType.normal,
    )
    db_session.add_all(
        [school_year, settings, timeslot, course, subject, subject_without_teacher, room]
    )
    await db_session.flush()

    school_year_state = models.SchedulerSchoolYearState(
        organization_id=org.id,
        school_year_id=school_year.id,
        school_year_publication_state=models.SchoolYearPublicationState.UNPUBLISHED,
        scheduler_state_version=1,
    )
    school_class = models.Class(
        organization_id=org.id,
        course_id=course.id,
        name="10º TGPSI",
        size=20,
        grade_level=10,
        start_year=2025,
        end_year=2028,
    )
    module = models.Module(
        organization_id=org.id,
        subject_id=subject.id,
        name="M1",
        required_minutes=60,
        order=0,
    )
    class_without_teacher = models.Class(
        organization_id=org.id,
        course_id=course.id,
        name="10º Redes",
        size=20,
        grade_level=10,
        start_year=2025,
        end_year=2028,
    )
    module_without_teacher = models.Module(
        organization_id=org.id,
        subject_id=subject_without_teacher.id,
        name="R1",
        required_minutes=60,
        order=0,
    )
    db_session.add_all(
        [school_year_state, school_class, module, class_without_teacher, module_without_teacher]
    )
    await db_session.flush()

    teacher = await create_teacher_profile(
        db_session,
        organization_id=org.id,
        name="Prof. Elegível",
        subject_ids=[subject.id],
    )
    link = models.ClassSubjectLink(
        organization_id=org.id,
        class_id=school_class.id,
        subject_id=subject.id,
        grade_level=10,
        teacher_id=teacher.id,
    )
    missing_teacher_link = models.ClassSubjectLink(
        organization_id=org.id,
        class_id=class_without_teacher.id,
        subject_id=subject_without_teacher.id,
        grade_level=10,
        teacher_id=None,
    )
    avail = models.Availability(
        organization_id=org.id,
        teacher_id=teacher.id,
        timeslot_id=timeslot.id,
        score=models.PreferenceLevel.PREFERRED.value,
    )
    db_session.add_all([link, missing_teacher_link, avail])
    await db_session.flush()
    # Both links start with their module selected so only the teacher rules
    # are under test (the selection is separate evidence).
    await db_session.execute(
        models.class_subject_module.insert(),
        [
            {
                "organization_id": org.id,
                "class_subject_link_id": link.id,
                "module_id": module.id,
            },
            {
                "organization_id": org.id,
                "class_subject_link_id": missing_teacher_link.id,
                "module_id": module_without_teacher.id,
            },
        ],
    )
    await db_session.flush()

    # Step 1: A missing teacher blocks even when another assignment is valid.
    from sqlalchemy import delete, insert

    service = PreflightService(db_session)
    report = await service.evaluate(organization_id=org.id, school_year_id=school_year.id)
    assert report.status == "BLOCKED"
    missing_teacher_issue = next(
        (i for i in report.issues if i.code == "INVALID_TEACHER_ASSIGNMENT"), None
    )
    assert missing_teacher_issue is not None
    assert missing_teacher_issue.severity == "BLOCKER"
    assert "não tem professor atribuído" in missing_teacher_issue.message
    assert missing_teacher_issue.route == (
        f"/courses/{course.id}/classes/{class_without_teacher.id}/subjects"
    )

    # Assign an eligible teacher: the same setup is READY again.
    missing_teacher_link.teacher_id = teacher.id
    await db_session.execute(
        insert(models.teacher_subject_link).values(
            organization_id=org.id,
            teacher_id=teacher.id,
            subject_id=subject_without_teacher.id,
        )
    )
    await db_session.flush()
    report = await service.evaluate(organization_id=org.id, school_year_id=school_year.id)
    assert report.status == "READY"
    assert not any(issue.code == "INVALID_TEACHER_ASSIGNMENT" for issue in report.issues)

    # Step 2: Unqualified teacher triggers BLOCKER with link to class-subject
    await db_session.execute(
        delete(models.teacher_subject_link).where(
            models.teacher_subject_link.c.organization_id == org.id,
            models.teacher_subject_link.c.teacher_id == teacher.id,
            models.teacher_subject_link.c.subject_id == subject.id,
        )
    )
    await db_session.flush()

    report_unqualified = await service.evaluate(
        organization_id=org.id, school_year_id=school_year.id
    )
    assert report_unqualified.status == "BLOCKED"
    blocker_unqualified = next(
        (i for i in report_unqualified.issues if i.code == "INVALID_TEACHER_ASSIGNMENT"), None
    )
    assert blocker_unqualified is not None
    assert blocker_unqualified.severity == "BLOCKER"
    assert blocker_unqualified.route == f"/courses/{course.id}/classes/{school_class.id}/subjects"

    # Restore qualification
    await db_session.execute(
        insert(models.teacher_subject_link).values(
            organization_id=org.id,
            teacher_id=teacher.id,
            subject_id=subject.id,
        )
    )
    await db_session.flush()

    # Step 3: Archived teacher triggers BLOCKER with link to class-subject
    teacher_membership = await db_session.get(
        models.OrganizationMembership, teacher.organization_membership_id
    )
    teacher_membership.lifecycle_status = models.MembershipLifecycleStatus.archived
    await db_session.flush()

    report_archived = await service.evaluate(organization_id=org.id, school_year_id=school_year.id)
    assert report_archived.status == "BLOCKED"
    blocker_archived = next(
        (
            i
            for i in report_archived.issues
            if i.code == "INVALID_TEACHER_ASSIGNMENT"
            and i.route == f"/courses/{course.id}/classes/{school_class.id}/subjects"
        ),
        None,
    )
    assert blocker_archived is not None
    assert blocker_archived.severity == "BLOCKER"
    assert blocker_archived.route == f"/courses/{course.id}/classes/{school_class.id}/subjects"

    # Step 4: Archived teacher is excluded from generator input snapshot
    from app.services.scheduler_fingerprint_service import SchedulerFingerprintService

    fps = SchedulerFingerprintService(db_session)
    snapshot = await fps.generation_input_snapshot(
        organization_id=org.id,
        school_year_id=school_year.id,
        strategy=models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
    )
    snapshot_teacher_ids = {t["id"] for t in snapshot["teachers"]}
    assert teacher.id not in snapshot_teacher_ids

    # Step 5: Restore teacher with scheduler_only mode -> passes preflight
    teacher_membership.lifecycle_status = models.MembershipLifecycleStatus.active
    teacher_membership.teacher_access_mode = models.TeacherAccessMode.scheduler_only
    teacher_membership.can_teach = True
    await db_session.flush()

    report_restored = await service.evaluate(organization_id=org.id, school_year_id=school_year.id)
    assert report_restored.status == "READY"


async def test_teacher_archive_restore_and_qualifications_invalidate_scheduler(db_session):
    from unittest.mock import AsyncMock, MagicMock

    from app.services import member_service

    organization, user, admin_mem = await _create_org_and_admin(
        db_session, "Teacher Inval School", "org_teacher_inval"
    )
    admin_actor = deps.Actor(
        account_id=user.id,
        clerk_user_id=user.clerk_user_id,
        organization_id=organization.id,
        membership_id=admin_mem.id,
        can_admin=True,
        can_teach=False,
        teacher_id=None,
    )

    school_year = models.SchedulerSchoolYear(
        organization_id=organization.id,
        label="2025/2026",
        start_date=date(2025, 9, 1),
        hard_end_date=date(2026, 6, 30),
        is_active=True,
    )
    db_session.add(school_year)
    await db_session.flush()

    school_year_state = models.SchedulerSchoolYearState(
        organization_id=organization.id,
        school_year_id=school_year.id,
        school_year_publication_state=models.SchoolYearPublicationState.UNPUBLISHED,
        scheduler_state_version=1,
    )

    subject1 = models.Subject(organization_id=organization.id, name="Sub1")
    subject2 = models.Subject(organization_id=organization.id, name="Sub2")
    db_session.add_all([school_year_state, subject1, subject2])
    await db_session.flush()

    teacher_account = models.User(
        email="prof.inval@example.com",
        name="Prof. Inval",
    )
    db_session.add(teacher_account)
    await db_session.flush()
    teacher_membership = models.OrganizationMembership(
        organization_id=organization.id,
        account_id=teacher_account.id,
        organization_display_name="Prof. Inval",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.none,
        teacher_access_mode=models.TeacherAccessMode.scheduler_only,
        can_admin=False,
        can_teach=True,
    )
    db_session.add(teacher_membership)
    await db_session.flush()
    teacher = await create_teacher_profile(
        db_session,
        organization_id=organization.id,
        organization_membership_id=teacher_membership.id,
        name="Prof. Inval",
        subject_ids=[subject1.id],
    )
    teacher_membership_id = teacher_membership.id

    course = models.Course(
        organization_id=organization.id,
        name="Curso Invalidação",
        abbreviation="CI",
    )
    db_session.add(course)
    await db_session.flush()
    class_ = models.Class(
        organization_id=organization.id,
        course_id=course.id,
        name="10º CI",
        size=20,
        grade_level=10,
        start_year=2025,
        end_year=2028,
    )
    module = models.Module(
        organization_id=organization.id,
        subject_id=subject1.id,
        name="Módulo Invalidação",
        required_minutes=60,
        order=0,
    )
    db_session.add_all([class_, module])
    await db_session.flush()
    db_session.add(
        models.ClassSubjectLink(
            organization_id=organization.id,
            class_id=class_.id,
            subject_id=subject1.id,
            grade_level=10,
            teacher_id=teacher.id,
        )
    )
    await db_session.flush()

    # Give teacher history so remove_member archives rather than hard-deletes
    db_session.add(
        models.TeacherWeeklyTimesheet(
            organization_id=organization.id,
            teacher_id=teacher.id,
            week_start_date=date(2025, 9, 1),
        )
    )
    await db_session.flush()

    initial_version = school_year_state.scheduler_state_version

    from app.services.member_access_operation_service import MemberAccessOperationService
    from tests._support.db_fixtures import TestingSessionLocal

    mock_clerk = MagicMock()
    mock_clerk.revoke_organization_membership = AsyncMock(return_value=MagicMock(ok=True))
    mock_clerk.get_organization_membership = AsyncMock(return_value=None)
    mock_clerk.create_organization_invitation = AsyncMock(return_value=MagicMock(ok=True))
    mock_clerk.change_membership_role = AsyncMock(return_value=MagicMock(ok=True))
    operation_service = MemberAccessOperationService(TestingSessionLocal, mock_clerk)

    # 1. Archive member -> scheduler state version bumped (pending work is stale)
    await member_service.remove_member(
        db_session,
        member_id=teacher_membership_id,
        organization_id=organization.id,
        current_admin=admin_actor,
        clerk_access=mock_clerk,
        operation_service=operation_service,
    )
    await db_session.refresh(school_year_state)
    assert school_year_state.scheduler_state_version > initial_version

    # 2. Restore member -> scheduler state version bumped again
    v2 = school_year_state.scheduler_state_version
    await member_service.restore_member(
        db_session,
        member_id=teacher_membership_id,
        restore_in=schemas.MemberRestore(
            restore_access=False,
            capabilities=["teacher"],
            teacher_access_mode="scheduler_only",
        ),
        organization_id=organization.id,
        current_admin=admin_actor,
        clerk_access=mock_clerk,
        operation_service=operation_service,
    )
    await db_session.refresh(school_year_state)
    assert school_year_state.scheduler_state_version > v2

    # 3. Update qualifications (add subject2) -> scheduler state version bumped
    v3 = school_year_state.scheduler_state_version
    await member_service.update_member(
        db_session,
        member_id=teacher_membership_id,
        member_in=schemas.MemberUpdate(
            subject_ids=[subject1.id, subject2.id],
        ),
        organization_id=organization.id,
        current_admin=admin_actor,
        clerk_access=mock_clerk,
        operation_service=operation_service,
    )
    await db_session.refresh(school_year_state)
    assert school_year_state.scheduler_state_version > v3


async def _seed_class_availability_preflight(db_session, *, suffix: str):
    org, _user, _mem = await _create_org_and_admin(
        db_session, f"Class Availability {suffix}", f"org_class_availability_{suffix}"
    )
    course = models.Course(organization_id=org.id, name=f"Curso {suffix}", abbreviation="CAV")
    subject = models.Subject(
        organization_id=org.id,
        name=f"Disciplina {suffix}",
        required_room_type=models.RoomType.normal,
    )
    room = models.Room(
        organization_id=org.id,
        name=f"Sala {suffix}",
        capacity=30,
        type=models.RoomType.normal,
    )
    slots = [
        models.Timeslot(
            organization_id=org.id, day_of_week=0, start_time=time(9, 0), end_time=time(9, 50)
        ),
        models.Timeslot(
            organization_id=org.id, day_of_week=1, start_time=time(9, 0), end_time=time(9, 50)
        ),
    ]
    db_session.add_all([course, subject, room, *slots])
    await db_session.flush()
    module = models.Module(
        organization_id=org.id,
        subject_id=subject.id,
        name=f"Módulo {suffix}",
        required_minutes=60,
        order=0,
    )
    db_session.add(module)
    await db_session.flush()
    school_class = models.Class(
        organization_id=org.id,
        course_id=course.id,
        name=f"Turma {suffix}",
        size=20,
        grade_level=10,
        start_year=2025,
        end_year=2028,
    )
    db_session.add(school_class)
    await db_session.flush()
    teacher = await create_teacher_profile(
        db_session, organization_id=org.id, subject_ids=[subject.id]
    )
    link = models.ClassSubjectLink(
        organization_id=org.id,
        class_id=school_class.id,
        subject_id=subject.id,
        grade_level=10,
        teacher_id=teacher.id,
    )
    db_session.add(link)
    await db_session.flush()
    await db_session.execute(
        models.class_subject_module.insert().values(
            organization_id=org.id,
            class_subject_link_id=link.id,
            module_id=module.id,
        )
    )
    await db_session.flush()
    return org, school_class, course, link, slots


async def test_preflight_blocks_class_subject_without_selected_modules(db_session):
    org, _user, _mem = await _create_org_and_admin(
        db_session, "Module Preflight School", "org_module_preflight"
    )
    school_year = models.SchedulerSchoolYear(
        organization_id=org.id,
        label="2025/2026",
        start_date=date(2025, 9, 1),
        hard_end_date=date(2026, 6, 30),
        is_active=True,
    )
    db_session.add(school_year)
    await db_session.flush()
    db_session.add(
        models.SchedulerSchoolYearState(
            organization_id=org.id,
            school_year_id=school_year.id,
            school_year_publication_state=models.SchoolYearPublicationState.UNPUBLISHED,
            scheduler_state_version=1,
        )
    )
    course = models.Course(organization_id=org.id, name="Curso Módulos", abbreviation="CM")
    subject = models.Subject(organization_id=org.id, name="UFCD Programação")
    other_subject = models.Subject(organization_id=org.id, name="UFCD Redes")
    room = models.Room(
        organization_id=org.id,
        name="Sala",
        capacity=30,
        type=models.RoomType.normal,
    )
    db_session.add_all([course, subject, other_subject, room])
    await db_session.flush()
    class_without_teacher = models.Class(
        organization_id=org.id,
        course_id=course.id,
        name="10º CM A",
        size=20,
        grade_level=10,
        start_year=2025,
        end_year=2028,
    )
    class_with_teacher = models.Class(
        organization_id=org.id,
        course_id=course.id,
        name="10º CM B",
        size=20,
        grade_level=10,
        start_year=2025,
        end_year=2028,
    )
    module = models.Module(
        organization_id=org.id,
        subject_id=subject.id,
        name="M1",
        required_minutes=60,
        order=0,
    )
    other_module = models.Module(
        organization_id=org.id,
        subject_id=other_subject.id,
        name="R1",
        required_minutes=60,
        order=0,
    )
    db_session.add_all([class_without_teacher, class_with_teacher, module, other_module])
    await db_session.flush()
    teacher = await create_teacher_profile(
        db_session, organization_id=org.id, subject_ids=[other_subject.id]
    )
    link_without_teacher = models.ClassSubjectLink(
        organization_id=org.id,
        class_id=class_without_teacher.id,
        subject_id=subject.id,
        grade_level=10,
        teacher_id=None,
    )
    link_with_teacher = models.ClassSubjectLink(
        organization_id=org.id,
        class_id=class_with_teacher.id,
        subject_id=other_subject.id,
        grade_level=10,
        teacher_id=teacher.id,
    )
    db_session.add_all([link_without_teacher, link_with_teacher])
    await db_session.flush()

    service = PreflightService(db_session)
    report = await service.evaluate(
        organization_id=org.id,
        school_year_id=school_year.id,
        resolve_fingerprint=False,
    )

    # The blocker follows invalid_assignment_rows (unarchived class, current
    # grade) and applies regardless of teacher assignment.
    blockers = [issue for issue in report.issues if issue.code == "CLASS_SUBJECT_WITHOUT_MODULES"]
    assert len(blockers) == 2
    assert all(issue.severity == "BLOCKER" for issue in blockers)
    without_teacher = next(
        issue for issue in blockers if f"classes/{class_without_teacher.id}/" in issue.route
    )
    assert without_teacher.route == (
        f"/courses/{course.id}/classes/{class_without_teacher.id}/subjects"
    )
    assert without_teacher.message == (
        "A turma 10º CM A tem a disciplina UFCD Programação sem módulos selecionados. "
        "Remova a disciplina ou selecione pelo menos um módulo."
    )
    with_teacher = next(
        issue for issue in blockers if f"classes/{class_with_teacher.id}/" in issue.route
    )
    assert with_teacher.route == (f"/courses/{course.id}/classes/{class_with_teacher.id}/subjects")

    # Selecting a module clears the blocker for that link only.
    await db_session.execute(
        models.class_subject_module.insert().values(
            organization_id=org.id,
            class_subject_link_id=link_without_teacher.id,
            module_id=module.id,
        )
    )
    await db_session.flush()
    report = await service.evaluate(
        organization_id=org.id,
        school_year_id=school_year.id,
        resolve_fingerprint=False,
    )
    remaining = [issue for issue in report.issues if issue.code == "CLASS_SUBJECT_WITHOUT_MODULES"]
    assert len(remaining) == 1
    assert f"classes/{class_with_teacher.id}/" in remaining[0].route


def _class_blocker_routes(report) -> list[str]:
    return [issue.route for issue in report.issues if issue.code == "CLASS_WITHOUT_AVAILABILITY"]


async def test_preflight_blocks_a_class_whose_blocks_are_all_impossible(db_session):
    org, school_class, course, _link, slots = await _seed_class_availability_preflight(
        db_session, suffix="allimpossible"
    )
    for slot in slots:
        db_session.add(
            models.ClassAvailability(
                organization_id=org.id,
                class_id=school_class.id,
                timeslot_id=slot.id,
                score=models.PreferenceLevel.IMPOSSIBLE.value,
            )
        )
    await db_session.flush()

    report = await PreflightService(db_session).evaluate(
        organization_id=org.id, resolve_fingerprint=False
    )

    blockers = [issue for issue in report.issues if issue.code == "CLASS_WITHOUT_AVAILABILITY"]
    assert len(blockers) == 1
    assert blockers[0].severity == "BLOCKER"
    assert blockers[0].message == (
        f"A turma {school_class.name} tem todos os blocos marcados como Impossível. "
        "Marque pelo menos um bloco como Neutro, Evitar ou Preferencial."
    )
    assert blockers[0].route == f"/courses/{course.id}/classes/{school_class.id}"


async def test_preflight_class_availability_requires_every_block_and_an_assigned_teacher(
    db_session,
):
    org, school_class, _course, link, slots = await _seed_class_availability_preflight(
        db_session, suffix="partial"
    )
    for slot in slots:
        db_session.add(
            models.ClassAvailability(
                organization_id=org.id,
                class_id=school_class.id,
                timeslot_id=slot.id,
                score=models.PreferenceLevel.IMPOSSIBLE.value,
            )
        )
    await db_session.flush()

    async def blocker_routes() -> list[str]:
        report = await PreflightService(db_session).evaluate(
            organization_id=org.id, resolve_fingerprint=False
        )
        return _class_blocker_routes(report)

    assert await blocker_routes() == [
        f"/courses/{school_class.course_id}/classes/{school_class.id}"
    ]

    # An archived class keeps its rows but is not a generation input.
    school_class.is_archived = True
    await db_session.flush()
    assert await blocker_routes() == []

    school_class.is_archived = False
    await db_session.flush()

    # A class-subject link without a teacher is not an eligible generation input.
    original_teacher_id = link.teacher_id
    link.teacher_id = None
    await db_session.flush()
    assert await blocker_routes() == []

    link.teacher_id = original_teacher_id
    await db_session.flush()
    assert await blocker_routes() == [
        f"/courses/{school_class.course_id}/classes/{school_class.id}"
    ]

    # A missing row means the block is possible, so the class is no longer blocked.
    await db_session.execute(
        delete(models.ClassAvailability).where(
            models.ClassAvailability.organization_id == org.id,
            models.ClassAvailability.class_id == school_class.id,
            models.ClassAvailability.timeslot_id == slots[0].id,
        )
    )
    await db_session.flush()
    assert await blocker_routes() == []
