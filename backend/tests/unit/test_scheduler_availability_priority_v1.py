"""WBS S1: availability priority ledger (tech spec T01-T06, T08, T14) and risks R04, R18-R21."""

from datetime import date, time, timedelta

from app.scheduler.domain.availability_priority import AvailabilityLedger, is_avoided, on_pace
from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import (
    Assignment,
    GridSlot,
    PlanningSnapshot,
    SchedulingStrategy,
    Unavailability,
    UnavailableResource,
)
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.domain.projection import ModuleRequirement
from app.scheduler.infrastructure.constructive import construct_schedule

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


def assignment(
    identity: int, teacher_id: int, class_ids: tuple[int, ...], minutes: int = 60
) -> Assignment:
    return Assignment(
        identity,
        class_ids,
        identity,
        teacher_id,
        frozenset({100 + identity}),
        (ModuleRequirement(identity * 10, 1, minutes),),
    )


def school_days(weeks: int) -> tuple[date, ...]:
    days = (MONDAY + timedelta(days=offset) for offset in range(weeks * 7))
    return tuple(day for day in days if day.weekday() < 5)


def horizon_periods(weeks: int) -> tuple:
    return tuple(
        normalize_period(day, time(hour), time(hour + 1), TZ)
        for day in school_days(weeks)
        for hour in HOURS
    )


def block(resource, identity: int, offset: int, start: int, end: int) -> Unavailability:
    """A block on the school day ``offset`` days after the Monday of the origin."""
    day = MONDAY + timedelta(days=offset)
    return Unavailability(resource, identity, normalize_period(day, time(start), time(end), TZ))


def daily(resource, identity: int, start: int, end: int, weeks: int = 1) -> tuple:
    return tuple(
        block(resource, identity, (day - MONDAY).days, start, end) for day in school_days(weeks)
    )


def week_of(lesson) -> int:
    return (lesson.period.school_date - MONDAY).days // 7 + 1


