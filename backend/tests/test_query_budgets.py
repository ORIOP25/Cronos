from contextlib import contextmanager
from datetime import date

from sqlalchemy import event

from app import models, schemas
from app.services import (
    dashboard_service,
    member_service,
    occurrence_service,
    schedule_service,
    timesheet_service,
)


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
