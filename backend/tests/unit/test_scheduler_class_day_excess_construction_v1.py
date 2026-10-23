"""Construction keeps a class day from two internal gap hours (owner rules, 23 Oct 2026).

Without the excess term of T06, class 2 leaves 10h and 11h empty on Monday and gets 12h and
14h, which is two internal gap hours. With the term, the 14h lesson moves to 13h.
"""

from datetime import date, time, timedelta

from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import (
    Assignment,
    GridSlot,
    PlanningSnapshot,
    SchedulingStrategy,
    Unavailability,
    UnavailableResource,
)
from app.scheduler.domain.priorities import DEFAULT_LEVELS, PriorityWeights
from app.scheduler.domain.priority_value import _gap_minutes
from app.scheduler.domain.projection import ModuleRequirement
from app.scheduler.infrastructure.constructive import construct_schedule

TZ = "Europe/Lisbon"
MONDAY = date(2026, 9, 14)
DAYS = tuple(MONDAY + timedelta(days=offset) for offset in range(5))
HOURS = (9, 10, 11, 12, 13, 14, 15)
# Teacher Evitar hours: the teachers are busy at these hours, so the constructor skips them.
EVITAR_HOURS = {
    1: (
        (MONDAY, 11),
        (DAYS[1], 14),
        (DAYS[2], 9),
        (DAYS[2], 10),
        (DAYS[2], 11),
        (DAYS[2], 14),
        (DAYS[3], 13),
        (DAYS[4], 11),
        (DAYS[4], 12),
    ),
    2: (
        (MONDAY, 13),
        (MONDAY, 15),
        (DAYS[1], 9),
        (DAYS[1], 12),
        (DAYS[1], 14),
        (DAYS[2], 9),
        (DAYS[2], 13),
        (DAYS[2], 14),
        (DAYS[3], 10),
        (DAYS[3], 11),
        (DAYS[4], 9),
        (DAYS[4], 11),
    ),
    3: (
        (MONDAY, 10),
        (MONDAY, 11),
        (DAYS[1], 10),
        (DAYS[2], 10),
        (DAYS[2], 11),
        (DAYS[2], 12),
        (DAYS[2], 13),
        (DAYS[3], 10),
        (DAYS[3], 14),
        (DAYS[4], 10),
        (DAYS[4], 11),
    ),
}
LEVELS = {**DEFAULT_LEVELS, "teacher_gaps": 2}


def assignment(identity, class_id, teacher_id, minutes):
    return Assignment(
        identity,
        (class_id,),
        identity,
        teacher_id,
        frozenset({100 + identity}),
        (ModuleRequirement(identity * 10, 1, minutes),),
    )


def school():
    assignments = (
        assignment(1, 1, 1, 60),
        assignment(2, 1, 2, 60),
        assignment(3, 1, 3, 60),
        assignment(4, 2, 1, 60),
        assignment(5, 2, 2, 60),
        assignment(6, 2, 3, 120),
    )
    soft = tuple(
        Unavailability(
            UnavailableResource.TEACHER,
            teacher_id,
            normalize_period(day, time(hour), time(hour + 1), TZ),
        )
        for teacher_id, hours in EVITAR_HOURS.items()
        for day, hour in hours
    )
    snapshot = PlanningSnapshot(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=MONDAY,
        preferred_end_date=DAYS[-1],
        hard_end_date=DAYS[-1],
        timezone_name=TZ,
        grid_slots=tuple(GridSlot(0, time(hour), time(hour + 1)) for hour in HOURS),
        assignments=assignments,
        executed_minutes={},
        blocked_dates=frozenset(),
        unavailable=(),
        soft_unavailable=soft,
        lunch_rule=None,
    )
    periods = tuple(
        normalize_period(day, time(hour), time(hour + 1), TZ) for day in DAYS for hour in HOURS
    )
    return snapshot, periods


def monday_internal_gap_minutes(snapshot, candidate, class_id):
    class_assignments = {
        row.assignment_id for row in snapshot.assignments if class_id in row.class_ids
    }
    intervals = [
        (row.period.start_local.hour * 60, row.period.end_local.hour * 60)
        for row in candidate.lessons
        if row.period.school_date == MONDAY and row.assignment_id in class_assignments
    ]
    return _gap_minutes(intervals, snapshot.grid_slots, None)


def test_excess_term_keeps_class_two_from_two_internal_gap_hours_on_monday():
    snapshot, periods = school()

    candidate = construct_schedule(snapshot, periods, weights=PriorityWeights(LEVELS))

    assert candidate is not None
    assert monday_internal_gap_minutes(snapshot, candidate, 2) <= 60
