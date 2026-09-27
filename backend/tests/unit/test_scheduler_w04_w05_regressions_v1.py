"""Acceptance regressions for the W04/W05 review defects F01-F09.

Each test reproduces a review counterexample and asserts the expected behavior
of the corrected generator. The independent oracle stays the reference for the
small instances.
"""

from dataclasses import replace
from datetime import date, time, timedelta

import pytest
from ortools.sat.python import cp_model

from app.scheduler.composition import generate_schedule
from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import (
    Assignment,
    GridSlot,
    PlanningSnapshot,
    SchedulingStrategy,
    Unavailability,
    UnavailableResource,
)
from app.scheduler.domain.oracle import optimal_candidate, oracle_objective
from app.scheduler.domain.projection import ModuleRequirement
from app.scheduler.infrastructure.annual_model import QuotaDistribution
from app.scheduler.infrastructure.placement_model import solve_placement

TZ = "Europe/Lisbon"
ORIGIN = date(2026, 9, 21)


def period(day, start=9, end=10, start_min=0, end_min=0):
    return normalize_period(
        ORIGIN + timedelta(days=day),
        time(start, start_min),
        time(end, end_min),
        TZ,
    )


def snapshot(periods, minutes=60, count=1, **kwargs):
    return PlanningSnapshot(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=ORIGIN,
        preferred_end_date=ORIGIN + timedelta(days=20),
        hard_end_date=ORIGIN + timedelta(days=30),
        timezone_name=TZ,
        grid_slots=tuple(
            dict.fromkeys(
                GridSlot(row.school_date.weekday(), row.start_local, row.end_local)
                for row in periods
            )
        ),
        assignments=tuple(
            Assignment(
                i,
                i,
                i,
                i,
                frozenset({i}),
                (ModuleRequirement(i, 1, minutes),),
            )
            for i in range(1, count + 1)
        ),
        executed_minutes={},
        blocked_dates=frozenset(),
        unavailable=kwargs.pop("unavailable", ()),
        **kwargs,
    )


def test_f01_overlapping_lessons_of_the_same_assignment_are_forbidden():
    periods = (period(0), period(0, start_min=30, end_min=30), period(1))
    target = snapshot(periods, minutes=120)

    result = generate_schedule(target, periods, time_limit_seconds=10)

    assert result.outcome == "COMPLETE"
    assert result.report is not None and result.report.valid
    assert oracle_objective(target, result.candidate) == (1,)
    assert oracle_objective(target, optimal_candidate(target, periods)) == (1,)


def test_f02_period_order_does_not_change_validity_or_quality():
    periods = (period(0), period(1))
    target = snapshot(periods, minutes=90)

    vectors = []
    for ordered in (periods, tuple(reversed(periods))):
        result = generate_schedule(target, ordered, time_limit_seconds=10)
        assert result.outcome == "COMPLETE"
        assert result.report is not None and result.report.valid
        lessons = sorted(result.candidate.lessons, key=lambda row: row.period.start_utc)
        assert lessons[-1].credit_minutes < lessons[-1].period.duration_minutes
        vectors.append(oracle_objective(target, result.candidate))

    assert vectors == [(1,), (1,)]


def test_f03_protected_dates_and_past_periods_are_not_eligible():
    periods = (period(0), period(1))
    for overrides in (
        {"protected_dates": frozenset({ORIGIN})},
        {"now_utc": periods[0].end_utc},
    ):
        target = snapshot(periods, **overrides)

        result = generate_schedule(target, periods, time_limit_seconds=10)

        assert result.outcome == "COMPLETE"
        assert result.report is not None and result.report.valid
        assert [row.period.school_date for row in result.candidate.lessons] == [
            ORIGIN + timedelta(days=1)
        ]


def test_f03_a_fully_protected_horizon_is_infeasible_not_failed():
    periods = (period(0),)
    target = snapshot(periods, protected_dates=frozenset({ORIGIN}))

    result = generate_schedule(target, periods, time_limit_seconds=10)

    assert result.outcome == "INFEASIBLE"


def test_f04_waste_does_not_replace_an_earlier_completion():
    periods = (period(0, end=11), period(1, end=10, end_min=30))
    target = snapshot(periods, minutes=90)

    result = generate_schedule(target, periods, time_limit_seconds=10)

    assert result.outcome == "COMPLETE"
    assert result.report is not None and result.report.valid
    assert oracle_objective(target, result.candidate) == (0,)
    assert oracle_objective(target, optimal_candidate(target, periods)) == (0,)


@pytest.mark.parametrize("count", [2, 6, 7, 8, 9])
def test_f05_the_whole_completion_vector_is_preserved(count):
    periods = (period(0), period(1))
    unavailable = tuple(
        Unavailability(UnavailableResource.TEACHER, i, periods[0]) for i in range(1, count)
    )
    soft = (Unavailability(UnavailableResource.TEACHER, count, periods[0]),)
    target = snapshot(periods, count=count, unavailable=unavailable, soft_unavailable=soft)

    result = generate_schedule(target, periods, time_limit_seconds=10)

    expected = tuple([1] * (count - 1) + [0])
    assert result.outcome == "COMPLETE"
    assert result.report is not None and result.report.valid
    assert oracle_objective(target, result.candidate) == expected
    assert oracle_objective(target, optimal_candidate(target, periods)) == expected


