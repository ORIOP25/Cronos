"""Prevalidation uses the same strategy as the requested schedule operation."""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select

from app import models, schemas
from app.scheduler.domain.demand import ExecutionEntry, ModuleCredit
from app.scheduler.infrastructure.models import SchedulerLessonSliceV1
from app.scheduler.infrastructure.progress import record_execution
from app.services.preflight_service import PreflightService
from tests._support.scheduler_v1 import MOMENT, add_lesson, add_version, seed_generatable_school

pytestmark = pytest.mark.postgresql


@pytest.mark.parametrize("strategy", ["COMPLETE_GENERATION", "ADAPTIVE_REPAIR"])
async def test_prevalidation_uses_requested_strategy(
    async_client, db_session, monkeypatch, strategy
):
    seed = await seed_generatable_school(
        db_session, clerk_user_id="readiness-strategy-admin", clerk_org_id="readiness-strategy-org"
    )
    await db_session.commit()
    evaluate = AsyncMock(
        return_value=schemas.PreflightReport(status="READY", fingerprint=None, issues=[])
    )
    monkeypatch.setattr(PreflightService, "evaluate", evaluate)

    response = await async_client.get(
        "/api/v1/readiness/prevalidation",
        params={"strategy": strategy},
        headers={"Authorization": "Bearer readiness-strategy-admin"},
    )

    assert response.status_code == 200
    evaluate.assert_awaited_once_with(
        organization_id=seed.organization.id,
        school_year_id=seed.year.id,
        strategy=models.ScheduleGenerationStrategy(strategy),
    )


@pytest.mark.parametrize("demand", ["protected", "executed", "editable"])
async def test_adaptive_preflight_presence_exempts_teachers_without_editable_demand(
    db_session, monkeypatch, demand
):
    monkeypatch.setattr(
        "app.services.preflight_service.datetime", Mock(now=Mock(return_value=MOMENT))
    )
    monkeypatch.setattr(
        "app.services.scheduler_fingerprint_service.datetime", Mock(now=Mock(return_value=MOMENT))
    )
    monkeypatch.setattr(
        "app.services.grid_version_service.school_today", AsyncMock(return_value=MOMENT.date())
    )
    seed = await seed_generatable_school(db_session, module_minutes=50)
    teacher = await db_session.get(models.Teacher, seed.assignment.teacher_id)
    teacher.minimum_presence_hours = 12
    teacher.maximum_presence_gap_hours = 1
    teacher.lunch_required = False
    db_session.add(
        models.OrganizationSettings(
            organization_id=seed.organization.id,
            school_start_date=seed.year.start_date,
            school_hard_end_date=seed.year.hard_end_date,
        )
    )
    await db_session.execute(
        models.teacher_subject_link.insert().values(
            organization_id=seed.organization.id,
            teacher_id=teacher.id,
            subject_id=seed.subject.id,
        )
    )
    slots = (
        await db_session.scalars(
            select(models.Timeslot).where(
                models.Timeslot.organization_id == seed.organization.id,
            )
        )
    ).all()
    db_session.add_all(
        models.Availability(
            organization_id=seed.organization.id,
            teacher_id=teacher.id,
            timeslot_id=slot.id,
            score=models.PreferenceLevel.NEUTRAL.value,
        )
        for slot in slots
    )
    version = await add_version(db_session, seed)
    seed.state.active_schedule_version_id = str(version.id)
    seed.state.school_year_publication_state = models.SchoolYearPublicationState.PUBLISHED
    if demand == "protected":
        lesson = await add_lesson(
            db_session,
            seed,
            version,
            stable_key="1",
            school_date=date(2026, 9, 1),
            start=datetime(2026, 9, 1, 8, tzinfo=UTC),
            end=datetime(2026, 9, 1, 8, 50, tzinfo=UTC),
        )
        lesson.teaching_unit_key = f"A:{seed.assignment.id}"
        db_session.add(
            SchedulerLessonSliceV1(
                organization_id=seed.organization.id,
                school_year_id=seed.year.id,
                lesson_id=lesson.id,
                module_id=seed.module.id,
                offset_minutes=0,
                minutes=50,
            )
        )
    elif demand == "executed":
        await record_execution(
            db_session,
            seed.organization.id,
            seed.year.id,
            seed.assignment.id,
            ExecutionEntry(
                "presence-completed",
                1,
                seed.membership.id,
                "Completed",
                (ModuleCredit(seed.module.id, 50),),
                recorded_at=MOMENT,
            ),
            planning_relevant=False,
        )
    await db_session.commit()

    report = await PreflightService(db_session).evaluate(
        organization_id=seed.organization.id,
        school_year_id=seed.year.id,
        strategy=models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR,
        resolve_fingerprint=False,
    )

    blockers = {issue.code for issue in report.issues if issue.severity == "BLOCKER"}
    assert blockers == ({"TEACHER_PRESENCE_IMPOSSIBLE"} if demand == "editable" else set())
