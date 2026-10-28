"""Lab MVP of the weekly template: class-day rules, joint units and Impossivel slots.

The tiny fixture is two classes of two units each, a joint unit for both classes, and four
school weeks. The assertions read observable output: the weekly template placements and the
materialized candidate checked by the independent validator.
"""

from collections import Counter, defaultdict
from datetime import date, time, timedelta

from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import (
    Assignment,
    GridSlot,
    LunchRule,
    PlanningSnapshot,
    SchedulingStrategy,
    TeacherPresenceRule,
    Unavailability,
    UnavailableResource,
)
from app.scheduler.domain.candidate_validation import (
    ValidationViolationCode,
    validate_candidate,
)
from app.scheduler.domain.projection import ModuleRequirement
from app.scheduler.lab.weekly_template import (
    _costs,
    _spread_counts,
    _week_inputs,
    build_weekly_template,
    generate_weekly_template,
)

TIMEZONE = "Europe/Lisbon"
ORIGIN = date(2026, 3, 2)  # a Monday
WEEKS = 4
LAST_DAY = ORIGIN + timedelta(weeks=WEEKS, days=-3)
SLOTS = (
    (time(9), time(10)),
    (time(10, 10), time(11, 10)),
    (time(11, 20), time(12, 20)),
    (time(12, 30), time(13, 30)),
    (time(13, 40), time(14, 40)),
    (time(14, 50), time(15, 50)),
    (time(16), time(17)),
)
LUNCH_SLOT = SLOTS[3]
LUNCH = LunchRule(time(12), time(14, 30), 60)
ROOMS = frozenset({10, 11, 12})
LESSON_MINUTES = 60
UNIT_MINUTES = 8 * LESSON_MINUTES
CLASS_1, CLASS_2 = 1, 2
JOINT_UNIT = 5


def _unit(assignment_id, class_ids, teacher_id):
    return Assignment(
        assignment_id=assignment_id,
        class_ids=class_ids,
        subject_id=assignment_id,
        teacher_id=teacher_id,
        eligible_room_ids=ROOMS,
        modules=(ModuleRequirement(assignment_id, 1, UNIT_MINUTES),),
    )


UNITS = (
    _unit(1, (CLASS_1,), 1),
    _unit(2, (CLASS_1,), 2),
    _unit(3, (CLASS_2,), 3),
    _unit(4, (CLASS_2,), 1),
    _unit(JOINT_UNIT, (CLASS_1, CLASS_2), 4),
)
CLASSES_OF = {unit.assignment_id: unit.class_ids for unit in UNITS}
TEACHER_OF = {unit.assignment_id: unit.teacher_id for unit in UNITS}
TEACHER_1 = 1  # Teaches units 1 and 4.


def _periods():
    return tuple(
        normalize_period(ORIGIN + timedelta(weeks=week, days=day), start, end, TIMEZONE)
        for week in range(WEEKS)
        for day in range(5)
        for start, end in SLOTS
    )


def _snapshot(unavailable=(), presence=()):
    return PlanningSnapshot(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=ORIGIN,
        preferred_end_date=LAST_DAY,
        hard_end_date=LAST_DAY,
        timezone_name=TIMEZONE,
        grid_slots=tuple(GridSlot(day, start, end) for day in range(5) for start, end in SLOTS),
        assignments=UNITS,
        executed_minutes={},
        blocked_dates=frozenset(),
        unavailable=tuple(unavailable),
        lunch_rule=LUNCH,
        teacher_presence=tuple(presence),
    )


def _template(snapshot):
    return build_weekly_template(
        snapshot,
        _periods(),
        remaining={unit.assignment_id: UNIT_MINUTES for unit in UNITS},
        weeks_left=WEEKS,
    )


def _class_days(placements):
    """Lesson start indexes per (class, weekday) from (unit, weekday, start, end) rows."""
    days = defaultdict(list)
    for unit, weekday, start, _end in placements:
        for class_id in CLASSES_OF[unit]:
            days[(class_id, weekday)].append(SLOTS.index((start, _end)))
    return days


