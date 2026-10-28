"""Lab MVP of the weekly template: class-day rules, joint units and Impossivel slots.

The tiny fixture is two classes of two units each, a joint unit for both classes, and four
school weeks. The assertions read observable output: the weekly template placements and the
materialized candidate checked by the independent validator.
"""

from collections import Counter, defaultdict
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

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
from app.scheduler.lab import weekly_template
from app.scheduler.lab.weekly_template import (
    Template,
    _costs,
    _solve_day,
    _spread_counts,
    _week_inputs,
    build_weekly_template,
    generate_weekly_template,
    update_weekly_template,
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
    available = frozenset((weekday, start, end) for weekday in range(5) for start, end in SLOTS) - {
        blocked_slot
    }
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
    counts = _spread_counts(week, targets)
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
    counts = _stage_a_counts(
        _snapshot(presence=presence), {unit.assignment_id: UNIT_MINUTES for unit in UNITS}
    )

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


def test_class_gap_day_costs_at_least_twenty_teacher_gap_hours():
    costs = _costs(_snapshot())
    one_gap_hour = costs["teacher_gaps"] * 60

    assert costs["class_gap_day"] >= 20 * one_gap_hour


def test_rollout_aims_one_week_before_the_target_finish_week():
    result = generate_weekly_template(_snapshot(), _periods(), target_finish=LAST_DAY)

    assert result.stats["target_week"] == (LAST_DAY - ORIGIN).days // 7 - 1


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


def test_stage_b_places_as_many_lessons_as_the_day_allows_instead_of_failing():
    # Lunch keeps one slot empty, so a unit asking for eight lessons on Monday can place six.
    week, _targets = _week_inputs(
        _snapshot(),
        _periods(),
        remaining={1: 2 * UNIT_MINUTES},
        weeks_left=WEEKS,
        previous=frozenset(),
        available=None,
    )

    rows, _status, _variables = _solve_day(week, 0, {1: len(SLOTS) + 1}, seed=1, time_limit=60)

    assert len(rows) == len(SLOTS) - 1


def test_stage_b_keeps_a_class_day_at_zero_or_three_lessons_when_it_cannot_place_them_all():
    # Teacher 1 is free only at 9:00 and 10:10 on Mondays, so unit 1 can place two lessons at most.
    # Two regular lessons would be a class day of one or two lessons, so the day places none.
    teacher_blocks = [
        Unavailability(
            UnavailableResource.TEACHER,
            TEACHER_1,
            normalize_period(ORIGIN + timedelta(weeks=week), start, end, TIMEZONE),
        )
        for week in range(WEEKS)
        for start, end in SLOTS[2:]
    ]
    week, _targets = _week_inputs(
        _snapshot(teacher_blocks),
        _periods(),
        remaining={1: 2 * UNIT_MINUTES},
        weeks_left=WEEKS,
        previous=frozenset(),
        available=None,
    )

    rows, _status, _variables = _solve_day(week, 0, {1: 2}, seed=1, time_limit=60)

    assert rows == []


def test_rollout_resolves_the_template_again_after_each_refresh_period(monkeypatch):
    monkeypatch.setattr(weekly_template, "REFRESH_WEEKS", 1)
    frequent = generate_weekly_template(_snapshot(), _periods(), target_finish=LAST_DAY)
    monkeypatch.setattr(weekly_template, "REFRESH_WEEKS", 100)
    rare = generate_weekly_template(_snapshot(), _periods(), target_finish=LAST_DAY)

    assert frequent.stats["template_solves"] > rare.stats["template_solves"]


def test_stage_a_teacher_day_counts_only_the_slots_the_teacher_can_use():
    # Teacher 1 can use only 9:00, 13:40 and 14:50 on Mondays. Lunch splits three lessons in those
    # slots into presences that are too short, so the teacher takes no lesson that Monday, although
    # three lessons would meet the presence rule on the full grid.
    teacher_blocks = [
        Unavailability(
            UnavailableResource.TEACHER,
            TEACHER_1,
            normalize_period(ORIGIN + timedelta(weeks=week), start, end, TIMEZONE),
        )
        for week in range(WEEKS)
        for start, end in (SLOTS[1], SLOTS[2], SLOTS[3], SLOTS[6])
    ]
    presence = (TeacherPresenceRule(TEACHER_1, True, 180, 60),)
    counts = _stage_a_counts(
        _snapshot(teacher_blocks, presence),
        {unit.assignment_id: UNIT_MINUTES for unit in UNITS},
    )

    monday_lessons = sum(
        count for (unit, day), count in counts.items() if day == 0 and TEACHER_OF[unit] == TEACHER_1
    )
    assert monday_lessons == 0


def test_rollout_resolves_the_template_before_it_places_more_lessons_than_a_unit_has_left(
    monkeypatch,
):
    # Unit 1 has three lessons left and two weeks to finish. Its template places two a week, so in
    # the second week one of its template slots is past its last lesson: the rollout solves again
    # at the start of that week instead of dropping the slot inside the week.
    monkeypatch.setattr(weekly_template, "REFRESH_WEEKS", 100)
    snapshot = replace(_snapshot(), executed_minutes={1: {1: UNIT_MINUTES - 3 * LESSON_MINUTES}})

    result = generate_weekly_template(
        snapshot, _periods(), target_finish=ORIGIN + timedelta(weeks=2)
    )

    assert result.stats["template_solves"] == 2


def test_leftover_fill_completes_units_a_rollout_leaves_unplaced(monkeypatch):
    # A rollout that places no lesson hands every unit's demand to the leftover fill.
    monkeypatch.setattr(
        weekly_template,
        "build_weekly_template",
        lambda *args, **kwargs: Template(frozenset(), 0, 0, 0.0),
    )
    snapshot = _snapshot()

    result = generate_weekly_template(snapshot, _periods(), target_finish=LAST_DAY)

    assert result.status == "COMPLETE"
    assert [v.code for v in validate_candidate(snapshot, result.candidate).violations] == []
    assert result.candidate is not None
    assert sum(row.credit_minutes for row in result.candidate.lessons) == len(UNITS) * UNIT_MINUTES


def test_leftover_fill_keeps_the_weekly_lessons_where_they_are():
    snapshot = _snapshot()
    periods = _periods()
    first, second = SLOTS[0][0], SLOTS[1][0]
    weekly = [
        next(p for p in periods if p.school_date == ORIGIN and p.start_local == start)
        for start in (first, second)
    ]
    placed = {1: [(period, LESSON_MINUTES) for period in weekly]}
    remaining = {
        1: UNIT_MINUTES - 2 * LESSON_MINUTES,
        **{unit.assignment_id: UNIT_MINUTES for unit in UNITS if unit.assignment_id != 1},
    }
    partial = weekly_template._materialize(snapshot, placed, remaining)

    filled = weekly_template._fill_leftover(snapshot, periods, partial, time_limit_seconds=60)

    assert filled is not None
    assert [v.code for v in validate_candidate(snapshot, filled).violations] == []
    kept = {
        (row.period.school_date, row.period.start_local)
        for row in filled.lessons
        if row.assignment_id == 1
    }
    assert {(ORIGIN, first), (ORIGIN, second)} <= kept
    assert sum(row.credit_minutes for row in filled.lessons) == len(UNITS) * UNIT_MINUTES


UPDATE_DAY = ORIGIN + timedelta(weeks=2)


def _published():
    return generate_weekly_template(_snapshot(), _periods(), target_finish=LAST_DAY).candidate


def _update_snapshot(published, *, missed=(), unavailable=()):
    """Update at UPDATE_DAY: published lessons before it are protected, except the missed ones."""
    protected = tuple(
        row
        for row in published.lessons
        if row.period.school_date < UPDATE_DAY and row.lesson_id not in missed
    )
    now = datetime.combine(UPDATE_DAY, time(0), tzinfo=ZoneInfo(TIMEZONE)).astimezone(UTC)
    school_dates = {period.school_date for period in _periods()}
    return replace(
        _snapshot(unavailable),
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        baseline_lessons=published.lessons,
        protected_lessons=protected,
        protected_dates=frozenset(day for day in school_dates if day < UPDATE_DAY),
        now_utc=now,
    )


def test_update_keeps_the_protected_past_and_plans_only_from_the_update_date():
    published = _published()
    snapshot = _update_snapshot(published)

    result = update_weekly_template(snapshot, _periods(), published)

    assert result.status == "COMPLETE"
    assert [v.code for v in validate_candidate(snapshot, result.candidate).violations] == []
    protected = set(snapshot.protected_lessons)
    assert protected <= set(result.candidate.lessons)
    assert all(
        row.period.school_date >= UPDATE_DAY
        for row in result.candidate.lessons
        if row not in protected
    )


def test_update_places_a_missed_lesson_on_or_after_the_update_date():
    published = _published()
    before = [
        row
        for row in published.lessons
        if row.assignment_id == 1 and row.period.school_date < UPDATE_DAY
    ]
    missed = max(before, key=lambda row: row.period.start_utc)
    snapshot = _update_snapshot(published, missed=(missed.lesson_id,))

    result = update_weekly_template(snapshot, _periods(), published)

    assert result.status == "COMPLETE"
    assert [v.code for v in validate_candidate(snapshot, result.candidate).violations] == []
    protected_ids = {row.lesson_id for row in snapshot.protected_lessons}
    debt = [
        row
        for row in result.candidate.lessons
        if row.assignment_id == 1 and row.lesson_id not in protected_ids
    ]
    # The missed lesson is one of the unit's lessons before the update; the rest stay protected.
    assert (
        sum(row.credit_minutes for row in debt) == UNIT_MINUTES - (len(before) - 1) * LESSON_MINUTES
    )
    assert min(row.period.school_date for row in debt) >= UPDATE_DAY


def test_update_keeps_the_published_lessons_of_a_week_that_a_change_does_not_touch():
    published = _published()
    week_three = ORIGIN + timedelta(weeks=3)
    blocked = tuple(
        Unavailability(
            UnavailableResource.TEACHER,
            TEACHER_1,
            normalize_period(week_three + timedelta(days=day), start, end, TIMEZONE),
        )
        for day in range(5)
        for start, end in SLOTS
    )
    snapshot = _update_snapshot(published, unavailable=blocked)

    result = update_weekly_template(snapshot, _periods(), published)

    assert result.status == "COMPLETE"
    assert [v.code for v in validate_candidate(snapshot, result.candidate).violations] == []
    week_two = range(0, 7)
    published_week_two = {
        (row.assignment_id, row.period.school_date, row.period.start_local)
        for row in published.lessons
        if (row.period.school_date - UPDATE_DAY).days in week_two
    }
    updated = {
        (row.assignment_id, row.period.school_date, row.period.start_local)
        for row in result.candidate.lessons
    }
    assert published_week_two <= updated
