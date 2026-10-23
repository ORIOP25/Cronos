"""Repair keeps a class day from two internal gap hours (owner rules, 23 Oct 2026).

The published week has class 1 lessons at 12h and 15h on Monday. Assignments 3 and 4 are missing.
Without the excess term the repair puts assignment 4 at 11h and assignment 3 at 9h, which leaves
13h and 14h empty: two internal gap hours. With the term, assignment 3 moves to 14h and the
class day keeps one gap hour. The Evitar hours of teachers 3 and 4 come from the same scenario.
"""

from datetime import date, time, timedelta
from time import monotonic

from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import (
    Assignment,
    GridSlot,
    PlanningSnapshot,
    ScheduledLesson,
    SchedulingStrategy,
    Unavailability,
    UnavailableResource,
)
from app.scheduler.domain.priorities import DEFAULT_LEVELS, PriorityWeights
from app.scheduler.domain.priority_value import _gap_minutes
from app.scheduler.domain.projection import ModuleRequirement, ModuleSlice
from app.scheduler.infrastructure.recovery_construction import construct_recovery

TZ = "Europe/Lisbon"
MONDAY = date(2026, 9, 14)
DAYS = tuple(MONDAY + timedelta(days=offset) for offset in range(5))
HOURS = (9, 10, 11, 12, 13, 14, 15)
# (teacher, day of September 2026, hour) where the teacher wants no lesson (Evitar).
EVITAR = (
    (3, 14, 10),
    (3, 14, 11),
    (3, 14, 12),
    (3, 14, 13),
    (3, 14, 15),
    (3, 17, 12),
    (3, 18, 15),
    (4, 14, 10),
    (4, 14, 12),
    (4, 14, 13),
    (4, 14, 14),
    (4, 15, 9),
    (4, 15, 12),
    (4, 15, 14),
    (4, 16, 11),
    (4, 16, 15),
    (4, 18, 15),
)


def window(day, hour):
    return normalize_period(day, time(hour), time(hour + 1), TZ)


def published_lesson(lesson_id, hour):
    return ScheduledLesson(
        lesson_id,
        lesson_id,
        window(MONDAY, hour),
        100 + lesson_id,
        60,
        (ModuleSlice(lesson_id, lesson_id * 10, 0, 60),),
        teacher_id=None,
        class_ids=(1,),
    )


def school():
    assignments = tuple(
        Assignment(
            identity,
            (1,),
            identity,
            identity,
            frozenset({100 + identity}),
            (ModuleRequirement(identity * 10, 1, 60),),
        )
        for identity in range(1, 5)
    )
    evitar = tuple(
        Unavailability(UnavailableResource.TEACHER, teacher, window(date(2026, 9, day), hour))
        for teacher, day, hour in EVITAR
    )
    snapshot = PlanningSnapshot(
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        origin=MONDAY,
        preferred_end_date=DAYS[-1],
        hard_end_date=DAYS[-1],
        timezone_name=TZ,
        grid_slots=tuple(GridSlot(0, time(hour), time(hour + 1)) for hour in HOURS),
        assignments=assignments,
        executed_minutes={},
        blocked_dates=frozenset(),
        unavailable=(),
        soft_unavailable=evitar,
        lunch_rule=None,
        baseline_lessons=(published_lesson(1, 12), published_lesson(2, 15)),
    )
    periods = tuple(window(day, hour) for day in DAYS for hour in HOURS)
    return snapshot, periods


def monday_internal_gap_minutes(snapshot, candidate):
    intervals = [
        (row.period.start_local.hour * 60, row.period.end_local.hour * 60)
        for row in candidate.lessons
        if row.period.school_date == MONDAY
    ]
    return _gap_minutes(intervals, snapshot.grid_slots, None)


def test_repair_keeps_class_one_from_two_internal_gap_hours_on_monday():
    snapshot, periods = school()

    candidate = construct_recovery(
        snapshot,
        periods,
        deadline=monotonic() + 60,
        weights=PriorityWeights(dict(DEFAULT_LEVELS)),
    )

    assert candidate is not None
    assert monday_internal_gap_minutes(snapshot, candidate) <= 60