def test_template_class_days_hold_three_or_more_lessons_and_one_gap_at_most():
    template = _template(_snapshot())

    assert template.placements
    for (class_id, weekday), indexes in _class_days(template.placements).items():
        lessons = len(indexes)
        assert 3 <= lessons <= 8, (class_id, weekday, lessons)
        assert LUNCH_SLOT not in [SLOTS[index] for index in indexes]
        internal_gaps = [
            index
            for index in range(min(indexes), max(indexes))
            if index not in indexes and SLOTS[index] != LUNCH_SLOT
        ]
        assert len(internal_gaps) <= 1, (class_id, weekday, internal_gaps)


def test_joint_unit_occupies_the_same_slot_for_every_member_class():
    template = _template(_snapshot())
    joint_slots = {
        (weekday, start, end)
        for unit, weekday, start, end in template.placements
        if unit == JOINT_UNIT
    }
    member_classes = set(CLASSES_OF[JOINT_UNIT])

    assert joint_slots
    for unit, weekday, start, end in template.placements:
        if unit != JOINT_UNIT and member_classes & set(CLASSES_OF[unit]):
            assert (weekday, start, end) not in joint_slots


def test_impossible_weekly_slot_is_never_used_for_the_blocked_class():
    fridays = [
        normalize_period(
            ORIGIN + timedelta(weeks=week, days=4), time(14, 50), time(15, 50), TIMEZONE
        )
        for week in range(WEEKS)
    ]
    blocked = [Unavailability(UnavailableResource.CLASS, CLASS_1, period) for period in fridays]
    snapshot = _snapshot(blocked)

    template = _template(snapshot)
    assert not [
        row
        for row in template.placements
        if CLASS_1 in CLASSES_OF[row[0]] and row[1] == 4 and (row[2], row[3]) == SLOTS[5]
    ]

    result = generate_weekly_template(snapshot, _periods(), target_finish=LAST_DAY)
    assert not [
        lesson
        for lesson in result.candidate.lessons
        if CLASS_1 in CLASSES_OF[lesson.assignment_id]
        and lesson.period.school_date.weekday() == 4
        and lesson.period.start_local == time(14, 50)
    ]


def test_generated_candidate_is_valid_and_finishes_every_unit_by_target():
    snapshot = _snapshot()
    result = generate_weekly_template(snapshot, _periods(), target_finish=LAST_DAY)

    report = validate_candidate(snapshot, result.candidate)
    assert [violation.code for violation in report.violations] == []
    assert report.total_credit_minutes == len(UNITS) * UNIT_MINUTES
    assert ValidationViolationCode.COVERAGE_MISMATCH not in {v.code for v in report.violations}


def test_tail_unit_finishes_its_last_two_lessons_on_a_short_class_day():
    template = build_weekly_template(
        _snapshot(), _periods(), remaining={1: 2 * LESSON_MINUTES}, weeks_left=1
    )

    assert len(template.placements) == 2
    assert {unit for unit, *_slot in template.placements} == {1}


def test_short_class_days_hold_only_units_finishing_their_last_lessons():
    remaining = {1: 2 * LESSON_MINUTES, 2: UNIT_MINUTES, 3: UNIT_MINUTES, 4: UNIT_MINUTES}
    template = build_weekly_template(_snapshot(), _periods(), remaining=remaining, weeks_left=WEEKS)

    units_by_class_day = defaultdict(list)
    for unit, weekday, _start, _end in template.placements:
        for class_id in CLASSES_OF[unit]:
            units_by_class_day[(class_id, weekday)].append(unit)
    assert sum(1 for unit, *_slot in template.placements if unit == 1) == 2
    for key, units in units_by_class_day.items():
        if len(units) <= 2:
            assert set(units) <= {1}, key


def test_stage_b_keeps_class_gaps_at_most_one_on_a_restricted_week():
    blocked_slot = (2, SLOTS[1][0], SLOTS[1][1])
    available = frozenset(
        (weekday, start, end) for weekday in range(5) for start, end in SLOTS
    ) - {blocked_slot}
    template = build_weekly_template(
        _snapshot(),
        _periods(),
        remaining={unit.assignment_id: UNIT_MINUTES for unit in UNITS},
        weeks_left=WEEKS,
        available=available,
    )

    assert template.placements
    assert not [row for row in template.placements if row[1:] == blocked_slot]
    for (class_id, weekday), indexes in _class_days(template.placements).items():
        internal_gaps = [
            index
            for index in range(min(indexes), max(indexes))
            if index not in indexes and SLOTS[index] != LUNCH_SLOT
        ]
        assert len(internal_gaps) <= 1, (class_id, weekday, internal_gaps)


