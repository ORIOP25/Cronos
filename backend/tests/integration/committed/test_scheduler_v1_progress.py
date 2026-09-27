import asyncio
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select

from app import models
from app.scheduler.domain.debt import DebtOrigin
from app.scheduler.domain.demand import ExecutionEntry, ModuleCredit
from app.scheduler.infrastructure.models import (
    CurricularAssignment,
    CurricularDebtSettlement,
    CurricularExecution,
    CurricularExecutionCredit,
    CurricularRequirement,
)
from app.scheduler.infrastructure.progress import record_debt, record_execution
from tests._support.db_fixtures import (
    TestingSessionLocal,
    create_completed_organization,
    create_teacher_profile,
)

pytestmark = pytest.mark.postgresql


@pytest.mark.asyncio
async def test_w02_execution_replay_and_invalid_adjustment_preserve_revisions(db_session):
    organization, user = await create_completed_organization(
        db_session, clerk_user_id="w02_progress_admin", clerk_org_id="w02_progress_org"
    )
    membership = await db_session.scalar(
        select(models.OrganizationMembership).where(
            models.OrganizationMembership.organization_id == organization.id,
            models.OrganizationMembership.account_id == user.id,
        )
    )
    course = models.Course(name="Course", abbreviation="C", organization_id=organization.id)
    subject = models.Subject(name="Subject", organization_id=organization.id)
    year = models.SchedulerSchoolYear(
        organization_id=organization.id,
        label="2026/27",
        start_date=date(2026, 9, 1),
        hard_end_date=date(2027, 7, 31),
    )
    db_session.add_all((course, subject, year))
    await db_session.flush()
    class_ = models.Class(
        name="A",
        size=20,
        start_year=2026,
        end_year=2029,
        grade_level=10,
        course_id=course.id,
        organization_id=organization.id,
    )
    module = models.Module(
        organization_id=organization.id,
        subject_id=subject.id,
        name="Module",
        required_minutes=150,
        order=1,
    )
    db_session.add_all((class_, module))
    await db_session.flush()
    teacher = await create_teacher_profile(db_session, organization_id=organization.id)
    assignment = CurricularAssignment(
        organization_id=organization.id,
        school_year_id=year.id,
        class_id=class_.id,
        subject_id=subject.id,
        teacher_id=teacher.id,
    )
    state = models.SchedulerSchoolYearState(
        organization_id=organization.id,
        school_year_id=year.id,
        school_year_publication_state=models.SchoolYearPublicationState.UNPUBLISHED,
        scheduler_state_version=0,
        lock_version=0,
    )
    db_session.add_all((assignment, state))
    await db_session.flush()
    db_session.add(
        CurricularRequirement(
            organization_id=organization.id,
            assignment_id=assignment.id,
            module_id=module.id,
            sequence=1,
            required_minutes=150,
        )
    )
    await db_session.flush()

    timestamp = datetime(2026, 9, 23, 12, tzinfo=UTC)
    lesson = ExecutionEntry(
        "lesson:1",
        1,
        membership.id,
        "Confirmed",
        (ModuleCredit(module.id, 50),),
        recorded_at=timestamp,
    )
    first_id = await record_execution(
        db_session, organization.id, year.id, assignment.id, lesson, planning_relevant=False
    )
    replay_id = await record_execution(
        db_session, organization.id, year.id, assignment.id, lesson, planning_relevant=False
    )
    with pytest.raises(ValueError, match="Conflicting replay"):
        await record_execution(
            db_session, organization.id, year.id, assignment.id, lesson, planning_relevant=True
        )
    adjustment = ExecutionEntry(
        "manual:1",
        1,
        membership.id,
        "Correction",
        (ModuleCredit(module.id, 50),),
        recorded_at=timestamp,
    )
    await record_execution(
        db_session, organization.id, year.id, assignment.id, adjustment, planning_relevant=True
    )
    before_invalid = (state.input_revision, state.planning_revision)
    with pytest.raises(ValueError, match="outside the module"):
        await record_execution(
            db_session,
            organization.id,
            year.id,
            assignment.id,
            ExecutionEntry(
                "manual:2",
                1,
                membership.id,
                "Too much",
                (ModuleCredit(module.id, 51),),
                recorded_at=timestamp,
            ),
            planning_relevant=True,
        )

    executions = (await db_session.scalars(select(CurricularExecution))).all()
    credits = (await db_session.scalars(select(CurricularExecutionCredit))).all()
    assert first_id == replay_id
    assert len(executions) == len(credits) == 2
    assert [credit.offset_minutes for credit in credits] == [0, 50]
    assert before_invalid == (2, 1)
    assert (state.input_revision, state.planning_revision) == before_invalid

    await db_session.commit()

    async def submit(origin: str) -> int:
        async with TestingSessionLocal.begin() as session:
            return await record_execution(
                session,
                organization.id,
                year.id,
                assignment.id,
                ExecutionEntry(
                    origin,
                    1,
                    membership.id,
                    "Concurrent correction",
                    (ModuleCredit(module.id, 25),),
                    recorded_at=timestamp,
                ),
                planning_relevant=True,
            )

    repeated = await asyncio.gather(submit("manual:3"), submit("manual:3"))
    assert repeated[0] == repeated[1]

    competing = await asyncio.gather(submit("manual:4"), submit("manual:5"), return_exceptions=True)
    assert sum(type(result) is int for result in competing) == 1
    assert sum(isinstance(result, ValueError) for result in competing) == 1

    async with TestingSessionLocal() as session:
        refreshed = await session.get(models.SchedulerSchoolYearState, state.id)
        final_credits = (await session.scalars(select(CurricularExecutionCredit))).all()
    assert (refreshed.input_revision, refreshed.planning_revision) == (4, 3)
    assert sum(credit.delta_minutes for credit in final_credits) == 150

    async with TestingSessionLocal.begin() as session:
        reversal_id = await record_execution(
            session,
            organization.id,
            year.id,
            assignment.id,
            ExecutionEntry(
                "manual:3",
                2,
                membership.id,
                "Reverse correction",
                (ModuleCredit(module.id, -25),),
                reversal_of=("manual:3", 1),
                recorded_at=timestamp,
            ),
            planning_relevant=True,
        )
    async with TestingSessionLocal() as session:
        original_credit = await session.scalar(
            select(CurricularExecutionCredit).where(
                CurricularExecutionCredit.execution_id == repeated[0]
            )
        )
        reversal_credit = await session.scalar(
            select(CurricularExecutionCredit).where(
                CurricularExecutionCredit.execution_id == reversal_id
            )
        )
    assert reversal_credit.offset_minutes == original_credit.offset_minutes

    async with TestingSessionLocal.begin() as session:
        first_debt_id = await record_debt(
            session,
            organization.id,
            year.id,
            assignment.id,
            DebtOrigin(
                "occurrence:9",
                1,
                date(2026, 9, 22),
                10,
                membership.id,
                "Missed lesson",
                recorded_at=timestamp,
            ),
        )

    second_origin = DebtOrigin(
        "occurrence:10",
        1,
        date(2026, 9, 23),
        15,
        membership.id,
        "Missed lesson",
        recorded_at=timestamp,
    )

    async def submit_debt(origin: DebtOrigin) -> int:
        async with TestingSessionLocal.begin() as session:
            return await record_debt(session, organization.id, year.id, assignment.id, origin)

    repeated_debt = await asyncio.gather(submit_debt(second_origin), submit_debt(second_origin))
    assert repeated_debt[0] == repeated_debt[1]
    second_debt_id = repeated_debt[0]
    with pytest.raises(ValueError, match="Open debt exceeds residual"):
        await submit_debt(
            DebtOrigin(
                "occurrence:11",
                1,
                date(2026, 9, 24),
                1,
                membership.id,
                "Extra debt",
                recorded_at=timestamp,
            )
        )

    final_adjustment = ExecutionEntry(
        "manual:6",
        1,
        membership.id,
        "Settle missed lesson",
        (ModuleCredit(module.id, 20),),
        recorded_at=timestamp,
    )
    with pytest.raises(ValueError, match="Open debt exceeds residual"):
        async with TestingSessionLocal.begin() as session:
            await record_execution(
                session,
                organization.id,
                year.id,
                assignment.id,
                final_adjustment,
                planning_relevant=True,
                settlements=(),
            )

    async with TestingSessionLocal.begin() as session:
        settled_id = await record_execution(
            session,
            organization.id,
            year.id,
            assignment.id,
            final_adjustment,
            planning_relevant=True,
        )
    async with TestingSessionLocal.begin() as session:
        replay_settled_id = await record_execution(
            session,
            organization.id,
            year.id,
            assignment.id,
            final_adjustment,
            planning_relevant=True,
        )
    last_adjustment = ExecutionEntry(
        "manual:7",
        1,
        membership.id,
        "Finish recovery",
        (ModuleCredit(module.id, 5),),
        recorded_at=timestamp,
    )
    async with TestingSessionLocal.begin() as session:
        await record_execution(
            session,
            organization.id,
            year.id,
            assignment.id,
            last_adjustment,
            planning_relevant=True,
        )
    async with TestingSessionLocal() as session:
        recorded_settlements = (await session.scalars(select(CurricularDebtSettlement))).all()
    assert settled_id == replay_settled_id
    assert [(row.debt_id, row.minutes) for row in recorded_settlements] == [
        (first_debt_id, 10),
        (second_debt_id, 10),
        (second_debt_id, 5),
    ]

    async with TestingSessionLocal.begin() as session:
        await record_execution(
            session,
            organization.id,
            year.id,
            assignment.id,
            ExecutionEntry(
                "manual:7",
                2,
                membership.id,
                "Reverse recovery",
                (ModuleCredit(module.id, -5),),
                reversal_of=last_adjustment.key,
                recorded_at=timestamp,
            ),
            planning_relevant=True,
        )
    async with TestingSessionLocal() as session:
        recorded_settlements = (
            await session.scalars(
                select(CurricularDebtSettlement).order_by(CurricularDebtSettlement.id)
            )
        ).all()
    assert [(row.debt_id, row.minutes) for row in recorded_settlements] == [
        (first_debt_id, 10),
        (second_debt_id, 10),
        (second_debt_id, 5),
        (second_debt_id, -5),
    ]
    assert recorded_settlements[-1].reversal_of_id == recorded_settlements[-2].id

    for revision in (2, 3):
        async with TestingSessionLocal.begin() as session:
            await record_execution(
                session,
                organization.id,
                year.id,
                assignment.id,
                ExecutionEntry(
                    "manual:6",
                    revision,
                    membership.id,
                    "Partial reversal of older recovery",
                    (ModuleCredit(module.id, -10),),
                    reversal_of=final_adjustment.key,
                    recorded_at=timestamp,
                ),
                planning_relevant=True,
            )
    async with TestingSessionLocal() as session:
        recorded_settlements = (
            await session.scalars(
                select(CurricularDebtSettlement).order_by(CurricularDebtSettlement.id)
            )
        ).all()
    assert [(row.debt_id, row.minutes) for row in recorded_settlements[-2:]] == [
        (second_debt_id, -10),
        (first_debt_id, -10),
    ]
    assert recorded_settlements[-2].reversal_of_id == recorded_settlements[1].id
    assert recorded_settlements[-1].reversal_of_id == recorded_settlements[0].id


