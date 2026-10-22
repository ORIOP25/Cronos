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
from app.scheduler.domain.priorities import (
    CRITERION_KEYS,
    LATE_DAY_COST,
    PRIORITY_MULTIPLIERS,
    UNIT_COSTS,
    PriorityWeights,
)
from app.scheduler.domain.priority_metrics import measure_priority_metrics, priority_cost
from app.scheduler.domain.projection import ModuleRequirement, ModuleSlice
from app.scheduler.domain.quality import lunch_minutes_in
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


def test_single_lesson_days_count_whole_days_and_skip_teachers_with_a_minimum():
    # Owner, 21 Oct 2026: "vem para uma só aula" counts whole days, not shifts.
    monday, tuesday = date(2026, 9, 7), date(2026, 9, 8)
    assignments = (assignment(1),)
    candidate = CandidateSchedule(
        (lesson(1, 1, monday, 9), lesson(2, 1, monday, 15), lesson(3, 1, tuesday, 9))
    )
    school = snapshot(assignments, end=tuesday, lunch=LunchRule(time(12), time(14), 30))

    metrics = measure_priority_metrics(school, candidate)

    # Monday has a morning and an afternoon lesson: one day, not two single shifts.
    assert (metrics["teacher_single_lessons"], metrics["class_single_lessons"]) == (1, 1)
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


def test_fragmented_free_periods_do_not_add_up_to_a_continuous_lunch():
    lunch = LunchRule(time(12, 30), time(14, 30), 60)
    free_periods = ((12 * 60 + 30, 12 * 60 + 50), (13 * 60, 13 * 60 + 40))
    lesson = ((12 * 60 + 50, 13 * 60), (13 * 60 + 40, 14 * 60 + 30))

    assert lunch_minutes_in(free_periods, lunch, lesson) == 0


def test_free_grid_slots_across_a_non_teaching_interval_form_continuous_lunch():
    lunch = LunchRule(time(12), time(14), 60)
    free_periods = ((12 * 60, 12 * 60 + 40), (12 * 60 + 50, 13 * 60 + 30))

    assert lunch_minutes_in(free_periods, lunch) == 50


def test_gap_metrics_do_not_discount_lunch_fragments_separated_by_a_lesson():
    monday = date(2026, 9, 7)
    grid = tuple(
        GridSlot(0, time(start_hour, start_minute), time(end_hour, end_minute))
        for start_hour, start_minute, end_hour, end_minute in (
            (11, 20, 12, 0),
            (12, 0, 12, 40),
            (12, 40, 12, 50),
            (12, 50, 13, 30),
            (13, 30, 14, 30),
            (14, 40, 15, 40),
        )
    )
    school = replace(
        snapshot((assignment(1),), end=monday, lunch=LunchRule(time(12), time(14), 60)),
        grid_slots=grid,
    )
    lessons = tuple(
        ScheduledLesson(
            identity,
            1,
            normalize_period(monday, start, end, TZ),
            1,
            duration,
            (ModuleSlice(identity, 1, 0, duration),),
        )
        for identity, start, end, duration in (
            (1, time(11, 20), time(12), 40),
            (2, time(12, 40), time(12, 50), 10),
            (3, time(13, 30), time(14, 30), 60),
            (4, time(14, 40), time(15, 40), 60),
        )
    )

    metrics = measure_priority_metrics(school, CandidateSchedule(lessons))

    assert (metrics["teacher_gaps"], metrics["class_gaps"]) == (80, 80)


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
        return ScheduledLesson(identity, 1, period, 1, 60, (ModuleSlice(identity, 1, 0, 60),))

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
    assert stronger_class_gaps_cost - class_gaps_cost == (
        (PRIORITY_MULTIPLIERS[3] - PRIORITY_MULTIPLIERS[2])
        * UNIT_COSTS["class_gaps"]
        * metrics["class_gaps"]
    )
    assert type(class_gaps_cost) is int


FINISH = date(2026, 9, 14)


def finish_only_metrics(finish: date = FINISH) -> dict:
    return {key: 0 for key in CRITERION_KEYS} | {"finish_early": finish}


def finish_early_weights(level: int) -> PriorityWeights:
    return PriorityWeights({key: 0 for key in CRITERION_KEYS} | {"finish_early": level})


def test_priority_cost_prices_each_day_past_the_preferred_end_at_the_late_day_cost():
    weights = finish_early_weights(4)
    on_time = priority_cost(finish_only_metrics(), weights, origin=ORIGIN)

    late = priority_cost(
        finish_only_metrics(), weights, origin=ORIGIN, preferred_end_date=FINISH - timedelta(7)
    )

    assert late - on_time == 7 * PRIORITY_MULTIPLIERS[4] * LATE_DAY_COST


@pytest.mark.parametrize("preferred_end", [FINISH, FINISH + timedelta(days=3)])
def test_priority_cost_adds_no_lateness_on_or_before_the_preferred_end(preferred_end):
    weights = finish_early_weights(4)

    assert priority_cost(
        finish_only_metrics(), weights, origin=ORIGIN, preferred_end_date=preferred_end
    ) == priority_cost(finish_only_metrics(), weights, origin=ORIGIN)


def test_priority_cost_adds_no_lateness_when_finish_early_is_ignored():
    weights = finish_early_weights(0)

    assert priority_cost(
        finish_only_metrics(), weights, origin=ORIGIN, preferred_end_date=FINISH - timedelta(7)
    ) == priority_cost(finish_only_metrics(), weights, origin=ORIGIN)


def test_priority_cost_rejects_a_preferred_end_that_is_not_a_date():
    with pytest.raises(ValueError):
        priority_cost(
            finish_only_metrics(),
            finish_early_weights(4),
            origin=ORIGIN,
            preferred_end_date="2026-09-14",
        )
