"""WBS S1: availability priority ledger (tech spec T01-T06, T08, T14) and risks R04, R18-R21."""

from datetime import date, time, timedelta

from app.scheduler.domain.availability_priority import AvailabilityLedger, on_pace
from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import (
    Assignment,
    GridSlot,
    PlanningSnapshot,
    SchedulingStrategy,
    Unavailability,
    UnavailableResource,
)
from app.scheduler.domain.projection import ModuleRequirement

TZ = "Europe/Lisbon"
MONDAY = date(2026, 9, 14)
HOURS = (9, 10, 11, 12, 14, 15, 16, 17)
TEACHER = UnavailableResource.TEACHER
CLASS = UnavailableResource.CLASS


def period(day: int, hour: int):
    return normalize_period(MONDAY + timedelta(days=day), time(hour), time(hour + 1), TZ)


def week_periods():
    """Forty one-hour periods, Monday to Friday, in chronological order."""
    return tuple(period(day, hour) for day in range(5) for hour in HOURS)


def assignment(identity: int, teacher_id: int, class_ids: tuple[int, ...]) -> Assignment:
    return Assignment(
        identity,
        class_ids,
        identity,
        teacher_id,
        frozenset({100 + identity}),
        (ModuleRequirement(identity * 10, 1, 60),),
    )


def snapshot(assignments, soft=()) -> PlanningSnapshot:
    return PlanningSnapshot(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=MONDAY,
        preferred_end_date=MONDAY + timedelta(days=4),
        hard_end_date=MONDAY + timedelta(days=4),
        timezone_name=TZ,
        grid_slots=tuple(
            GridSlot(day, time(hour), time(hour + 1)) for day in range(5) for hour in HOURS
        ),
        assignments=tuple(assignments),
        executed_minutes={},
        blocked_dates=frozenset(),
        unavailable=(),
        soft_unavailable=tuple(soft),
    )


def test_on_pace_compares_remaining_demand_with_its_share_of_capacity():
    # R04: demand 600 of 600 over capacity 1200; a period with 600 left.
    assert on_pace(300, 600, 600, 1200) is True
    assert on_pace(290, 600, 600, 1200) is False


def test_priority_falls_back_to_the_ceiling_once_a_resource_is_ahead_of_pace():
    # R04 through the ledger: teacher 1 has D(0)=600 and C(0)=1200.
    grid = week_periods()
    teacher_row = assignment(1, teacher_id=1, class_ids=(1,))
    ceiling_row = assignment(2, teacher_id=2, class_ids=(2,))
    ledger = AvailabilityLedger.build(
        snapshot((teacher_row, ceiling_row)),
        {1: grid[:20], 2: grid},
        {1: 600, 2: 2400},
    )

    assert ledger.priority(teacher_row, grid[10]) == 1200
    ledger.place(teacher_row, 300)
    assert ledger.priority(teacher_row, grid[10]) == 1200
    ledger.place(teacher_row, 10)
    assert ledger.priority(teacher_row, grid[10]) == 2400


def test_shared_periods_count_once_and_only_the_own_evitar_leaves_neutral_capacity():
    # R18: two assignments of teacher 1 over the same five periods.
    five = week_periods()[:5]
    first = assignment(1, teacher_id=1, class_ids=(1,))
    second = assignment(2, teacher_id=1, class_ids=(2,))
    soft = (
        Unavailability(TEACHER, 1, five[0]),
        Unavailability(TEACHER, 1, five[1]),
        Unavailability(CLASS, 1, five[2]),
    )
    ledger = AvailabilityLedger.build(
        snapshot((first, second), soft),
        {1: five, 2: five},
        {1: 60, 2: 60},
    )

    assert ledger.capacity(("teacher", 1)) == 300
    assert ledger.neutral_capacity(("teacher", 1), five[0]) == 180
    assert ledger.neutral_capacity(("class", 1), five[0]) == 240
    assert ledger.demand(("teacher", 1)) == 120


def test_a_joint_assignment_counts_once_for_the_teacher_and_once_per_class():
    # R19: one teacher, two classes, 120 minutes missing.
    joint = assignment(1, teacher_id=1, class_ids=(1, 2))
    ledger = AvailabilityLedger.build(snapshot((joint,)), {1: week_periods()[:2]}, {1: 120})

    assert ledger.demand(("teacher", 1)) == 120
    assert ledger.demand(("class", 1)) == 120
    assert ledger.demand(("class", 2)) == 120


def test_the_ceiling_applies_only_when_no_resource_of_the_option_is_on_pace():
    # R20: teacher 1 is on pace (600 of 600) and class 2 is ahead of pace (C(0)=300).
    week = week_periods()
    first_days = week[:5]
    second_day = week[8:13]
    option = assignment(1, teacher_id=1, class_ids=(2,))
    class_mate = assignment(2, teacher_id=5, class_ids=(2,))
    teacher_extra = assignment(3, teacher_id=1, class_ids=(3,))
    ceiling = assignment(4, teacher_id=9, class_ids=(9,))
    ledger = AvailabilityLedger.build(
        snapshot((option, class_mate, teacher_extra, ceiling)),
        {1: first_days, 2: first_days, 3: second_day, 4: week},
        {1: 300, 2: 100, 3: 300, 4: 2400},
    )

    assert ledger.priority(option, first_days[0]) == 300
    ledger.place(class_mate, 100)
    assert ledger.priority(option, first_days[0]) == 600
    ledger.place(teacher_extra, 100)
    assert ledger.priority(option, first_days[0]) == 2400


def test_an_option_in_an_evitar_is_refused_without_spare_demand_and_allowed_with_it():
    # R21: the Evitar of teacher 1 covers Monday 9h; four free hours follow it.
    first_days = week_periods()[:5]
    option = assignment(1, teacher_id=1, class_ids=(1,))
    spare = assignment(2, teacher_id=1, class_ids=(3,))
    soft = (Unavailability(TEACHER, 1, first_days[0]),)

    without_spare = AvailabilityLedger.build(
        snapshot((option, spare), soft), {1: first_days, 2: first_days[:1]}, {1: 240}
    )
    assert without_spare.allows(option, first_days[0]) is False
    assert without_spare.refused == 1

    with_spare = AvailabilityLedger.build(
        snapshot((option, spare), soft), {1: first_days, 2: first_days[:1]}, {1: 240, 2: 60}
    )
    assert with_spare.allows(option, first_days[0]) is True
    assert with_spare.refused == 0


def test_occupied_periods_leave_the_capacity_of_the_teacher_and_its_classes():
    # T14: a retained published lesson takes its period out of the teacher and class capacity.
    first_days = week_periods()[:5]
    row = assignment(1, teacher_id=1, class_ids=(1,))
    ledger = AvailabilityLedger.build(
        snapshot((row,)),
        {1: first_days},
        {1: 300},
        occupied=[(row, first_days[0])],
    )

    assert ledger.capacity(("teacher", 1)) == 240
    assert ledger.capacity(("class", 1)) == 240


def test_unfavorable_flags_a_period_inside_the_evitar_of_the_teacher_or_a_class():
    first_days = week_periods()[:5]
    joint = assignment(1, teacher_id=1, class_ids=(1, 2))
    soft = (Unavailability(CLASS, 2, first_days[0]),)
    ledger = AvailabilityLedger.build(snapshot((joint,), soft), {1: first_days}, {1: 60})

    assert ledger.unfavorable(joint, first_days[0]) is True
    assert ledger.unfavorable(joint, first_days[1]) is False
