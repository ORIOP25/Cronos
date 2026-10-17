"""D09/T11/T12: per-teacher capacity deficits proven before the search."""

from app.scheduler.composition import generate_schedule
from app.scheduler.domain.candidate import (
    Assignment,
    GridSlot,
    PlanningSnapshot,
    SchedulingStrategy,
    Unavailability,
    UnavailableResource,
)
from app.scheduler.domain.capacity import aggregate_capacity_check
from app.scheduler.domain.diagnostics import DiagnosisCode
from app.scheduler.domain.projection import ModuleRequirement
from app.scheduler.domain.results import OUTCOME_INFEASIBLE
from tests.unit.test_scheduler_w04_w05_regressions_v1 import ORIGIN, period

TEACHER = 7
WEEK_DAYS = range(5)
SLOT_STARTS = (9, 10, 11, 12, 14, 15, 16, 17)


def _week_periods():
    return tuple(period(day, start, start + 1) for day in WEEK_DAYS for start in SLOT_STARTS)


def _only_nine_oclock_is_free(teacher_id):
    """The teacher is impossible from 10h to 18h every day, so only 9h remains."""
    return tuple(
        Unavailability(UnavailableResource.TEACHER, teacher_id, period(day, 10, 18))
        for day in WEEK_DAYS
    )


def _assignment(identity, class_id, teacher_id, room_id, minutes):
    return Assignment(
        identity,
        (class_id,),
        identity,
        teacher_id,
        frozenset({room_id}),
        (ModuleRequirement(identity, 1, minutes),),
    )


def _snapshot(periods, assignments, unavailable=()):
    return PlanningSnapshot(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=ORIGIN,
        preferred_end_date=periods[-1].school_date,
        hard_end_date=periods[-1].school_date,
        timezone_name="Europe/Lisbon",
        grid_slots=tuple(
            dict.fromkeys(
                GridSlot(row.school_date.weekday(), row.start_local, row.end_local)
                for row in periods
            )
        ),
        assignments=tuple(assignments),
        executed_minutes={},
        blocked_dates=frozenset(),
        unavailable=tuple(unavailable),
    )


def test_a_teacher_with_too_little_time_for_two_classes_has_a_teacher_deficit():
    periods = _week_periods()
    target = _snapshot(
        periods,
        (_assignment(1, 1, TEACHER, 1, 180), _assignment(2, 2, TEACHER, 2, 180)),
        _only_nine_oclock_is_free(TEACHER),
    )

    check = aggregate_capacity_check(target, periods)

    assert check.teacher_deficits == {TEACHER: 60}
    assert check.deficits == {}
    assert check.class_deficits == {}
    assert check.proven_infeasible


def test_generation_names_the_short_teacher_before_the_search():
    periods = _week_periods()
    target = _snapshot(
        periods,
        (_assignment(1, 1, TEACHER, 1, 180), _assignment(2, 2, TEACHER, 2, 180)),
        _only_nine_oclock_is_free(TEACHER),
    )

    result = generate_schedule(target, periods, time_limit_seconds=5)

    assert result.outcome == OUTCOME_INFEASIBLE
    [diagnosis] = result.diagnoses
    assert diagnosis.code is DiagnosisCode.INSUFFICIENT_TEACHER_TIME
    assert diagnosis.scope == f"TEACHER:{TEACHER}"
    assert diagnosis.affected_teacher_ids == (TEACHER,)
    assert diagnosis.affected_class_ids == ()
    assert diagnosis.minimum_missing_minutes == 60


def test_a_joint_unit_counts_once_toward_its_teacher_demand():
    periods = _week_periods()
    joint = Assignment(
        1,
        (1, 2),
        1,
        TEACHER,
        frozenset({1}),
        (ModuleRequirement(1, 1, 300),),
    )
    target = _snapshot(periods, (joint,), _only_nine_oclock_is_free(TEACHER))

    check = aggregate_capacity_check(target, periods)

    assert check.teacher_deficits == {}
    assert check.deficits == {}
    assert check.class_deficits == {}


def test_a_single_short_assignment_does_not_repeat_as_a_teacher_deficit():
    periods = (period(0),)
    target = _snapshot(periods, (_assignment(1, 1, 1, 1, 120),))

    check = aggregate_capacity_check(target, periods)

    assert check.deficits == {1: 60}
    assert check.teacher_deficits == {}
