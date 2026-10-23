"""Same-day compaction of class days (owner rules, 23 Oct 2026)."""

from datetime import date, time
from types import SimpleNamespace

from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    GridSlot,
    LunchRule,
    PlanningSnapshot,
    ScheduledLesson,
    SchedulingStrategy,
    Unavailability,
    UnavailableResource,
)
from app.scheduler.domain.class_day_gaps import (
    CLASS_DAY_EXCESS_UNIT,
    TOLERATED_CLASS_DAY_GAP_MINUTES,
    class_day_excess_cost,
    class_day_excess_minutes,
    class_day_excess_value,
)
from app.scheduler.domain.priorities import (
    DEFAULT_LEVELS,
    PRIORITY_MULTIPLIERS,
    UNIT_COSTS,
    PriorityWeights,
)
from app.scheduler.domain.projection import ModuleRequirement, ModuleSlice
from app.scheduler.infrastructure import class_day_compaction
from app.scheduler.infrastructure.class_day_compaction import compact_class_days

TZ = "Europe/Lisbon"
MONDAY = date(2026, 9, 14)
# One Monday: 9h, 10h, 11h, then lunch 12h-14h, then 14h and 15h.
HOURS = (8, 9, 10, 11, 14, 15)
LUNCH = LunchRule(time(12), time(14), 60)


def weights(**changes):
    levels = dict(DEFAULT_LEVELS)
    levels.update(changes)
    return PriorityWeights(levels)


def grid():
    return tuple(GridSlot(0, time(hour), time(hour + 1)) for hour in HOURS)


def window(hour, length=1):
    return normalize_period(MONDAY, time(hour), time(hour + length), TZ)


def assignment(identity, class_ids, teacher_id, room_id, hours=1):
    return Assignment(
        identity,
        tuple(class_ids),
        identity,
        teacher_id,
        frozenset({room_id}),
        (ModuleRequirement(identity * 10, 1, 60 * hours),),
    )


def lesson(lesson_id, assignment_row, hour, room_id, *, teacher_id=None):
    period = window(hour)
    module_id = assignment_row.modules[0].module_id
    return ScheduledLesson(
        lesson_id,
        assignment_row.assignment_id,
        period,
        room_id,
        60,
        (ModuleSlice(lesson_id, module_id, 0, 60),),
        teacher_id=teacher_id,
        class_ids=assignment_row.class_ids,
    )


def snapshot(assignments, *, soft=(), unavailable=()):
    return PlanningSnapshot(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=MONDAY,
        preferred_end_date=MONDAY,
        hard_end_date=MONDAY,
        timezone_name=TZ,
        grid_slots=grid(),
        assignments=tuple(assignments),
        executed_minutes={},
        blocked_dates=frozenset(),
        unavailable=tuple(unavailable),
        soft_unavailable=tuple(soft),
        lunch_rule=LUNCH,
    )


def times_by_lesson(candidate):
    return {row.lesson_id: row.period.start_local.hour for row in candidate.lessons}


def tdes_day(extra_assignments=(), extra_lessons=()):
    """Class 1 Monday: 9h lesson, two empty hours, lunch, then two afternoon lessons."""
    first = assignment(1, (1,), teacher_id=1, room_id=101)
    second = assignment(2, (1,), teacher_id=2, room_id=102)
    third = assignment(3, (1,), teacher_id=3, room_id=103)
    rows = (first, second, third, *extra_assignments)
    lessons = (
        lesson(1, first, 9, 101),
        lesson(2, second, 14, 102),
        lesson(3, third, 15, 103),
        *extra_lessons,
    )
    return snapshot(rows), CandidateSchedule(lessons)


def test_excess_minutes_tolerate_one_gap_hour_per_class_day():
    assert TOLERATED_CLASS_DAY_GAP_MINUTES == 60
    assert [class_day_excess_minutes(minutes) for minutes in (0, 60, 61, 120, 180)] == [
        0,
        0,
        1,
        60,
        120,
    ]


def test_excess_cost_outweighs_a_slight_teacher_cost_at_the_highest_levels():
    slight_teacher_cost = PRIORITY_MULTIPLIERS[4] * (
        UNIT_COSTS["teacher_gaps"] * 60 + UNIT_COSTS["teacher_preferences"] * 60
    )

    assert class_day_excess_cost(60) == 0
    assert class_day_excess_cost(120) > slight_teacher_cost


