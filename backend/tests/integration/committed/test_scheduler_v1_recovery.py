from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import models
from app.scheduler.domain.debt import DebtOrigin, RecoveryAllocation
from app.scheduler.domain.demand import ExecutionEntry, ModuleCredit
from app.scheduler.infrastructure.models import (
    CurricularAssignment,
    CurricularDebt,
    CurricularDebtRevision,
    CurricularRequirement,
    SchedulerLessonSliceV1,
    SchedulerLessonV1,
    SchedulerRecoveryReservationV1,
)
from app.scheduler.infrastructure.progress import (
    cancel_recovery,
    ensure_no_physical_collisions,
    plan_recovery,
    record_debt,
    record_execution,
    revise_debt,
)
from tests._support.db_fixtures import create_teacher_profile
from tests._support.scheduler_v1 import (
    add_lesson,
    add_version,
    lesson_interval,
    seed_v1_assignment,
)

pytestmark = pytest.mark.postgresql

TIMESTAMP = datetime(2026, 9, 23, 12, tzinfo=UTC)
LESSON_DATE = date(2026, 9, 23)


async def _seed_with_debt(db_session, suffix: str, *, debt_minutes: int = 50):
    seed = await seed_v1_assignment(
        db_session,
        clerk_user_id=f"w02_rec_{suffix}",
        clerk_org_id=f"w02_rec_org_{suffix}",
    )
    version = await add_version(db_session, seed, status="CANDIDATE")
    start, end = lesson_interval(LESSON_DATE, 9)
    lesson = await add_lesson(
        db_session,
        seed,
        version,
        stable_key="lesson:1",
        school_date=LESSON_DATE,
        start=start,
        end=end,
    )
    debt_id = await record_debt(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        DebtOrigin(
            f"occurrence:{suffix}",
            1,
            date(2026, 9, 22),
            debt_minutes,
            seed.membership.id,
            "Missed lesson",
            TIMESTAMP,
        ),
    )
    return seed, version, lesson, debt_id


@pytest.mark.asyncio
async def test_plan_recovery_is_idempotent_and_respects_bounds(db_session):
    seed, version, lesson, debt_id = await _seed_with_debt(db_session, "a")
    allocation = RecoveryAllocation(version.id, lesson.id, debt_id, 50)

    planned = await plan_recovery(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        version.id,
        (allocation,),
    )
    replay = await plan_recovery(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        version.id,
        (allocation,),
    )

    reservations = (await db_session.scalars(select(SchedulerRecoveryReservationV1))).all()
    assert planned is True
    assert replay is False
    assert [
        (row.assignment_id, row.lesson_id, row.debt_id, row.minutes) for row in reservations
    ] == [(seed.assignment.id, lesson.id, debt_id, 50)]

    with pytest.raises(ValueError, match="planned version"):
        await plan_recovery(
            db_session,
            seed.organization.id,
            seed.year.id,
            seed.assignment.id,
            version.id,
            (RecoveryAllocation(version.id, 9_999, debt_id, 10),),
        )
    with pytest.raises(ValueError, match="Reserved recovery exceeds"):
        await plan_recovery(
            db_session,
            seed.organization.id,
            seed.year.id,
            seed.assignment.id,
            version.id,
            (RecoveryAllocation(version.id, lesson.id, debt_id, 60),),
        )


@pytest.mark.asyncio
async def test_record_execution_releases_reserved_debt(db_session):
    seed, version, lesson, debt_id = await _seed_with_debt(db_session, "b")
    version.status = "ACTIVE"
    version.approved_at = TIMESTAMP
    await db_session.flush()
    await plan_recovery(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        version.id,
        (RecoveryAllocation(version.id, lesson.id, debt_id, 50),),
    )

    await record_execution(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        ExecutionEntry(
            "manual:1",
            1,
            seed.membership.id,
            "Recovered lesson",
            (ModuleCredit(seed.module.id, 50),),
            recorded_at=TIMESTAMP,
        ),
        planning_relevant=True,
    )

    reservations = (await db_session.scalars(select(SchedulerRecoveryReservationV1))).all()
    assert reservations == []


