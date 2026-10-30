"""Characterization of ``load_version_lessons`` (WBS 3.2.3).

Pins the exact ``VersionLessons`` of one published version: joint sisters
collapse into one logical lesson, withdrawn lessons are excluded, slices stay
sorted per lesson, unmapped units stay unresolved, and inconsistent sisters are
rejected.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import event

from app import models
from app.scheduler.domain.calendar import Period, normalize_period
from app.scheduler.domain.candidate import ScheduledLesson
from app.scheduler.domain.projection import ModuleSlice
from app.scheduler.infrastructure.models import (
    SchedulerLessonLogV1,
    SchedulerLessonSliceV1,
    SchedulerLessonV1,
    SchedulerVersionV1,
)
from app.scheduler.infrastructure.snapshot import (
    SnapshotConfigurationError,
    VersionLessons,
    load_version_lessons,
)
from tests._support.scheduler_v1 import (
    JointSeed,
    add_version,
    lesson_interval,
    seed_joint_school,
)

SCHOOL_DATE = date(2026, 9, 14)
LOGGED_AT = datetime(2026, 9, 14, 8, tzinfo=UTC)
JOINT_UNIT = "J:joint"
SINGLE_UNIT = "U:single"
ORPHAN_UNIT = "U:orphan"


@dataclass(frozen=True)
class Scenario:
    joint: JointSeed
    version: SchedulerVersionV1
    module_a: int
    module_b: int
    module_c: int

    @property
    def seed(self):
        return self.joint.base

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.seed.year.timezone)


async def _extra_module(db_session, seed, order: int) -> int:
    module = models.Module(
        organization_id=seed.organization.id,
        subject_id=seed.subject.id,
        name=f"Módulo {order + 1}",
        required_minutes=100,
        order=order,
    )
    db_session.add(module)
    await db_session.flush()
    return module.id


async def _scenario(db_session) -> Scenario:
    joint = await seed_joint_school(db_session)
    seed = joint.base
    version = await add_version(db_session, seed)
    return Scenario(
        joint=joint,
        version=version,
        module_a=seed.module.id,
        module_b=await _extra_module(db_session, seed, 1),
        module_c=await _extra_module(db_session, seed, 2),
    )


async def _add_lesson(
    db_session,
    scenario: Scenario,
    *,
    stable_key: str,
    teaching_unit_key: str,
    assignment_id: int,
    hour: int,
    minutes: int,
    credit_minutes: int | None = None,
    source_lesson_id: int | None = None,
) -> SchedulerLessonV1:
    seed = scenario.seed
    start, end = lesson_interval(SCHOOL_DATE, hour, minutes)
    lesson = SchedulerLessonV1(
        organization_id=seed.organization.id,
        school_year_id=seed.year.id,
        version_id=scenario.version.id,
        assignment_id=assignment_id,
        stable_key=stable_key,
        school_date=SCHOOL_DATE,
        starts_at=start,
        ends_at=end,
        room_id=seed.room.id,
        physical_minutes=minutes,
        credit_minutes=minutes if credit_minutes is None else credit_minutes,
        source_lesson_id=source_lesson_id,
        teaching_unit_key=teaching_unit_key,
    )
    db_session.add(lesson)
    await db_session.flush()
    return lesson


async def _add_slices(db_session, scenario: Scenario, lesson, slices) -> None:
    db_session.add_all(
        [
            SchedulerLessonSliceV1(
                organization_id=scenario.seed.organization.id,
                school_year_id=scenario.seed.year.id,
                lesson_id=lesson.id,
                module_id=module_id,
                offset_minutes=offset,
                minutes=minutes,
            )
            for module_id, offset, minutes in slices
        ]
    )
    await db_session.flush()


def _period(zone: ZoneInfo, hour: int, minutes: int) -> Period:
    start, end = lesson_interval(SCHOOL_DATE, hour, minutes)
    start_local = start.astimezone(zone)
    end_local = end.astimezone(zone)
    return normalize_period(
        SCHOOL_DATE,
        time(start_local.hour, start_local.minute),
        time(end_local.hour, end_local.minute),
        zone.key,
    )


async def _load(db_session, scenario: Scenario, **mappings) -> VersionLessons:
    return await load_version_lessons(
        db_session,
        scenario.seed.organization.id,
        scenario.seed.year.id,
        scenario.version,
        scenario.zone,
        **mappings,
    )


async def test_version_lessons_are_loaded_exactly(db_session):
    scenario = await _scenario(db_session)
    seed = scenario.seed
    class_a, class_b = seed.class_.id, scenario.joint.second_class.id
    assign_a, assign_b = scenario.joint.assignment_ids
    module_a, module_b, module_c = scenario.module_a, scenario.module_b, scenario.module_c

    sister_a = await _add_lesson(
        db_session,
        scenario,
        stable_key="7001",
        teaching_unit_key=JOINT_UNIT,
        assignment_id=assign_a,
        hour=9,
        minutes=60,
    )
    sister_b = await _add_lesson(
        db_session,
        scenario,
        stable_key="7001",
        teaching_unit_key=JOINT_UNIT,
        assignment_id=assign_b,
        hour=9,
        minutes=60,
    )
    joint_slices = ((module_a, 0, 30), (module_b, 30, 30))
    await _add_slices(db_session, scenario, sister_a, joint_slices)
    await _add_slices(db_session, scenario, sister_b, joint_slices)

    single = await _add_lesson(
        db_session,
        scenario,
        stable_key="7002",
        teaching_unit_key=SINGLE_UNIT,
        assignment_id=assign_a,
        hour=11,
        minutes=90,
    )
    await _add_slices(
        db_session,
        scenario,
        single,
        ((module_c, 60, 30), (module_a, 0, 30), (module_b, 30, 30)),
    )

    withdrawn = await _add_lesson(
        db_session,
        scenario,
        stable_key="7003",
        teaching_unit_key=SINGLE_UNIT,
        assignment_id=assign_a,
        hour=14,
        minutes=60,
    )
    await _add_slices(db_session, scenario, withdrawn, ((module_a, 0, 60),))
    db_session.add(
        SchedulerLessonLogV1(
            organization_id=seed.organization.id,
            school_year_id=seed.year.id,
            lesson_id=withdrawn.id,
            status="OCCURRENCE",
            revision=1,
            logged_by_membership_id=seed.membership.id,
            logged_at=LOGGED_AT,
            created_at=LOGGED_AT,
            updated_at=LOGGED_AT,
            withdrawn_at=LOGGED_AT,
        )
    )
    orphan = await _add_lesson(
        db_session,
        scenario,
        stable_key="7004",
        teaching_unit_key=ORPHAN_UNIT,
        assignment_id=assign_a,
        hour=15,
        minutes=30,
        source_lesson_id=single.id,
    )
    await _add_slices(db_session, scenario, orphan, ((module_a, 0, 30),))
    await db_session.commit()

    result = await _load(
        db_session,
        scenario,
        unit_keys={JOINT_UNIT: 55, SINGLE_UNIT: 56},
        class_ids_by_unit={55: (class_a, class_b), 56: (class_a,)},
        accounting_classes={assign_a: class_a, assign_b: class_b},
    )

    assert result == VersionLessons(
        lessons=(
            ScheduledLesson(
                lesson_id=7001,
                assignment_id=55,
                period=_period(scenario.zone, 9, 60),
                room_id=seed.room.id,
                credit_minutes=60,
                slices=(ModuleSlice(7001, module_a, 0, 30), ModuleSlice(7001, module_b, 30, 30)),
                class_ids=(class_a, class_b),
            ),
            ScheduledLesson(
                lesson_id=7002,
                assignment_id=56,
                period=_period(scenario.zone, 11, 90),
                room_id=seed.room.id,
                credit_minutes=90,
                slices=(
                    ModuleSlice(7002, module_a, 0, 30),
                    ModuleSlice(7002, module_b, 30, 30),
                    ModuleSlice(7002, module_c, 60, 30),
                ),
                class_ids=(class_a,),
            ),
            ScheduledLesson(
                lesson_id=7004,
                assignment_id=assign_a,
                period=_period(scenario.zone, 15, 30),
                room_id=seed.room.id,
                credit_minutes=30,
                slices=(ModuleSlice(7004, module_a, 0, 30),),
                source_lesson_id=7002,
            ),
        ),
        identity_by_db_id={
            sister_a.id: 7001,
            sister_b.id: 7001,
            single.id: 7002,
            orphan.id: 7004,
        },
        db_id_by_identity={7001: sister_a.id, 7002: single.id, 7004: orphan.id},
        db_ids_by_identity_class={
            7001: {class_a: sister_a.id, class_b: sister_b.id},
            7002: {class_a: single.id},
            7004: {class_a: orphan.id},
        },
        unresolved_identities=frozenset({7004}),
    )


async def test_sister_with_a_different_credit_is_inconsistent(db_session):
    scenario = await _scenario(db_session)
    assign_a, assign_b = scenario.joint.assignment_ids
    slices = ((scenario.module_a, 0, 30), (scenario.module_b, 30, 30))
    sister_a = await _add_lesson(
        db_session,
        scenario,
        stable_key="8001",
        teaching_unit_key=JOINT_UNIT,
        assignment_id=assign_a,
        hour=9,
        minutes=60,
    )
    sister_b = await _add_lesson(
        db_session,
        scenario,
        stable_key="8001",
        teaching_unit_key=JOINT_UNIT,
        assignment_id=assign_b,
        hour=9,
        minutes=60,
        credit_minutes=50,
    )
    await _add_slices(db_session, scenario, sister_a, slices)
    await _add_slices(db_session, scenario, sister_b, slices)

    with pytest.raises(SnapshotConfigurationError) as exc:
        await _load(db_session, scenario)

    assert exc.value.code == "JOINT_LESSON_INCONSISTENT"


async def test_sister_with_different_modules_is_inconsistent(db_session):
    scenario = await _scenario(db_session)
    assign_a, assign_b = scenario.joint.assignment_ids
    sister_a = await _add_lesson(
        db_session,
        scenario,
        stable_key="8002",
        teaching_unit_key=JOINT_UNIT,
        assignment_id=assign_a,
        hour=9,
        minutes=60,
    )
    sister_b = await _add_lesson(
        db_session,
        scenario,
        stable_key="8002",
        teaching_unit_key=JOINT_UNIT,
        assignment_id=assign_b,
        hour=9,
        minutes=60,
    )
    await _add_slices(
        db_session,
        scenario,
        sister_a,
        ((scenario.module_a, 0, 30), (scenario.module_b, 30, 30)),
    )
    await _add_slices(
        db_session,
        scenario,
        sister_b,
        ((scenario.module_a, 0, 30), (scenario.module_c, 30, 30)),
    )

    with pytest.raises(SnapshotConfigurationError) as exc:
        await _load(db_session, scenario)

    assert exc.value.code == "JOINT_LESSON_INCONSISTENT"


async def test_slice_query_parameters_do_not_grow_with_the_lessons(db_session):
    """A real school year has tens of thousands of lessons; PostgreSQL accepts 32 767 parameters."""
    scenario = await _scenario(db_session)
    assign_a, _ = scenario.joint.assignment_ids
    for hour in range(8, 20):
        lesson = await _add_lesson(
            db_session,
            scenario,
            stable_key=str(8000 + hour),
            teaching_unit_key=SINGLE_UNIT,
            assignment_id=assign_a,
            hour=hour,
            minutes=30,
        )
        await _add_slices(db_session, scenario, lesson, ((scenario.module_a, 0, 30),))
    await db_session.commit()
    slice_parameters: list[int] = []

    def record(_connection, _cursor, statement, parameters, _context, _many):
        if "scheduler_lesson_slice_v1" in statement:
            slice_parameters.append(len(parameters))

    engine = db_session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", record)
    try:
        result = await _load(db_session, scenario, unit_keys={SINGLE_UNIT: 56})
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert len(result.lessons) == 12
    assert slice_parameters and max(slice_parameters) <= 5
