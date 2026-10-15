from contextlib import contextmanager
from datetime import UTC, date, datetime, time

from sqlalchemy import event

from app import models, schemas
from app.scheduler.domain.demand import ExecutionEntry, ModuleCredit
from app.scheduler.infrastructure.models import SchedulerLessonLogV1
from app.scheduler.infrastructure.operations import week_schedule
from app.scheduler.infrastructure.progress import record_execution
from app.services import (
    dashboard_service,
    member_service,
    timesheet_service,
)
from tests._support.db_fixtures import TestingSessionLocal, create_teacher_profile
from tests._support.scheduler_v1 import add_lesson, add_version, lesson_interval, seed_v1_assignment


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
            debt_summary=schemas.DebtSummary(as_of_date=date(2026, 4, 20)),
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
    # Roster, active-v1 lookup and slot counts: the v1 ledger requires one
    # extra indexed lookup over the legacy-only path.
    assert len(statements) <= 3


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


async def test_week_schedule_without_a_published_year_uses_one_statement(db_session):
    organization = models.Organization(name="Week Budget", plan_status="active")
    db_session.add(organization)
    await db_session.flush()
    organization_id = organization.id
    await db_session.commit()

    with _statement_counter(db_session) as statements:
        rows = await week_schedule(
            db_session,
            organization_id,
            week_start=date(2026, 4, 20),
            class_id=None,
            teacher_id=999_999,
        )

    assert rows is None
    assert len(statements) == 1


async def test_dashboard_overview_counts_pending_v1_occurrences(db_session):
    seed = await seed_v1_assignment(db_session)
    version = await add_version(db_session, seed)
    today = date(2026, 9, 22)
    for index, (day, decision) in enumerate(
        ((today, None), (today, "GAP"), (date(2026, 9, 21), None))
    ):
        start, end = lesson_interval(day, 9 + index)
        lesson = await add_lesson(
            db_session,
            seed,
            version,
            stable_key=f"alert-{index}",
            school_date=day,
            start=start,
            end=end,
        )
        db_session.add(
            SchedulerLessonLogV1(
                organization_id=seed.organization.id,
                school_year_id=seed.year.id,
                lesson_id=lesson.id,
                status="OCCURRENCE",
                decision=decision,
                decided_at=end if decision else None,
                decided_by_membership_id=seed.membership.id if decision else None,
                logged_by_membership_id=seed.membership.id,
                logged_at=end,
                created_at=end,
                updated_at=end,
            )
        )
    await db_session.commit()

    alerts, _, _, _ = await db_session.run_sync(
        lambda db: dashboard_service._get_overview(db, seed.organization.id, today)
    )

    assert alerts.pending_occurrences_today == 1
    assert alerts.pending_occurrences_total == 2


async def test_dashboard_class_progress_uses_v1_execution_credits(db_session):
    seed = await seed_v1_assignment(db_session, module_minutes=120)
    await record_execution(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        ExecutionEntry(
            "dashboard:lesson",
            1,
            seed.membership.id,
            "Confirmed",
            (ModuleCredit(seed.module.id, 60),),
            recorded_at=datetime(2026, 9, 22, 12, tzinfo=UTC),
        ),
        planning_relevant=False,
    )
    db_session.add(
        models.ProgressLedgerEntry(
            organization_id=seed.organization.id,
            source_type="MANUAL_ADJUSTMENT",
            source_id=seed.class_.id,
            class_id=seed.class_.id,
            module_id=seed.module.id,
            completed_minutes_delta=600,
            debt_minutes_delta=0,
            idempotency_key="retired-progress",
        )
    )
    await db_session.commit()

    progress = await db_session.run_sync(
        lambda db: dashboard_service._get_class_progress(db, seed.organization.id)
    )

    assert len(progress) == 1
    assert progress[0].class_id == seed.class_.id
    assert progress[0].completed_hours == 1.0
    assert progress[0].total_hours == 2.0
    assert progress[0].overall_percentage == 50.0


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
    module = models.Module(
        organization_id=organization.id,
        subject_id=subject.id,
        name="Módulo Populado",
        required_minutes=60,
        order=0,
    )
    db_session.add(module)

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
    await db_session.execute(
        models.class_subject_module.insert().values(
            [
                {
                    "organization_id": organization.id,
                    "class_subject_link_id": link.id,
                    "module_id": module.id,
                }
                for link in links
            ]
        )
    )
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
    # Room prevalidation adds two constant set queries (rooms and rules); the
    # budget stays bounded and independent of the number of assignments.
    assert len(statements) <= 22