async def _seed_module_assignment(db_session, clerk_user_id: str, clerk_org_id: str):
    organization, user = await create_completed_organization(
        db_session, clerk_user_id=clerk_user_id, clerk_org_id=clerk_org_id
    )
    membership = await db_session.scalar(
        select(models.OrganizationMembership).where(
            models.OrganizationMembership.organization_id == organization.id,
            models.OrganizationMembership.account_id == user.id,
        )
    )
    course = models.Course(name="Course", abbreviation="C", organization_id=organization.id)
    subject = models.Subject(name="Subject", organization_id=organization.id)
    year = models.SchedulerSchoolYear(
        organization_id=organization.id,
        label="2026/27",
        start_date=date(2026, 9, 1),
        hard_end_date=date(2027, 7, 31),
    )
    db_session.add_all((course, subject, year))
    await db_session.flush()
    class_ = models.Class(
        name="A",
        size=20,
        start_year=2026,
        end_year=2029,
        grade_level=10,
        course_id=course.id,
        organization_id=organization.id,
    )
    module = models.Module(
        organization_id=organization.id,
        subject_id=subject.id,
        name="Module",
        required_minutes=100,
        order=1,
    )
    db_session.add_all((class_, module))
    await db_session.flush()
    teacher = await create_teacher_profile(db_session, organization_id=organization.id)
    assignment = CurricularAssignment(
        organization_id=organization.id,
        school_year_id=year.id,
        class_id=class_.id,
        subject_id=subject.id,
        teacher_id=teacher.id,
    )
    state = models.SchedulerSchoolYearState(
        organization_id=organization.id,
        school_year_id=year.id,
        school_year_publication_state=models.SchoolYearPublicationState.UNPUBLISHED,
        scheduler_state_version=0,
        lock_version=0,
    )
    db_session.add_all((assignment, state))
    await db_session.flush()
    db_session.add(
        CurricularRequirement(
            organization_id=organization.id,
            assignment_id=assignment.id,
            module_id=module.id,
            sequence=1,
            required_minutes=100,
        )
    )
    await db_session.flush()
    return organization, year, assignment, module, membership


