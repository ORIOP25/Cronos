"""Permanent regressions for the W06/W07 review counterexamples E01-E08."""

from dataclasses import replace
from datetime import time

import pytest

from app.scheduler.application import recovery as recovery_application
from app.scheduler.composition import repair_published_schedule
from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import (
    CandidateSchedule,
    ScheduledLesson,
)
from app.scheduler.domain.projection import ModuleSlice
from app.scheduler.domain.recovery import (
    BaselineIssueKind,
    assess_baseline,
    recovery_vector,
)
from app.scheduler.domain.results import OUTCOME_CANCELLED, SearchOutcome
from app.scheduler.domain.stop import (
    BudgetPhase,
    ExecutionBudget,
    ExplorationPolicy,
    TrajectoryPoint,
    decide_stop,
)
from app.scheduler.lab.fixtures import AssignmentSpec, build_snapshot
from tests.unit.test_scheduler_recovery_solver_v1 import DAY0, DAY1, POLICY, TZ, _spec


def _lesson(identity, assignment_id, when, room, credit, offset=0):
    return ScheduledLesson(
        lesson_id=identity,
        assignment_id=assignment_id,
        period=when,
        room_id=room,
        credit_minutes=credit,
        slices=(ModuleSlice(identity, 1, offset, credit),),
    )


def _period(day):
    return normalize_period(day, time(9), time(10), TZ)


def _two_day_spec(**overrides):
    values = dict(
        periods=((DAY0, time(9), time(10)), (DAY1, time(9), time(10))),
        grid_slots=((0, time(9), time(10)), (1, time(9), time(10))),
    )
    values.update(overrides)
    return _spec(**values)


def _single_assignment_spec(**overrides):
    return _two_day_spec(assignments=(AssignmentSpec(1, 7, (60,), (500,)),), **overrides)


def test_e01_a_valid_baseline_is_never_replaced_by_a_worse_repair():
    snapshot = build_snapshot(_single_assignment_spec())
    baseline = CandidateSchedule((_lesson(1, 1, _period(DAY1), 500, 60),))
    snapshot = replace(snapshot, baseline_lessons=baseline.lessons)
    periods = (_period(DAY0), _period(DAY1))
    baseline_vector = recovery_vector(snapshot, baseline, baseline, POLICY)

    result = repair_published_schedule(snapshot, periods, baseline, POLICY, time_limit_seconds=10)

    assert result.outcome == "COMPLETE"
    assert result.report is not None and result.report.valid
    assert recovery_vector(snapshot, baseline, result.candidate, POLICY) <= baseline_vector


def test_e02_room_matching_cannot_worsen_the_adaptive_vector():
    day0, day1 = _period(DAY0), _period(DAY1)
    snapshot = build_snapshot(
        _two_day_spec(
            assignments=(
                AssignmentSpec(1, 7, (120,), (500, 501)),
                AssignmentSpec(2, 8, (120,), (500, 501)),
            )
        )
    )
    protected = (
        _lesson(10, 1, day0, 500, 60),
        _lesson(20, 2, day0, 501, 60),
    )
    future = (
        _lesson(11, 1, day1, 501, 60),
        _lesson(21, 2, day1, 500, 60),
    )
    baseline = CandidateSchedule((*protected, *future))
    snapshot = replace(snapshot, protected_lessons=protected, baseline_lessons=baseline.lessons)

    result = repair_published_schedule(
        snapshot, (day0, day1), baseline, POLICY, time_limit_seconds=10
    )

    assert result.outcome == "COMPLETE"
    assert result.report is not None and result.report.valid
    assert result.quality is not None
    assert result.quality.disruption.total_cost == 0
    rooms = {
        lesson.source_lesson_id: lesson.room_id
        for lesson in result.candidate.lessons
        if lesson.source_lesson_id in {11, 21}
    }
    assert rooms == {11: 501, 21: 500}


def test_e03_a_moved_lesson_keeps_its_published_identity():
    day0, day1 = _period(DAY0), _period(DAY1)
    snapshot = build_snapshot(
        _single_assignment_spec(unavailable=(("teacher", 7, (DAY0, time(9), time(10))),))
    )
    baseline = CandidateSchedule((_lesson(1, 1, day0, 500, 60),))
    snapshot = replace(snapshot, baseline_lessons=baseline.lessons)

    result = repair_published_schedule(
        snapshot, (day0, day1), baseline, POLICY, time_limit_seconds=10
    )

    assert result.outcome == "COMPLETE"
    assert result.quality is not None
    disruption = result.quality.disruption
    assert disruption.moved_lessons == 1
    assert disruption.inserted_lessons == 0
    assert disruption.removed_lessons == 0
    assert disruption.changes[0].source_lesson_id == 1
    assert disruption.changes[0].cost == POLICY.move_cost


