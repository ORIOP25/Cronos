"""A teacher with a presence minimum is constructed without the exact model.

Iris rule: at least three hours per presence, a free lunch and at most one hour
of gap. Greedy construction must book a whole presence run, so the constructive
route (and the adaptive recovery that relies on it) completes the schedule.
"""

from collections import Counter
from dataclasses import replace
from datetime import time, timedelta

from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import (
    GridSlot,
    LunchRule,
    SchedulingStrategy,
    TeacherPresenceRule,
    Unavailability,
    UnavailableResource,
)
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.infrastructure import search
from app.scheduler.infrastructure.constructive import construct_schedule
from app.scheduler.infrastructure.search import search_adaptive_schedule
from app.scheduler.lab.recovery import laboratory_policy
from app.scheduler.lab.typology import build_typology_fixture
from tests.unit.test_scheduler_availability_priority_v1 import (
    MONDAY,
    TEACHER,
    TZ,
    assignment,
    block,
    period,
    snapshot,
)

IRIS_TEACHER_ID = 1001
LUNCH_RULE = LunchRule(time(12), time(14), 60)


def iris_rule(*, lunch_required: bool) -> TeacherPresenceRule:
    return TeacherPresenceRule(
        teacher_id=IRIS_TEACHER_ID,
        lunch_required=lunch_required,
        minimum_minutes=180,
        max_gap_minutes=60,
    )


def test_a_presence_with_a_lunch_break_books_a_full_run_in_construction():
    fixture = build_typology_fixture(12)
    snapshot = replace(
        fixture.snapshot, teacher_presence=(iris_rule(lunch_required=True),), lunch_rule=LUNCH_RULE
    )

    candidate = construct_schedule(snapshot, fixture.periods)

    assert candidate is not None
    assert validate_candidate(snapshot, candidate).valid is True


def test_a_presence_without_lunch_books_a_full_run_in_construction():
    fixture = build_typology_fixture(12)
    snapshot = replace(
        fixture.snapshot, teacher_presence=(iris_rule(lunch_required=False),), lunch_rule=LUNCH_RULE
    )

    candidate = construct_schedule(snapshot, fixture.periods)

    assert candidate is not None
    assert validate_candidate(snapshot, candidate).valid is True


def test_adaptive_recovery_repairs_a_presence_rule_without_the_exact_model(monkeypatch):
    fixture = build_typology_fixture(12)
    snapshot = replace(
        fixture.snapshot,
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        baseline_lessons=fixture.witness.lessons,
        teacher_presence=(iris_rule(lunch_required=True),),
        lunch_rule=LUNCH_RULE,
    )

    def exact_model_must_not_run(*_args, **_kwargs):
        raise AssertionError("The exact placement model must not run.")

    monkeypatch.setattr(search, "solve_placement", exact_model_must_not_run)

    outcome = search_adaptive_schedule(
        snapshot,
        fixture.periods,
        fixture.witness,
        laboratory_policy(snapshot),
        time_limit_seconds=300,
        stop_at_first_complete=True,
    )

    assert outcome.status == "COMPLETE"
    assert validate_candidate(snapshot, outcome.candidate).valid is True


def test_a_presence_run_respects_evitar_net_of_its_planned_lessons():
    """A run's later lesson inside the teacher's Evitar must pass T08 net of the run's earlier lessons.

    Teacher 1 teaches class 1 (assignment 1) and class 2 (assignment 2), one hour each,
    and prefers 09-10 to be free, so 09-10 is Evitar. A presence needs two hours with no
    gap. Once the 08-09 lesson is credited, the teacher's remaining demand equals the
    neutral capacity from 09-10, so 09-10 is refused and the presence is 09-11.
    """
    monday_grid = tuple(GridSlot(0, time(hour), time(hour + 1)) for hour in (8, 9, 10))
    periods = tuple(normalize_period(MONDAY, time(hour), time(hour + 1), TZ) for hour in (8, 9, 10))
    first = assignment(1, teacher_id=1, class_ids=(1,))
    second = assignment(2, teacher_id=1, class_ids=(2,))
    scenario = replace(
        snapshot((first, second), soft=(block(TEACHER, 1, 0, 9, 10),)),
        grid_slots=monday_grid,
        teacher_presence=(
            TeacherPresenceRule(
                teacher_id=1, lunch_required=False, minimum_minutes=120, max_gap_minutes=0
            ),
        ),
    )

    candidate = construct_schedule(scenario, periods)

    assert candidate is not None
    assert validate_candidate(scenario, candidate).valid is True
    booked = sorted(
        (lesson.period.start_local.hour, lesson.assignment_id) for lesson in candidate.lessons
    )
    assert booked == [(9, 1), (10, 2)]


