from datetime import UTC, date, datetime
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy import select

from app import models
from app.services import timesheet_service
from tests._support.db_fixtures import create_teacher_profile

WEEK_START = date(2026, 4, 20)


async def test_admin_weekly_list_includes_never_signed_in_scheduler_teacher(
    async_client: AsyncClient,
    clerk_admin_headers: dict,
    db_session,
):
    organization = await db_session.scalar(
        select(models.Organization).where(models.Organization.clerk_org_id == "org_test_001")
    )
    teacher = await create_teacher_profile(
        db_session,
        organization_id=organization.id,
        name="Scheduler Only Teacher",
    )
    await db_session.commit()

    response = await async_client.get(
        "/api/v1/timesheets/",
        params={"week_start_date": WEEK_START.isoformat()},
        headers=clerk_admin_headers,
    )

    assert response.status_code == 200
    rows = response.json()
    row = next(item for item in rows if item["teacher_id"] == teacher.id)
    assert row["status"] == "OPEN"
    assert row["id"] is None
    assert row["created_at"] is None

    persisted = await db_session.scalar(
        select(models.TeacherWeeklyTimesheet).where(
            models.TeacherWeeklyTimesheet.organization_id == organization.id,
            models.TeacherWeeklyTimesheet.teacher_id == teacher.id,
            models.TeacherWeeklyTimesheet.week_start_date == WEEK_START,
        )
    )
    assert persisted is None