def snapshot(assignments, soft=(), unavailable=(), weeks: int = 1) -> PlanningSnapshot:
    last_day = school_days(weeks)[-1]
    return PlanningSnapshot(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=MONDAY,
        preferred_end_date=last_day,
        hard_end_date=last_day,
        timezone_name=TZ,
        grid_slots=tuple(
            GridSlot(day, time(hour), time(hour + 1)) for day in range(5) for hour in HOURS
        ),
        assignments=tuple(assignments),
        executed_minutes={},
        blocked_dates=frozenset(),
        unavailable=tuple(unavailable),
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


def test_urgency_ranks_resources_without_spare_periods_by_their_remaining_capacity():
    # Schedule priorities T09: a resource that cannot skip this period is urgent;
    # the one with less remaining capacity is served first, the rest share the ceiling.
    grid = week_periods()
    tight = assignment(1, teacher_id=1, class_ids=(1,), minutes=120)
    tighter = assignment(2, teacher_id=2, class_ids=(2,), minutes=60)
    loose = assignment(3, teacher_id=3, class_ids=(3,), minutes=60)
    ledger = AvailabilityLedger.build(
        snapshot((tight, tighter, loose)),
        {1: grid[:2], 2: grid[:1], 3: grid[:5]},
        {1: 120, 2: 60, 3: 60},
    )

    assert ledger.urgency(tighter, grid[0]) == 60
    assert ledger.urgency(tight, grid[0]) == 120
    assert ledger.urgency(loose, grid[0]) == 300
    # At most one period to spare is urgent: four periods left for one lesson is not,
    # two periods left is (one spare), and the last period is.
    assert ledger.urgency(loose, grid[1]) == 300
    assert ledger.urgency(loose, grid[3]) == 120
    assert ledger.urgency(loose, grid[4]) == 60


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


def test_inside_its_own_evitar_a_resource_is_necessary_only_when_the_rest_cannot_hold_it():
    # A teacher prefers mornings: every afternoon (14h-18h) is Evitar, 10 hours to teach.
    week = week_periods()
    row = assignment(1, teacher_id=1, class_ids=(1,), minutes=600)
    afternoons = tuple(
        Unavailability(TEACHER, 1, item) for item in week if item.start_local.hour >= 14
    )
    ledger = AvailabilityLedger.build(snapshot((row,), afternoons), {1: week}, {1: 600})
    monday_afternoon, monday_morning = week[4], week[3]

    # Behind pace against all 40 hours, but 16 morning hours still hold the 10 hours:
    # the Evitar afternoon is not necessary and its Evitar is not waived.
    assert ledger.is_necessary(row, monday_afternoon) is False
    assert ledger.needed_evitar(row, monday_afternoon) == frozenset()
    # Outside Evitar the pace rule still applies.
    assert ledger.is_necessary(row, monday_morning) is True

    # On Friday afternoon no morning is left, so the Evitar hour is needed.
    friday_afternoon = week[36]
    assert ledger.is_necessary(row, friday_afternoon) is True
    assert ledger.needed_evitar(row, friday_afternoon) == frozenset({("teacher", 1)})


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


# Risk scenarios R01, R02, R03, R05, R06, R07. Each returned candidate also passes validate_candidate.

R01_TEACHERS = {"R1": 1, "R2": 2, "R3": 3, "M1": 4, "M2": 5, "F1": 6, "F2": 7, "F3": 8, "F4": 9}
R01_WINDOW_END = {"R1": 11, "R2": 11, "R3": 12, "M1": 13, "M2": 13, "L": 11}
# (class, teacher, minutes per week). R1 and R2 are 9h-11h, R3 9h-12h, M1 and M2 9h-13h.
R01_ROWS = (
    (1, "R1", 300),
    (2, "R1", 300),
    (3, "R2", 300),
    (4, "R2", 300),
    (1, "M1", 360),
    (2, "M1", 360),
    (3, "M2", 360),
    (4, "M2", 360),
    (1, "R3", 210),
    (2, "R3", 210),
    (3, "R3", 210),
    (4, "R3", 210),
    (1, "F1", 1290),
    (2, "F2", 1290),
    (3, "F3", 1290),
    (4, "F4", 1290),
)


def r01_case(weeks: int, rows, teachers: dict[str, int]):
    """Each restricted teacher is unavailable from its window end to 18h, every school day."""
    assignments = tuple(
        assignment(
            index,
            teacher_id=teachers[name],
            class_ids=(class_id,),
            minutes=per_week * weeks,
        )
        for index, (class_id, name, per_week) in enumerate(rows, start=1)
    )
    unavailable = tuple(
        row
        for name, end in R01_WINDOW_END.items()
        if name in teachers
        for row in daily(TEACHER, teachers[name], end, 18, weeks)
    )
    return snapshot(assignments, unavailable=unavailable, weeks=weeks), horizon_periods(weeks)


def test_r01_scarce_teachers_are_served_and_the_last_lesson_falls_in_week_12():
    scenario, periods = r01_case(12, R01_ROWS, R01_TEACHERS)

    candidate = construct_schedule(scenario, periods)

    assert candidate is not None
    assert validate_candidate(scenario, candidate).valid is True
    assert max(week_of(lesson) for lesson in candidate.lessons) == 12


def test_r02_pace_keeps_the_scarce_teacher_until_the_last_weeks():
    # Teacher L (9h-11h) gives 2 h per week to class 1; F1 drops to 19.5 h per week.
    rows = tuple(
        (class_id, name, 1170 if name == "F1" else per_week)
        for class_id, name, per_week in (*R01_ROWS, (1, "L", 120))
    )
    teachers = {**R01_TEACHERS, "L": 10}
    scenario, periods = r01_case(12, rows, teachers)

    candidate = construct_schedule(scenario, periods)

    assert candidate is not None
    assert validate_candidate(scenario, candidate).valid is True
    assert max(week_of(lesson) for lesson in candidate.lessons) <= 12
    last_of_l = max(
        week_of(lesson) for lesson in candidate.lessons if lesson.assignment_id == len(rows)
    )
    assert last_of_l >= 10


def test_r03_a_scarce_class_wins_the_morning_over_a_class_with_more_hours():
    # One teacher gives 20 h to class 1 (all day) and 20 h to class 2 (only 9h-13h).
    scenario = snapshot(
        (
            assignment(1, teacher_id=1, class_ids=(1,), minutes=1200),
            assignment(2, teacher_id=1, class_ids=(2,), minutes=1200),
        ),
        unavailable=daily(CLASS, 2, 13, 18),
    )

    candidate = construct_schedule(scenario, horizon_periods(1))

    assert candidate is not None
    assert validate_candidate(scenario, candidate).valid is True
    assert len(candidate.lessons) == 40
    class_two = [lesson for lesson in candidate.lessons if lesson.assignment_id == 2]
    assert len(class_two) == 20
    assert all(lesson.period.start_local.hour < 13 for lesson in class_two)


def test_r05_evitar_is_used_only_as_many_times_as_the_hours_need():
    # 34 h of demand in one week; the teacher's Evitar covers 16h-18h every day (10 blocks).
    scenario = snapshot(
        (assignment(1, teacher_id=1, class_ids=(1,), minutes=34 * 60),),
        soft=daily(TEACHER, 1, 16, 18),
    )

    candidate = construct_schedule(scenario, horizon_periods(1))

    assert candidate is not None
    assert validate_candidate(scenario, candidate).valid is True
    assert len(candidate.lessons) == 34
    inside_evitar = [lesson for lesson in candidate.lessons if lesson.period.start_local.hour >= 16]
    assert len(inside_evitar) == 4


def test_r06_preferred_blocks_take_every_lesson_when_they_have_room():
    # 8 h of demand; the teacher prefers 9h-11h, so 11h-18h is Evitar every day.
    scenario = snapshot(
        (assignment(1, teacher_id=1, class_ids=(1,), minutes=8 * 60),),
        soft=daily(TEACHER, 1, 11, 18),
    )

    candidate = construct_schedule(scenario, horizon_periods(1))

    assert candidate is not None
    assert validate_candidate(scenario, candidate).valid is True
    assert len(candidate.lessons) == 8
    assert all(lesson.period.start_local.hour in (9, 10) for lesson in candidate.lessons)


def test_r07_a_dead_end_caused_by_evitar_is_repaired_by_the_relaxed_pass():
    # T1 (teacher 7): Evitar on Monday and Tuesday, only 9h on Wednesday-Friday.
    # T2 (teacher 8): only 9h on Wednesday-Friday. Both teach class 1, 3 h each.
    scenario = snapshot(
        (
            assignment(1, teacher_id=7, class_ids=(1,), minutes=180),
            assignment(2, teacher_id=8, class_ids=(1,), minutes=180),
        ),
        soft=(block(TEACHER, 7, 0, 9, 18), block(TEACHER, 7, 1, 9, 18)),
        unavailable=(
            *(block(TEACHER, 7, offset, 10, 18) for offset in (2, 3, 4)),
            *(block(TEACHER, 8, offset, 9, 18) for offset in (0, 1)),
            *(block(TEACHER, 8, offset, 10, 18) for offset in (2, 3, 4)),
        ),
    )

    candidate = construct_schedule(scenario, horizon_periods(1))

    assert candidate is not None
    assert validate_candidate(scenario, candidate).valid is True
    first = [lesson for lesson in candidate.lessons if lesson.assignment_id == 1]
    second = [lesson for lesson in candidate.lessons if lesson.assignment_id == 2]
    assert len(first) == 3
    assert all(lesson.period.school_date == MONDAY for lesson in first)
    assert len(second) == 3
    assert all(lesson.period.school_date.weekday() in (2, 3, 4) for lesson in second)


def test_is_avoided_flags_the_evitar_of_the_teacher_or_a_class_and_nothing_else():
    first_day = week_periods()[0]
    by_teacher = assignment(1, teacher_id=1, class_ids=(1,))
    by_class = assignment(2, teacher_id=2, class_ids=(2,))
    neither = assignment(3, teacher_id=3, class_ids=(3,))
    scenario = snapshot(
        (by_teacher, by_class, neither),
        soft=(Unavailability(TEACHER, 1, first_day), Unavailability(CLASS, 2, first_day)),
    )

    assert is_avoided(scenario, by_teacher, first_day) is True
    assert is_avoided(scenario, by_class, first_day) is True
    assert is_avoided(scenario, neither, first_day) is False