def test_compaction_moves_the_first_lesson_into_the_gap_when_the_teacher_is_free():
    school, candidate = tdes_day()

    compacted = compact_class_days(school, candidate, weights())

    assert times_by_lesson(compacted) == {1: 11, 2: 14, 3: 15}


def test_compaction_keeps_the_lesson_when_the_teacher_is_busy_at_every_empty_hour():
    # Teacher 1 teaches another class at 10h and 11h, so the 9h lesson has no free target.
    other = assignment(4, (2,), teacher_id=1, room_id=104, hours=2)
    busy = (lesson(10, other, 10, 104), lesson(11, other, 11, 104))
    school, candidate = tdes_day(extra_assignments=(other,), extra_lessons=busy)

    compacted = compact_class_days(school, candidate, weights())

    assert compacted is candidate


def test_joint_lesson_is_not_split_when_one_member_class_is_busy():
    joint = assignment(1, (1, 2), teacher_id=1, room_id=101)
    class_two_at_ten = assignment(2, (2,), teacher_id=4, room_id=102)
    class_two_at_eleven = assignment(3, (2,), teacher_id=5, room_id=103)
    second = assignment(4, (1,), teacher_id=2, room_id=104)
    third = assignment(5, (1,), teacher_id=3, room_id=105)
    school = snapshot((joint, class_two_at_ten, class_two_at_eleven, second, third))
    candidate = CandidateSchedule(
        (
            lesson(1, joint, 9, 101),
            lesson(2, class_two_at_ten, 10, 102),
            lesson(3, class_two_at_eleven, 11, 103),
            lesson(4, second, 14, 104),
            lesson(5, third, 15, 105),
        )
    )

    compacted = compact_class_days(school, candidate, weights())

    joint_after = next(row for row in compacted.lessons if row.lesson_id == 1)
    assert joint_after.period.start_local.hour == 9
    assert joint_after.class_ids == (1, 2)


def test_move_is_rejected_when_the_teacher_evitar_costs_more_than_the_gap_saved():
    # Class 1 has one empty hour (10h): tolerated, so a move only saves the gap cost.
    # Both teachers want no lesson at 10h, and that Evitar costs more than the gap saved.
    first = assignment(1, (1,), teacher_id=1, room_id=101)
    second = assignment(2, (1,), teacher_id=2, room_id=102)
    school = snapshot(
        (first, second),
        soft=(
            Unavailability(UnavailableResource.TEACHER, 1, window(10)),
            Unavailability(UnavailableResource.TEACHER, 2, window(10)),
        ),
    )
    candidate = CandidateSchedule((lesson(1, first, 9, 101), lesson(2, second, 11, 102)))

    compacted = compact_class_days(school, candidate, weights())

    assert compacted is candidate


def test_invalid_compacted_candidate_falls_back_to_the_uncompacted_one(monkeypatch):
    school, candidate = tdes_day()
    monkeypatch.setattr(
        class_day_compaction,
        "validate_candidate",
        lambda _snapshot, _candidate: SimpleNamespace(valid=False, violations=()),
    )

    compacted = compact_class_days(school, candidate, weights())

    assert compacted is candidate


def test_move_is_rejected_when_the_teacher_gap_grows_even_if_the_class_excess_falls():
    # Teacher 1 teaches class 2 at 8h. Moving class 1's 9h lesson to 10h or 11h opens
    # a teacher gap, so the move is refused although it removes the class excess.
    first = assignment(1, (1,), teacher_id=1, room_id=101)
    second = assignment(2, (1,), teacher_id=2, room_id=102)
    third = assignment(3, (1,), teacher_id=3, room_id=103)
    other = assignment(4, (2,), teacher_id=1, room_id=104)
    school = snapshot((first, second, third, other))
    candidate = CandidateSchedule(
        (
            lesson(1, first, 9, 101),
            lesson(2, second, 14, 102),
            lesson(3, third, 15, 103),
            lesson(4, other, 8, 104),
        )
    )

    compacted = compact_class_days(school, candidate, weights())

    assert times_by_lesson(compacted)[1] == 9


def test_class_day_excess_value_rewards_each_excess_minute_removed():
    slots = tuple(GridSlot(0, time(hour), time(hour + 1)) for hour in range(9, 14))
    # Classes 9-10h and 13-14h: 180 empty minutes, 120 of them excess.
    # A lesson at 11-12h leaves 120 empty minutes, 60 of them excess: 60 minutes removed.
    intervals = [(540, 600), (780, 840)]

    value = class_day_excess_value([intervals], (660, 720), slots, None)

    assert value == 60 * CLASS_DAY_EXCESS_UNIT