@pytest.mark.asyncio
async def test_w02_retroactive_reversal_leaves_a_free_interval_for_new_credit(db_session):
    organization, year, assignment, module, membership = await _seed_module_assignment(
        db_session, "w02_compensation_admin", "w02_compensation_org"
    )
    timestamp = datetime(2026, 9, 23, 12, tzinfo=UTC)

    async def submit(origin: str, revision: int, minutes: int, reversal_of=None) -> None:
        await record_execution(
            db_session,
            organization.id,
            year.id,
            assignment.id,
            ExecutionEntry(
                origin,
                revision,
                membership.id,
                "Recorded",
                (ModuleCredit(module.id, minutes),),
                reversal_of,
                recorded_at=timestamp,
            ),
            planning_relevant=False,
        )

    await submit("lesson:A", 1, 50)
    await submit("lesson:B", 1, 50)
    await submit("lesson:A", 2, -25, ("lesson:A", 1))
    await submit("manual:new", 1, 25)

    credits = (
        await db_session.scalars(
            select(CurricularExecutionCredit).order_by(CurricularExecutionCredit.id)
        )
    ).all()
    effective: list[tuple[int, int]] = []
    for row in credits:
        start = row.offset_minutes
        end = start + abs(row.delta_minutes)
        if row.delta_minutes > 0:
            effective.append((start, end))
        else:
            remaining: list[tuple[int, int]] = []
            for low, high in effective:
                if high <= start or low >= end:
                    remaining.append((low, high))
                    continue
                if low < start:
                    remaining.append((low, start))
                if high > end:
                    remaining.append((end, high))
            effective = remaining
    effective.sort()
    assert [row.offset_minutes for row in credits] == [0, 50, 25, 25]
    assert [row.delta_minutes for row in credits] == [50, 50, -25, 25]
    assert effective == [(0, 25), (25, 50), (50, 100)]
    for (_, previous_end), (next_start, _) in zip(effective, effective[1:], strict=False):
        assert previous_end <= next_start