def _create_teacher(
    db,
    organization: models.Organization,
    name: str,
    *,
    lifecycle_status: models.MembershipLifecycleStatus = models.MembershipLifecycleStatus.active,
    can_teach: bool = True,
) -> models.Teacher:
    account = models.User(
        email=f"{uuid4().hex}@timesheets.test.invalid",
        name=name,
    )
    db.add(account)
    db.flush()
    membership = models.OrganizationMembership(
        organization_id=organization.id,
        account_id=account.id,
        organization_display_name=name,
        lifecycle_status=lifecycle_status,
        access_status=models.MembershipAccessStatus.none,
        teacher_access_mode=(models.TeacherAccessMode.scheduler_only if can_teach else None),
        can_admin=not can_teach,
        can_teach=can_teach,
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


def _create_admin_membership(
    db, organization: models.Organization
) -> models.OrganizationMembership:
    account = models.User(
        email=f"{uuid4().hex}@timesheets.test.invalid",
        name="Timesheet Approver",
    )
    db.add(account)
    db.flush()
    membership = models.OrganizationMembership(
        organization_id=organization.id,
        account_id=account.id,
        organization_display_name="Timesheet Approver",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.active,
        can_admin=True,
        can_teach=False,
    )
    db.add(membership)
    db.flush()
    return membership


def test_weekly_listing_uses_active_teacher_roster_and_status_filters(sync_db):
    organization = models.Organization(name="Timesheet Roster", plan_status="active")
    other_organization = models.Organization(name="Other Organization", plan_status="active")
    sync_db.add_all([organization, other_organization])
    sync_db.flush()

    virtual_teacher = _create_teacher(sync_db, organization, "Virtual Teacher")
    open_teacher = _create_teacher(sync_db, organization, "Persisted Open Teacher")
    submitted_teacher = _create_teacher(sync_db, organization, "Submitted Teacher")
    approved_teacher = _create_teacher(sync_db, organization, "Approved Teacher")
    archived_teacher = _create_teacher(
        sync_db,
        organization,
        "Archived Teacher",
        lifecycle_status=models.MembershipLifecycleStatus.archived,
    )
    non_teacher = _create_teacher(
        sync_db,
        organization,
        "Active Non Teacher",
        can_teach=False,
    )
    other_teacher = _create_teacher(sync_db, other_organization, "Other Organization Teacher")
    approver = _create_admin_membership(sync_db, organization)
    submitted_at = datetime(2026, 4, 25, 12, tzinfo=UTC)
    approved_at = datetime(2026, 4, 26, 12, tzinfo=UTC)

    persisted_open = models.TeacherWeeklyTimesheet(
        organization_id=organization.id,
        teacher_id=open_teacher.id,
        week_start_date=WEEK_START,
        status=models.TimesheetStatus.OPEN,
    )
    persisted_submitted = models.TeacherWeeklyTimesheet(
        organization_id=organization.id,
        teacher_id=submitted_teacher.id,
        week_start_date=WEEK_START,
        status=models.TimesheetStatus.SUBMITTED,
        submitted_at=submitted_at,
    )
    persisted_approved = models.TeacherWeeklyTimesheet(
        organization_id=organization.id,
        teacher_id=approved_teacher.id,
        week_start_date=WEEK_START,
        status=models.TimesheetStatus.APPROVED,
        submitted_at=submitted_at,
        approved_at=approved_at,
        approved_by_membership_id=approver.id,
    )
    sync_db.add_all(
        [
            persisted_open,
            persisted_submitted,
            persisted_approved,
            models.TeacherWeeklyTimesheet(
                organization_id=organization.id,
                teacher_id=archived_teacher.id,
                week_start_date=WEEK_START,
                status=models.TimesheetStatus.SUBMITTED,
            ),
            models.TeacherWeeklyTimesheet(
                organization_id=organization.id,
                teacher_id=non_teacher.id,
                week_start_date=WEEK_START,
                status=models.TimesheetStatus.SUBMITTED,
            ),
            models.TeacherWeeklyTimesheet(
                organization_id=other_organization.id,
                teacher_id=other_teacher.id,
                week_start_date=WEEK_START,
                status=models.TimesheetStatus.SUBMITTED,
            ),
        ]
    )
    sync_db.commit()

    rows = timesheet_service.list_timesheets_sync(
        sync_db,
        organization.id,
        week_start_date=WEEK_START,
    )
    by_teacher = {row["teacher_id"]: row for row in rows}

    assert set(by_teacher) == {
        virtual_teacher.id,
        open_teacher.id,
        submitted_teacher.id,
        approved_teacher.id,
    }
    assert by_teacher[virtual_teacher.id]["status"] == models.TimesheetStatus.OPEN
    assert by_teacher[virtual_teacher.id]["id"] is None
    assert by_teacher[virtual_teacher.id]["created_at"] is None

    open_row = by_teacher[open_teacher.id]
    assert open_row["id"] == persisted_open.id
    assert open_row["created_at"] == persisted_open.created_at
    assert open_row["status"] == models.TimesheetStatus.OPEN

    submitted = by_teacher[submitted_teacher.id]
    assert submitted["status"] == models.TimesheetStatus.SUBMITTED
    assert submitted["id"] == persisted_submitted.id
    assert submitted["submitted_at"] == submitted_at
    assert submitted["created_at"] == persisted_submitted.created_at

    approved = by_teacher[approved_teacher.id]
    assert approved["status"] == models.TimesheetStatus.APPROVED
    assert approved["id"] == persisted_approved.id
    assert approved["submitted_at"] == submitted_at
    assert approved["approved_at"] == approved_at
    assert approved["approved_by_membership_id"] == approver.id
    assert approved["created_at"] == persisted_approved.created_at

    assert {
        row["teacher_id"]
        for row in timesheet_service.list_timesheets_sync(
            sync_db,
            organization.id,
            week_start_date=WEEK_START,
            status=models.TimesheetStatus.OPEN,
        )
    } == {virtual_teacher.id, open_teacher.id}
    assert {
        row["teacher_id"]
        for row in timesheet_service.list_timesheets_sync(
            sync_db,
            organization.id,
            week_start_date=WEEK_START,
            status=models.TimesheetStatus.SUBMITTED,
        )
    } == {submitted_teacher.id}
    assert {
        row["teacher_id"]
        for row in timesheet_service.list_timesheets_sync(
            sync_db,
            organization.id,
            week_start_date=WEEK_START,
            status=models.TimesheetStatus.APPROVED,
        )
    } == {approved_teacher.id}

    historical_rows = timesheet_service.list_timesheets_sync(sync_db, organization.id)
    assert {row["teacher_id"] for row in historical_rows} == {
        open_teacher.id,
        submitted_teacher.id,
        approved_teacher.id,
        archived_teacher.id,
        non_teacher.id,
    }