@pytest.mark.asyncio
async def test_cancel_recovery_releases_without_duplicating_debt(db_session):
    seed, version, lesson, debt_id = await _seed_with_debt(db_session, "c")
    await plan_recovery(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        version.id,
        (RecoveryAllocation(version.id, lesson.id, debt_id, 50),),
    )
    before = len((await db_session.scalars(select(CurricularDebt))).all())

    cancelled = await cancel_recovery(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        version.id,
        lesson.id,
        debt_id,
    )
    replay = await cancel_recovery(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        version.id,
        lesson.id,
        debt_id,
    )

    assert cancelled is True
    assert replay is False
    assert (await db_session.scalars(select(SchedulerRecoveryReservationV1))).all() == []
    assert len((await db_session.scalars(select(CurricularDebt))).all()) == before


@pytest.mark.asyncio
async def test_revise_debt_appends_audited_revision_and_rejects_negative_open(db_session):
    seed, _, _, debt_id = await _seed_with_debt(db_session, "d")

    revision_id = await revise_debt(
        db_session,
        seed.organization.id,
        seed.year.id,
        debt_id,
        origin="manual:1",
        revision=1,
        delta_minutes=10,
        author_id=seed.membership.id,
        reason="Add missed minutes",
        recorded_at=TIMESTAMP,
    )
    replay_id = await revise_debt(
        db_session,
        seed.organization.id,
        seed.year.id,
        debt_id,
        origin="manual:1",
        revision=1,
        delta_minutes=10,
        author_id=seed.membership.id,
        reason="Add missed minutes",
        recorded_at=TIMESTAMP,
    )

    revisions = (await db_session.scalars(select(CurricularDebtRevision))).all()
    assert revision_id == replay_id
    assert [(row.delta_minutes, row.revision) for row in revisions] == [(10, 1)]

    with pytest.raises(ValueError, match="Conflicting replay"):
        await revise_debt(
            db_session,
            seed.organization.id,
            seed.year.id,
            debt_id,
            origin="manual:1",
            revision=1,
            delta_minutes=20,
            author_id=seed.membership.id,
            reason="Different",
            recorded_at=TIMESTAMP,
        )


@pytest.mark.asyncio
async def test_reservation_cannot_mix_assignments_or_debts(db_session):
    seed, version, lesson, _ = await _seed_with_debt(db_session, "e")
    second_class = models.Class(
        name="B",
        size=20,
        start_year=2026,
        end_year=2029,
        grade_level=10,
        course_id=seed.course.id,
        organization_id=seed.organization.id,
    )
    module_b = models.Module(
        organization_id=seed.organization.id,
        subject_id=seed.subject.id,
        name="Module B",
        required_minutes=50,
        order=2,
    )
    db_session.add_all((second_class, module_b))
    await db_session.flush()
    teacher_b = await create_teacher_profile(db_session, organization_id=seed.organization.id)
    assignment_b = CurricularAssignment(
        organization_id=seed.organization.id,
        school_year_id=seed.year.id,
        class_id=second_class.id,
        subject_id=seed.subject.id,
        teacher_id=teacher_b.id,
    )
    db_session.add(assignment_b)
    await db_session.flush()
    db_session.add(
        CurricularRequirement(
            organization_id=seed.organization.id,
            assignment_id=assignment_b.id,
            module_id=module_b.id,
            sequence=1,
            required_minutes=50,
        )
    )
    await db_session.flush()
    debt_b_id = await record_debt(
        db_session,
        seed.organization.id,
        seed.year.id,
        assignment_b.id,
        DebtOrigin(
            "occurrence:other",
            1,
            date(2026, 9, 22),
            50,
            seed.membership.id,
            "Other class",
            TIMESTAMP,
        ),
    )

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                SchedulerRecoveryReservationV1(
                    organization_id=seed.organization.id,
                    school_year_id=seed.year.id,
                    version_id=version.id,
                    assignment_id=seed.assignment.id,
                    lesson_id=lesson.id,
                    debt_id=debt_b_id,
                    minutes=10,
                )
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_physical_minutes_must_match_the_interval(db_session):
    seed = await seed_v1_assignment(
        db_session, clerk_user_id="w02_rec_f", clerk_org_id="w02_rec_org_f"
    )
    version = await add_version(db_session, seed, status="CANDIDATE")
    start, end = lesson_interval(LESSON_DATE, 9)

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                SchedulerLessonV1(
                    organization_id=seed.organization.id,
                    school_year_id=seed.year.id,
                    version_id=version.id,
                    assignment_id=seed.assignment.id,
                    stable_key="lesson:bad",
                    school_date=LESSON_DATE,
                    starts_at=start,
                    ends_at=end,
                    room_id=seed.room.id,
                    physical_minutes=61,
                    credit_minutes=60,
                )
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_collision_boundary_rejects_overlapping_resources(db_session):
    seed = await seed_v1_assignment(
        db_session, clerk_user_id="w02_rec_g", clerk_org_id="w02_rec_org_g"
    )
    version = await add_version(db_session, seed, status="CANDIDATE")
    first_start, first_end = lesson_interval(LESSON_DATE, 9)
    overlapping_start, overlapping_end = lesson_interval(LESSON_DATE, 9, 30)
    await add_lesson(
        db_session,
        seed,
        version,
        stable_key="lesson:1",
        school_date=LESSON_DATE,
        start=first_start,
        end=first_end,
    )
    await add_lesson(
        db_session,
        seed,
        version,
        stable_key="lesson:2",
        school_date=LESSON_DATE,
        start=overlapping_start,
        end=overlapping_end,
    )

    with pytest.raises(ValueError, match="overlaps resource"):
        await ensure_no_physical_collisions(
            db_session, seed.organization.id, seed.year.id, version.id
        )