def test_a_presence_extension_never_strands_fewer_minutes_than_the_minimum():
    """Teacher 1 needs a three-hour presence and the grid offers four hours a day.

    Six one-hour lessons over two days fit as 3 + 3. Extending the first presence to
    four hours would strand two lessons that can never form a presence of their own.
    """
    hours = (9, 10, 11, 12)
    scenario = replace(
        snapshot((assignment(1, teacher_id=1, class_ids=(1,), minutes=360),)),
        grid_slots=tuple(
            GridSlot(day, time(hour), time(hour + 1)) for day in (0, 1) for hour in hours
        ),
        teacher_presence=(
            TeacherPresenceRule(
                teacher_id=1, lunch_required=False, minimum_minutes=180, max_gap_minutes=0
            ),
        ),
    )
    periods = tuple(period(day, hour) for day in (0, 1) for hour in hours)

    candidate = construct_schedule(scenario, periods)

    assert candidate is not None
    assert validate_candidate(scenario, candidate).valid is True
    lessons_per_day = Counter(lesson.period.school_date for lesson in candidate.lessons)
    assert [lessons_per_day[MONDAY], lessons_per_day[MONDAY + timedelta(days=1)]] == [3, 3]


def test_a_presence_never_leaves_hours_that_no_valid_presence_can_hold():
    # Nine hours for a teacher with a 3-hour minimum and at most 4 hours per presence:
    # booking 4 hours first would strand 5 hours, which no presence split can teach.
    row = assignment(1, teacher_id=IRIS_TEACHER_ID, class_ids=(1,), minutes=540)
    school = replace(
        snapshot((row,)),
        teacher_presence=(iris_rule(lunch_required=True),),
        lunch_rule=LUNCH_RULE,
    )
    periods = tuple(
        period(day, hour) for day in range(5) for hour in (9, 10, 11, 12, 14, 15, 16, 17)
    )

    candidate = construct_schedule(school, periods)

    assert candidate is not None
    assert validate_candidate(school, candidate).valid is True


def test_a_presence_lesson_that_cannot_complete_does_not_block_its_class_mates():
    """A presence lesson that cannot complete its run must not keep its class's period.

    Assignment 1 needs a two-hour presence of teacher 1, who has no other lesson on
    Monday, so its Monday 09 lesson is dropped. Assignment 2 (teacher 2, same class)
    can teach Monday 09 instead. Teacher 1 then teaches Tuesday 09 and 10 for
    assignments 1 and 3, a valid two-hour presence.
    """
    monday, tuesday, tuesday_late = period(0, 9), period(1, 9), period(1, 10)
    target = replace(
        snapshot(
            (
                assignment(1, teacher_id=1, class_ids=(1,)),
                assignment(2, teacher_id=2, class_ids=(1,)),
                assignment(3, teacher_id=1, class_ids=(2,)),
            ),
            unavailable=(
                Unavailability(UnavailableResource.CLASS, 1, tuesday_late),
                Unavailability(UnavailableResource.CLASS, 2, monday),
            ),
        ),
        teacher_presence=(
            TeacherPresenceRule(
                teacher_id=1, lunch_required=False, minimum_minutes=120, max_gap_minutes=0
            ),
        ),
    )

    candidate = construct_schedule(target, (monday, tuesday, tuesday_late))

    assert candidate is not None
    assert validate_candidate(target, candidate).valid is True
    monday_nine = [
        row.assignment_id
        for row in candidate.lessons
        if row.period.school_date == monday.school_date and row.period.start_local.hour == 9
    ]
    assert monday_nine == [2]
