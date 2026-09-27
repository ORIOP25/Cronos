from datetime import UTC, date, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import models
from app.api import deps
from app.main import app
from tests._support.db_fixtures import accept_current_legal_documents

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


async def _prepare_org(db_session):
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
    db_session.add(class_)
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
    return org, class_, actor


async def test_internship_flow_endpoint_lifecycle(db_session, override_auth_actor):
    org, class_, actor = await _prepare_org(db_session)
    override_auth_actor(actor)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        preview = await ac.post(
            "/api/v1/school/calendar-events/preview",
            json={
                "operation": "create",
                "name": "Estágio 10A",
                "start_date": FLOW_START.isoformat(),
                "end_date": FLOW_END.isoformat(),
                "class_ids": [class_.id],
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
                "class_ids": [class_.id],
            },
        )
        assert created.status_code == 200
        assert created.json()["class_ids"] == [class_.id]
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


async def test_flow_endpoint_maps_validation_and_missing_event(db_session, override_auth_actor):
    org, class_, actor = await _prepare_org(db_session)
    override_auth_actor(actor)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        outside = await ac.post(
            "/api/v1/school/calendar-events/",
            json={
                "name": "Fora do período",
                "start_date": "2025-01-01",
                "end_date": "2025-01-05",
                "event_type": "internship_flow",
                "class_ids": [class_.id],
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