@pytest.mark.asyncio
async def test_collision_boundary_rejects_slices_outside_the_curriculum(db_session):
    seed = await seed_v1_assignment(
        db_session, clerk_user_id="w02_rec_h", clerk_org_id="w02_rec_org_h"
    )
    version = await add_version(db_session, seed, status="CANDIDATE")
    start, end = lesson_interval(LESSON_DATE, 9)
    lesson = await add_lesson(
        db_session,
        seed,
        version,
        stable_key="lesson:1",
        school_date=LESSON_DATE,
        start=start,
        end=end,
    )
    foreign_module = models.Module(
        organization_id=seed.organization.id,
        subject_id=seed.subject.id,
        name="Not required",
        required_minutes=50,
        order=2,
    )
    db_session.add(foreign_module)
    await db_session.flush()
    db_session.add(
        SchedulerLessonSliceV1(
            organization_id=seed.organization.id,
            school_year_id=seed.year.id,
            lesson_id=lesson.id,
            module_id=foreign_module.id,
            offset_minutes=0,
            minutes=60,
        )
    )
    await db_session.flush()

    with pytest.raises(ValueError, match="leaves the assignment curriculum"):
        await ensure_no_physical_collisions(
            db_session, seed.organization.id, seed.year.id, version.id
        )


@pytest.mark.asyncio
async def test_collision_boundary_accepts_coherent_versions(db_session):
    seed = await seed_v1_assignment(
        db_session, clerk_user_id="w02_rec_i", clerk_org_id="w02_rec_org_i"
    )
    requirement = (
        await db_session.scalars(
            select(CurricularRequirement).where(
                CurricularRequirement.assignment_id == seed.assignment.id
            )
        )
    ).one()
    version = await add_version(db_session, seed, status="CANDIDATE")
    first_start, first_end = lesson_interval(LESSON_DATE, 9)
    second_start, second_end = lesson_interval(LESSON_DATE, 10)
    first = await add_lesson(
        db_session,
        seed,
        version,
        stable_key="lesson:1",
        school_date=LESSON_DATE,
        start=first_start,
        end=first_end,
        credit_minutes=60,
    )
    await add_lesson(
        db_session,
        seed,
        version,
        stable_key="lesson:2",
        school_date=LESSON_DATE,
        start=second_start,
        end=second_end,
        credit_minutes=40,
        room_id=seed.room.id,
    )
    db_session.add(
        SchedulerLessonSliceV1(
            organization_id=seed.organization.id,
            school_year_id=seed.year.id,
            lesson_id=first.id,
            module_id=requirement.module_id,
            offset_minutes=0,
            minutes=60,
        )
    )
    await db_session.flush()

    await ensure_no_physical_collisions(db_session, seed.organization.id, seed.year.id, version.id)