def test_holiday_week_moves_its_lessons_onto_school_days():
    for offset in range(5):
        holiday = ORIGIN + timedelta(days=offset)
        periods = tuple(period for period in _periods() if period.school_date != holiday)

        result = generate_weekly_template(_snapshot(), periods, target_finish=LAST_DAY)

        assert result.stats["skipped_placements"].get("no_school_date", 0) == 0, holiday
        assert all(lesson.period.school_date != holiday for lesson in result.candidate.lessons)


def _stage_a_counts(snapshot, remaining):
    """Stage A counts for one full week, with the class and teacher repairs applied."""
    week, targets = _week_inputs(
        snapshot,
        _periods(),
        remaining=remaining,
        weeks_left=WEEKS,
        previous=frozenset(),
        available=None,
    )
    counts, _shortfall = _spread_counts(week, targets, {})
    return counts


def test_stage_a_class_days_hold_zero_or_three_lessons():
    counts = _stage_a_counts(_snapshot(), {unit.assignment_id: UNIT_MINUTES for unit in UNITS})

    assert counts
    for class_id in (CLASS_1, CLASS_2):
        for weekday in range(5):
            total = sum(
                count
                for (unit, day), count in counts.items()
                if day == weekday and class_id in CLASSES_OF[unit]
            )
            assert total == 0 or total >= 3, (class_id, weekday, total)


def test_stage_a_teacher_days_hold_a_total_the_presence_rule_allows():
    presence = (TeacherPresenceRule(TEACHER_1, True, 180, 60),)
    counts = _stage_a_counts(_snapshot(presence=presence), {unit.assignment_id: UNIT_MINUTES for unit in UNITS})

    for weekday in range(5):
        total = sum(
            count
            for (unit, day), count in counts.items()
            if day == weekday and TEACHER_OF[unit] == TEACHER_1
        )
        assert total == 0 or total >= 3, (weekday, total)


def _teacher_day_counts(placements):
    """Lesson count per (teacher, weekday) of one weekly template."""
    return Counter((TEACHER_OF[unit], weekday) for unit, weekday, _start, _end in placements)


def test_teacher_single_lesson_day_joins_another_lesson_of_the_same_teacher():
    # Unit 1 has one tail lesson; unit 4, taught by the same teacher, has lessons on other days.
    remaining = {1: LESSON_MINUTES, 2: LESSON_MINUTES, 4: 6 * LESSON_MINUTES}
    template = build_weekly_template(_snapshot(), _periods(), remaining=remaining, weeks_left=2)

    assert template.placements
    single_days = [
        key
        for key, count in _teacher_day_counts(template.placements).items()
        if count == 1 and key[0] == TEACHER_1
    ]
    assert single_days == []


def test_teacher_single_lesson_day_costs_more_than_one_teacher_gap_hour():
    costs = _costs(_snapshot())
    single_day = costs["teacher_single_lessons"] * LESSON_MINUTES
    one_gap_hour = costs["teacher_gaps"] * 60

    assert single_day > one_gap_hour


def test_stage_b_teacher_presence_rule_rejects_a_split_below_the_minimum():
    # The teacher is blocked at 9:00, 14:50 and 16:00 on every day, so the only 3-lesson day
    # (10:10, 11:20, 13:40) splits around lunch into 2 + 1 lessons, below the 3-hour minimum.
    teacher_blocks = [
        Unavailability(
            UnavailableResource.TEACHER,
            TEACHER_1,
            normalize_period(ORIGIN + timedelta(weeks=week, days=day), start, end, TIMEZONE),
        )
        for week in range(WEEKS)
        for day in range(5)
        for start, end in (SLOTS[0], SLOTS[5], SLOTS[6])
    ]
    presence = (TeacherPresenceRule(TEACHER_1, True, 180, 60),)
    snapshot = _snapshot(teacher_blocks, presence)

    result = generate_weekly_template(snapshot, _periods(), target_finish=LAST_DAY)

    report = validate_candidate(snapshot, result.candidate)
    assert ValidationViolationCode.TEACHER_PRESENCE_VIOLATION not in {
        violation.code for violation in report.violations
    }