def test_e04_a_protected_lesson_is_not_counted_as_excess():
    protected = _lesson(1, 1, _period(DAY0), 500, 60)
    future = _lesson(2, 1, _period(DAY1), 500, 60, offset=60)
    snapshot = build_snapshot(_two_day_spec(assignments=(AssignmentSpec(1, 7, (120,), (500,)),)))
    snapshot = replace(
        snapshot, protected_lessons=(protected,), baseline_lessons=(protected, future)
    )

    assessment = assess_baseline(snapshot, (protected, future))

    assert assessment.valid
    assert assessment.missing_minutes == 0
    assert assessment.excess_minutes == 0


def test_e05_a_baseline_with_a_resource_conflict_is_invalid():
    day0 = _period(DAY0)
    snapshot = build_snapshot(
        _two_day_spec(
            assignments=(
                AssignmentSpec(1, 7, (60,), (500,)),
                AssignmentSpec(2, 7, (60,), (501,)),
            )
        )
    )
    baseline = CandidateSchedule((_lesson(1, 1, day0, 500, 60), _lesson(2, 2, day0, 501, 60)))
    snapshot = replace(snapshot, baseline_lessons=baseline.lessons)

    assessment = assess_baseline(snapshot, baseline.lessons)

    assert not assessment.valid
    assert BaselineIssueKind.RESOURCE_CONFLICT in {row.kind for row in assessment.issues}


def _valid_baseline_case():
    snapshot = build_snapshot(_single_assignment_spec())
    baseline = CandidateSchedule((_lesson(1, 1, _period(DAY0), 500, 60),))
    snapshot = replace(snapshot, baseline_lessons=baseline.lessons)
    return snapshot, (_period(DAY0), _period(DAY1)), baseline


class _ValidReport:
    valid = True
    violations: tuple = ()
    credited_minutes: dict = {}
    total_credit_minutes = 0
    completion_dates: dict = {}


def test_e06_the_budget_sums_phase_deltas_without_double_counting(monkeypatch):
    snapshot, periods, baseline = _valid_baseline_case()
    clock = iter([0.0, 1.0, 3.0, 4.0, 4.0])

    def stub_search(*args, **kwargs):
        return SearchOutcome("COMPLETE", baseline, 0, None, "stub", 2.0, {})

    monkeypatch.setattr(recovery_application, "monotonic", lambda: next(clock))
    monkeypatch.setattr(
        recovery_application, "validate_candidate", lambda snapshot, candidate: _ValidReport()
    )
    monkeypatch.setattr(recovery_application, "_summary", lambda snapshot, quality: None)

    result = recovery_application.repair_schedule(
        snapshot,
        periods,
        baseline,
        search=stub_search,
        policy=POLICY,
        time_limit_seconds=10,
    )

    assert result.outcome == "COMPLETE"
    assert result.budget is not None
    phases = result.budget.phase_seconds
    assert phases[BudgetPhase.CONSTRUCTION] == pytest.approx(1.0)
    assert phases[BudgetPhase.SEARCH] == pytest.approx(2.0)
    assert phases[BudgetPhase.FINALIZATION] == pytest.approx(1.0)
    assert result.budget.elapsed_seconds == pytest.approx(4.0)
    assert result.budget.elapsed_seconds <= result.wall_time_seconds + 1e-9


def test_e07_cancellation_after_the_search_response_is_respected():
    snapshot, periods, baseline = _valid_baseline_case()
    cancelled = {"value": False}

    def stub_search(*args, **kwargs):
        cancelled["value"] = True
        return SearchOutcome("COMPLETE", baseline, 0, None, "stub", 0.1, {})

    result = recovery_application.repair_schedule(
        snapshot,
        periods,
        baseline,
        search=stub_search,
        policy=POLICY,
        should_cancel=lambda: cancelled["value"],
        time_limit_seconds=10,
    )

    assert result.outcome == OUTCOME_CANCELLED
    assert result.candidate is None


@pytest.mark.parametrize("limit", [float("inf"), float("-inf"), float("nan")])
def test_e08_the_safety_limit_must_be_finite(limit):
    with pytest.raises(ValueError):
        ExecutionBudget(limit_seconds=limit)


def test_r67_07_a_single_first_solution_never_stops_the_search():
    policy = ExplorationPolicy("lab", 10.0, 5.0, 1, 0, minimum_solutions=2)
    points = (TrajectoryPoint(30.0, (9, 0, 0), complete=True),)

    decision = decide_stop(points, policy)

    assert decision.stop is False


def test_r67_07_disruption_gain_counts_even_with_an_equal_max_day():
    policy = ExplorationPolicy("lab", 0.0, 5.0, 1, 0, minimum_solutions=1)
    points = (
        TrajectoryPoint(10.0, (9, 5, 40), complete=True),
        TrajectoryPoint(12.0, (9, 4, 40), complete=True),
    )

    decision = decide_stop(points, policy)

    assert decision.stop is False
    assert decision.reason == "RECENT_IMPROVEMENT"
