"""Schedule priority measurements and integer cost (S3, R11-R14)."""

from dataclasses import replace
from datetime import date, time, timedelta

from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    GridSlot,
    LunchRule,
    PlanningSnapshot,
    ScheduledLesson,
    SchedulingStrategy,
    TeacherPresenceRule,
)
from app.scheduler.domain.priorities import CRITERION_KEYS, DEFAULT_LEVELS, PriorityWeights
from app.scheduler.domain.priority_metrics import measure_priority_metrics, priority_cost
from app.scheduler.domain.projection import ModuleRequirement

TZ = "Europe/Lisbon"
ORIGIN = date(2026, 9, 1)


def assignment(identity: int, *, class_id: int = 1, subject_id: int = 1) -> Assignment:
    return Assignment(
        identity,
        (class_id,),
        subject_id,
        1,
        frozenset({1}),
        (ModuleRequirement(identity, 1, 600),),
    )


def lesson(identity: int, assignment_id: int, day: date, hour: int) -> ScheduledLesson:
    period = normalize_period(day, time(hour), time(hour + 1), TZ)
    return ScheduledLesson(identity, assignment_id, period, 1, 60, ())


def snapshot(assignments, *, end: date, blocked=(), presence=(), lunch=None):
    return PlanningSnapshot(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=ORIGIN,
        preferred_end_date=end,
        hard_end_date=end,
        timezone_name=TZ,
        grid_slots=(
            GridSlot(0, time(9), time(10)),
            GridSlot(0, time(15), time(16)),
        ),
        assignments=tuple(assignments),
        executed_minutes={},
        blocked_dates=frozenset(blocked),
        unavailable=(),
        lunch_rule=lunch,
        teacher_presence=tuple(presence),
    )


def test_single_lesson_turns_follow_lunch_and_presence_rules():
    monday = date(2026, 9, 7)
    assignments = (assignment(1),)
    candidate = CandidateSchedule((lesson(1, 1, monday, 9), lesson(2, 1, monday, 15)))
    school = snapshot(
        assignments,
        end=monday,
        lunch=LunchRule(time(12), time(14), 30),
    )

    assert measure_priority_metrics(school, candidate)["teacher_single_lessons"] == 2
    assert measure_priority_metrics(
        replace(school, teacher_presence=(TeacherPresenceRule(1, lunch_required=False),)),
        candidate,
    )["teacher_single_lessons"] == 0
    assert measure_priority_metrics(
        replace(
            school,
            teacher_presence=(TeacherPresenceRule(1, minimum_minutes=120, max_gap_minutes=60),),
        ),
        candidate,
    )["teacher_single_lessons"] == 0
    assert measure_priority_metrics(school, candidate)["class_single_lessons"] == 2


def test_weekly_stability_skips_a_blocked_class_day():
    mondays = (date(2026, 9, 7), date(2026, 9, 14), date(2026, 9, 21))
    assignments = (assignment(1, subject_id=1), assignment(2, subject_id=2))
    candidate = CandidateSchedule(
        (lesson(1, 1, mondays[0], 9), lesson(2, 2, mondays[1], 9))
    )
    school = snapshot(assignments, end=mondays[2], blocked=(mondays[2],))

    assert measure_priority_metrics(school, candidate)["weekly_stability"] == 1


def test_subject_pace_is_the_sum_of_class_completion_spreads():
    day_10 = ORIGIN + timedelta(days=10)
    day_30 = ORIGIN + timedelta(days=30)
    assignments = (
        assignment(1, class_id=1, subject_id=1),
        assignment(2, class_id=1, subject_id=2),
        assignment(3, class_id=2, subject_id=3),
        assignment(4, class_id=2, subject_id=4),
    )
    candidate = CandidateSchedule(
        (
            lesson(1, 1, day_10, 9),
            lesson(2, 2, day_30, 9),
            lesson(3, 3, day_10, 9),
            lesson(4, 4, day_30, 9),
        )
    )

    first_class = measure_priority_metrics(
        snapshot(assignments[:2], end=day_30), CandidateSchedule(candidate.lessons[:2])
    )
    both_classes = measure_priority_metrics(snapshot(assignments, end=day_30), candidate)

    assert first_class["subject_pace"] == 20
    assert both_classes["subject_pace"] == 40


def test_priority_cost_is_integer_and_weights_only_the_selected_criterion():
    monday = date(2026, 9, 7)
    candidate = CandidateSchedule((lesson(1, 1, monday, 9),))
    school = snapshot((assignment(1),), end=monday)
    metrics = measure_priority_metrics(school, candidate)
    ignored = PriorityWeights({key: 0 for key in CRITERION_KEYS})
    metrics["class_gaps"] = 60
    class_gaps = dict(ignored.to_dict(), class_gaps=2)
    stronger_class_gaps = dict(class_gaps, class_gaps=3)

    assert priority_cost(metrics, ignored, origin=school.origin) == 0
    class_gaps_cost = priority_cost(metrics, PriorityWeights(class_gaps), origin=school.origin)
    stronger_class_gaps_cost = priority_cost(
        metrics, PriorityWeights(stronger_class_gaps), origin=school.origin
    )
    assert stronger_class_gaps_cost - class_gaps_cost == 2 * metrics["class_gaps"]
    assert type(class_gaps_cost) is int
