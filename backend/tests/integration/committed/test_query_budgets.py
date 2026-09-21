from contextlib import contextmanager
from datetime import date, datetime, time

from sqlalchemy import event

from app import models, schemas
from app.services import (
    dashboard_service,
    member_service,
    occurrence_service,
    schedule_service,
    timesheet_service,
)
from tests._support.db_fixtures import TestingSessionLocal, create_teacher_profile


@contextmanager
def _statement_counter(db):
    statements: list[str] = []
    engine = db.get_bind()

    def record(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


def _teacher(db, organization: models.Organization) -> models.Teacher:
    account = models.User(email="query-budget@test.invalid", name="Query Budget")
    db.add(account)
    db.flush()
    membership = models.OrganizationMembership(
        organization_id=organization.id,
        account_id=account.id,
        organization_display_name="Query Budget",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.none,
        teacher_access_mode=models.TeacherAccessMode.scheduler_only,
        can_admin=False,
        can_teach=True,
    )
    db.add(membership)
    db.flush()
    teacher = models.Teacher(
        organization_id=organization.id,
        organization_membership_id=membership.id,
    )
    db.add(teacher)
    db.flush()
    return teacher


def test_dashboard_uses_at_most_four_statements(sync_db):
    organization = models.Organization(name="Dashboard Budget", plan_status="active")
    sync_db.add(organization)
    sync_db.flush()
    organization_id = organization.id
    sync_db.commit()

    with _statement_counter(sync_db) as statements:
        dashboard_service.get_dashboard_summary_sync(
            sync_db,
            organization_id,
            bases=schemas.BasesReadinessResponse(
                percentage=0,
                depth=0,
                complete=False,
            ),
            prevalidation=schemas.PreflightReport(status="BLOCKED"),
        )

    assert len(statements) <= 4


def test_timesheet_listing_uses_at_most_two_statements(sync_db):
    organization = models.Organization(name="Timesheet Budget", plan_status="active")
    sync_db.add(organization)
    sync_db.flush()
    teacher = _teacher(sync_db, organization)
    week_start = date(2026, 4, 20)
    sync_db.add(
        models.TeacherWeeklyTimesheet(
            organization_id=organization.id,
            teacher_id=teacher.id,
            week_start_date=week_start,
            status=models.TimesheetStatus.OPEN,
        )
    )
    organization_id = organization.id
    sync_db.commit()

    with _statement_counter(sync_db) as statements:
        rows = timesheet_service.list_timesheets_sync(
            sync_db,
            organization_id,
            week_start_date=week_start,
        )

    assert len(rows) == 1
    assert len(statements) <= 2


async def test_teacher_history_detection_uses_one_statement(db_session):
    organization = models.Organization(name="History Budget", plan_status="active")
    db_session.add(organization)
    await db_session.flush()
    teacher = await db_session.run_sync(lambda db: _teacher(db, organization))
    await db_session.commit()
    engine = db_session.get_bind()
    statements: list[str] = []

    def record(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        history = await member_service._teacher_ids_with_history(
            db_session,
            organization.id,
            [teacher.id],
        )
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert history == set()
    assert len(statements) == 1


def test_occurrence_context_uses_one_joined_statement(sync_db):
    organization = models.Organization(name="Occurrence Budget", plan_status="active")
    sync_db.add(organization)
    sync_db.flush()
    organization_id = organization.id
    sync_db.commit()

    with _statement_counter(sync_db) as statements:
        occurrence = occurrence_service._get_occurrence_with_context_sync(
            sync_db,
            occurrence_id=999_999,
            organization_id=organization_id,
        )

    assert occurrence is None
    assert len(statements) == 1


def test_week_schedule_uses_two_statements(sync_db):
    organization = models.Organization(name="Week Budget", plan_status="active")
    sync_db.add(organization)
    sync_db.flush()
    organization_id = organization.id
    sync_db.commit()

    with _statement_counter(sync_db) as statements:
        rows = schedule_service.get_week_schedule_sync(
            sync_db,
            organization_id,
            week_start=date(2026, 4, 20),
            teacher_id=999_999,
        )

    assert rows == []
    assert len(statements) == 2


async def test_async_dashboard_summary_uses_bounded_statements(db_session):
    organization = models.Organization(
        name="Dashboard Async Budget",
        plan_status="active",
        first_real_schedule_approved_at=None,
    )
    db_session.add(organization)
    await db_session.flush()

    engine = db_session.get_bind()
    statements: list[str] = []

    def record(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        summary = await dashboard_service.get_dashboard_summary(
            db_session,
            organization.id,
        )
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert summary.bases is not None
    assert summary.bases.fingerprint is None
    assert summary.prevalidation is not None
    assert summary.prevalidation.fingerprint is None
    # Ensure fingerprint generation is excluded and queries remain strictly bounded
    assert len(statements) <= 20


async def test_populated_dashboard_skips_fingerprints_with_bounded_queries(db_session, monkeypatch):
    organization = models.Organization(
        name="Populated Dashboard Budget",
        plan_status="active",
        foundation_status=models.OrganizationFoundationStatus.COMPLETED,
        foundation_completed_at=datetime(2026, 1, 1),
        first_real_schedule_approved_at=None,
    )
    db_session.add(organization)
    await db_session.flush()
    db_session.add_all(
        [
            models.OrganizationSettings(
                organization_id=organization.id,
                school_start_date=date(2025, 9, 1),
                school_hard_end_date=date(2026, 6, 30),
            ),
            models.SchedulerSchoolYear(
                organization_id=organization.id,
                label="2025/2026",
                start_date=date(2025, 9, 1),
                hard_end_date=date(2026, 6, 30),
                is_active=True,
            ),
            models.Timeslot(
                organization_id=organization.id,
                day_of_week=0,
                start_time=time(8, 30),
                end_time=time(9, 20),
            ),
        ]
    )
    course = models.Course(
        organization_id=organization.id,
        name="Curso Populado",
        abbreviation="CP",
    )
    subject = models.Subject(
        organization_id=organization.id,
        name="Disciplina Populada",
        required_room_type=models.RoomType.normal,
    )
    room = models.Room(
        organization_id=organization.id,
        name="Sala Populada",
        type=models.RoomType.normal,
        capacity=30,
    )
    db_session.add_all([course, subject, room])
    await db_session.flush()
    db_session.add(
        models.Module(
            organization_id=organization.id,
            subject_id=subject.id,
            name="Módulo Populado",
            required_minutes=60,
            order=0,
        )
    )

    teachers = []
    classes = []
    links = []
    for index in range(12):
        teacher = await create_teacher_profile(
            db_session,
            organization_id=organization.id,
            name=f"Professor {index}",
            subject_ids=[subject.id],
        )
        school_class = models.Class(
            organization_id=organization.id,
            course_id=course.id,
            name=f"Turma {index}",
            size=20,
            grade_level=10,
            start_year=2025,
            end_year=2028,
        )
        db_session.add(school_class)
        await db_session.flush()
        teachers.append(teacher)
        classes.append(school_class)
        links.append(
            models.ClassSubjectLink(
                organization_id=organization.id,
                class_id=school_class.id,
                subject_id=subject.id,
                grade_level=10,
                teacher_id=teacher.id,
            )
        )
    db_session.add_all(links)
    await db_session.commit()

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("dashboard readiness must not calculate fingerprints")

    monkeypatch.setattr(
        "app.services.scheduler_fingerprint_service.SchedulerFingerprintService.generation_input_fingerprint",
        fail_if_called,
    )

    async with TestingSessionLocal() as fresh_session:
        statements: list[str] = []
        engine = fresh_session.get_bind()

        def record(_connection, _cursor, statement, _parameters, _context, _many):
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", record)
        try:
            summary = await dashboard_service.get_dashboard_summary(
                fresh_session,
                organization.id,
            )
        finally:
            event.remove(engine, "before_cursor_execute", record)

    assert summary.bases is not None
    assert summary.bases.complete is True
    assert summary.bases.depth == 6
    assert summary.prevalidation is not None
    assert summary.prevalidation.status == "READY"
    assert summary.bases.fingerprint is None
    assert summary.prevalidation.fingerprint is None
    assert len(statements) <= 20
