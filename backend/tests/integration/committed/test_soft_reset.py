from sqlalchemy import func, select

from app import models
from app.config import settings

RESET_URL = f"{settings.API_V1_STR}/school/settings/soft-reset"
CONFIRMATION = {"confirm_phrase": "Confirmo"}


async def test_soft_reset_admin_success(async_client, clerk_admin_headers):
    response = await async_client.post(
        RESET_URL,
        json=CONFIRMATION,
        headers=clerk_admin_headers,
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Soft-reset efetuado com sucesso."}


async def test_soft_reset_denies_non_admin(async_client, clerk_teacher_headers):
    response = await async_client.post(
        RESET_URL,
        json=CONFIRMATION,
        headers=clerk_teacher_headers,
    )

    assert response.status_code == 403


async def test_soft_reset_reverses_progress_without_mutating_history(
    async_client,
    clerk_admin_headers,
    db_session,
):
    organization = await db_session.scalar(
        select(models.Organization).where(models.Organization.clerk_org_id == "org_test_001")
    )
    membership = await db_session.scalar(
        select(models.OrganizationMembership)
        .join(models.User, models.User.id == models.OrganizationMembership.account_id)
        .where(
            models.OrganizationMembership.organization_id == organization.id,
            models.User.clerk_user_id == "user_admin_001",
        )
    )
    course = models.Course(
        organization_id=organization.id,
        name="Reset Course",
        abbreviation="RST",
    )
    subject = models.Subject(
        organization_id=organization.id,
        name="Reset Subject",
        required_room_type=models.RoomType.normal,
    )
    db_session.add_all([course, subject])
    await db_session.flush()
    class_ = models.Class(
        organization_id=organization.id,
        name="Reset Class",
        size=20,
        start_year=2025,
        end_year=2026,
        grade_level=10,
        course_id=course.id,
    )
    module = models.Module(
        organization_id=organization.id,
        subject_id=subject.id,
        name="Reset Module",
        code="RST-1",
        required_minutes=120,
        order=0,
    )
    db_session.add_all([class_, module])
    await db_session.flush()
    original = models.ProgressLedgerEntry(
        organization_id=organization.id,
        source_type="lesson_log",
        source_id=1,
        class_id=class_.id,
        module_id=module.id,
        completed_minutes_delta=75,
        debt_minutes_delta=15,
        idempotency_key="reset-test-original",
        created_by_membership_id=membership.id,
    )
    db_session.add(original)
    await db_session.commit()

    response = await async_client.post(
        RESET_URL,
        json=CONFIRMATION,
        headers=clerk_admin_headers,
    )

    assert response.status_code == 200, response.text
    db_session.expire_all()
    entries = list(
        await db_session.scalars(
            select(models.ProgressLedgerEntry).order_by(models.ProgressLedgerEntry.id)
        )
    )
    assert len(entries) == 2
    assert entries[0].completed_minutes_delta == 75
    assert entries[0].debt_minutes_delta == 15
    totals = await db_session.execute(
        select(
            func.sum(models.ProgressLedgerEntry.completed_minutes_delta),
            func.sum(models.ProgressLedgerEntry.debt_minutes_delta),
        )
    )
    assert totals.one() == (0, 0)
