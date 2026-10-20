"""Schedule priority measurements and integer cost (S3, R11-R14)."""

from dataclasses import replace
from datetime import date, time, timedelta

import pytest

from app.scheduler.application.publishing import recovery_proposal_payload
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
from app.scheduler.domain.candidate_validation import ValidationReport
from app.scheduler.domain.priorities import CRITERION_KEYS, PriorityWeights
from app.scheduler.domain.priority_metrics import measure_priority_metrics, priority_cost
from app.scheduler.domain.projection import ModuleRequirement, ModuleSlice
from app.scheduler.domain.recovery import (
    InitialQualityMetrics,
    RecoveryPolicy,
    RecoveryQualityMetrics,
    measure_disruption,
)

TZ = "Europe/Lisbon"
ORIGIN = date(2026, 9, 1)
RECOVERY_POLICY = RecoveryPolicy("test", (1,), 1, 1, 1, 1, 1, 0, 0, 0)


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
    return ScheduledLesson(
        identity,
        assignment_id,
        period,
        1,
        60,
        (ModuleSlice(identity, assignment_id, 0, 60),),
    )


def snapshot(assignments, *, end: date, blocked=(), class_blocked=None, presence=(), lunch=None):
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
        class_blocked_dates=class_blocked or {},
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
    assert (
        measure_priority_metrics(
            replace(school, teacher_presence=(TeacherPresenceRule(1, lunch_required=False),)),
            candidate,
        )["teacher_single_lessons"]
        == 0
    )
    assert (
        measure_priority_metrics(
            replace(
                school,
                teacher_presence=(TeacherPresenceRule(1, minimum_minutes=120, max_gap_minutes=60),),
            ),
            candidate,
        )["teacher_single_lessons"]
        == 0
    )
    assert measure_priority_metrics(school, candidate)["class_single_lessons"] == 2


def test_gap_metrics_do_not_count_the_lunch_hour_inside_the_window():
    monday = date(2026, 9, 7)
    grid = tuple(
        GridSlot(0, time(hour, minute), time(hour + 1, minute))
        for hour, minute in ((11, 20), (12, 30), (13, 30), (14, 40))
    )

    def at(identity, hour, minute):
        period = normalize_period(monday, time(hour, minute), time(hour + 1, minute), TZ)
        return ScheduledLesson(identity, 1, period, 1, 60, (ModuleSlice(identity, 1, 0, 60),))

    school = replace(
        snapshot((assignment(1),), end=monday, lunch=LunchRule(time(12, 30), time(14, 30), 60)),
        grid_slots=grid,
    )
    candidate = CandidateSchedule((at(1, 11, 20), at(2, 14, 40)))

    metrics = measure_priority_metrics(school, candidate)

    # Two empty hours between the lessons; one of them is the 60-minute lunch.
    assert (metrics["teacher_gaps"], metrics["class_gaps"]) == (60, 60)


def test_gap_metrics_count_the_lunch_window_for_a_teacher_dispensed_from_lunch():
    monday = date(2026, 9, 7)
    grid = tuple(
        GridSlot(0, time(hour, minute), time(hour + 1, minute))
        for hour, minute in ((11, 20), (12, 30), (13, 30), (14, 40))
    )
    school = replace(
        snapshot(
            (assignment(1),),
            end=monday,
            lunch=LunchRule(time(12, 30), time(14, 30), 60),
            presence=(TeacherPresenceRule(1, lunch_required=False),),
        ),
        grid_slots=grid,
    )

    def at(identity: int, hour: int, minute: int):
        period = normalize_period(monday, time(hour, minute), time(hour + 1, minute), TZ)
        return ScheduledLesson(
            identity, 1, period, 1, 60, (ModuleSlice(identity, 1, 0, 60),)
        )

    candidate = CandidateSchedule(
        (
            at(1, 11, 20),
            at(2, 14, 40),
        )
    )

    metrics = measure_priority_metrics(school, candidate)

    assert metrics["teacher_gaps"] == 120


def test_weekly_stability_skips_a_blocked_class_day():
    mondays = (date(2026, 9, 7), date(2026, 9, 14), date(2026, 9, 21))
    assignments = (assignment(1, subject_id=1), assignment(2, subject_id=2))
    candidate = CandidateSchedule((lesson(1, 1, mondays[0], 9), lesson(2, 2, mondays[1], 9)))
    school = snapshot(assignments, end=mondays[2], blocked=(mondays[2],))

    assert measure_priority_metrics(school, candidate)["weekly_stability"] == 1


def test_weekly_stability_counts_changes_across_an_empty_teachable_week():
    mondays = (date(2026, 9, 7), date(2026, 9, 14), date(2026, 9, 21))
    school = snapshot((assignment(1),), end=mondays[2])
    candidate = CandidateSchedule((lesson(1, 1, mondays[0], 9), lesson(2, 1, mondays[2], 9)))

    assert measure_priority_metrics(school, candidate)["weekly_stability"] == 2
    class_holiday = replace(
        school,
        class_blocked_dates={1: frozenset({mondays[1]})},
    )
    assert measure_priority_metrics(class_holiday, candidate)["weekly_stability"] == 0


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        (
            lambda baseline, day: CandidateSchedule(
                (replace(baseline.lessons[0], slices=(ModuleSlice(1, 1, 10, 60),)),)
            ),
            0,
        ),
        (lambda _baseline, day: CandidateSchedule((lesson(77, 1, day, 9),)), 0),
        (
            lambda _baseline, day: CandidateSchedule((lesson(2, 1, day + timedelta(days=7), 9),)),
            1,
        ),
    ],
    ids=("modular-update", "identity-rekey", "physical-move"),
)
def test_update_stability_reuses_physical_disruption_count(candidate, expected):
    day = date(2026, 9, 7)
    school = snapshot((assignment(1),), end=day + timedelta(days=7))
    published = CandidateSchedule((lesson(1, 1, day, 9),))
    planned = candidate(published, day)
    disruption = measure_disruption(school, published, planned, RECOVERY_POLICY)
    changed = len(disruption.changes)
    latest = max(lesson.period.school_date for lesson in planned.lessons)
    report = ValidationReport(
        validator_version="test",
        violations=(),
        credited_minutes={},
        completion_dates={1: latest},
        total_credit_minutes=0,
    )
    initial_quality = InitialQualityMetrics(
        completion_dates={1: latest},
        teacher_gap_minutes=0,
        class_gap_minutes=0,
        preference_cost_minutes=0,
        room_change_cost=0,
    )
    proposal = recovery_proposal_payload(
        replace(
            school,
            strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
            baseline_lessons=published.lessons,
        ),
        planned,
        quality=RecoveryQualityMetrics(initial_quality, disruption),
        report=report,
        evidence=None,
    )

    assert len(disruption.changes) == expected
    assert (
        measure_priority_metrics(school, planned, changed_lessons=changed)["update_stability"]
        == expected
    )
    assert proposal.metrics["priority_summary"]["proposal"]["update_stability"] == expected


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