def test_f06_an_unproven_stage_does_not_certify_following_stages(monkeypatch):
    periods = (period(0), period(1))
    target = snapshot(
        periods,
        minutes=60,
        soft_unavailable=(Unavailability(UnavailableResource.TEACHER, 1, periods[0]),),
    )
    original = cp_model.CpSolver.Solve
    calls = [0]

    def unproven_completion(self, model, *args, **kwargs):
        status = original(self, model, *args, **kwargs)
        calls[0] += 1
        # The pre-solve is call 1; the completion threshold is call 2.
        return cp_model.FEASIBLE if calls[0] == 2 else status

    monkeypatch.setattr(cp_model.CpSolver, "Solve", unproven_completion)

    outcome = solve_placement(target, periods, time_limit_seconds=10)

    assert outcome.status == "COMPLETE"
    assert outcome.evidence is not None
    assert outcome.evidence.stages[0].proven is False
    assert any(stage.proven for stage in outcome.evidence.stages[1:])
    assert outcome.evidence.certified_stages == 0


def test_f07_the_detail_materializes_the_distribution_exactly():
    periods = (
        period(0),
        period(0, start=10, end=11),
        period(0, start=11, end=12, end_min=30),
    )
    target = snapshot(periods, count=2)
    target = replace(
        target,
        assignments=(
            target.assignments[0],
            replace(
                target.assignments[1],
                teacher_id=1,
                modules=(ModuleRequirement(2, 1, 90),),
            ),
        ),
        unavailable=(
            Unavailability(UnavailableResource.CLASS, 1, periods[1]),
            Unavailability(UnavailableResource.CLASS, 1, periods[2]),
            Unavailability(UnavailableResource.CLASS, 2, periods[0]),
        ),
    )
    distribution = QuotaDistribution(
        counts={(1, 0, 60): 1, (2, 0, 90): 1},
        final_groups={1: (0, 60), 2: (0, 90)},
    )

    outcome = solve_placement(target, periods, distribution=distribution, time_limit_seconds=10)

    assert outcome.status == "COMPLETE"
    by_assignment = {}
    for lesson in outcome.candidate.lessons:
        by_assignment.setdefault(lesson.assignment_id, []).append(lesson)
    assert len(by_assignment[1]) == 1
    assert by_assignment[1][0].period.duration_minutes == 60
    assert len(by_assignment[2]) == 1
    assert by_assignment[2][0].period.duration_minutes == 90
    assert by_assignment[2][0].credit_minutes == 90


def test_f08_the_optimized_preference_cost_equals_the_metric():
    periods = (period(0),)
    target = snapshot(
        periods,
        soft_unavailable=(
            Unavailability(UnavailableResource.TEACHER, 1, periods[0]),
            Unavailability(UnavailableResource.ROOM, 1, periods[0]),
        ),
    )

    result = generate_schedule(target, periods, time_limit_seconds=10)

    assert result.outcome == "COMPLETE"
    assert result.quality is not None
    assert result.quality.preference_cost_minutes == 60
    values = [
        stage.value for stage in result.evidence.stages if stage.stage == "PREFERENCE_COST_MINUTES"
    ]
    assert values == [60]


def test_f09_margin_does_not_imply_recovery_capacity():
    periods = (period(0), period(7), period(14))
    target = snapshot(
        periods,
        unavailable=tuple(
            Unavailability(UnavailableResource.TEACHER, 1, row) for row in periods[1:]
        ),
    )

    result = generate_schedule(target, periods, time_limit_seconds=10, assess_recovery=True)

    assert result.outcome == "COMPLETE"
    assert result.completion is not None
    assert result.completion.margin_days == 20
    assert result.completion.recovery.status == "IMPOSSIBLE_PROVEN"


def test_f09_recovery_is_demonstrated_when_a_perturbed_schedule_exists():
    periods = (period(0), period(1))
    target = snapshot(periods, minutes=60)

    result = generate_schedule(target, periods, time_limit_seconds=10, assess_recovery=True)

    assert result.outcome == "COMPLETE"
    assert result.completion.recovery.status == "DEMONSTRATED"


def test_l12_extra_eligible_options_do_not_worsen_the_certified_optimum():
    narrow_periods = (period(0),)
    wide_periods = (period(0), period(1))
    narrow = snapshot(narrow_periods, minutes=60)
    wide = snapshot(wide_periods, minutes=60)

    narrow_result = generate_schedule(narrow, narrow_periods, time_limit_seconds=10)
    wide_result = generate_schedule(wide, wide_periods, time_limit_seconds=10)

    assert narrow_result.outcome == wide_result.outcome == "COMPLETE"
    narrow_vector = oracle_objective(narrow, narrow_result.candidate)
    wide_vector = oracle_objective(wide, wide_result.candidate)
    assert wide_vector <= narrow_vector
    assert wide_vector == oracle_objective(wide, optimal_candidate(wide, wide_periods))
