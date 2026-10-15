from datetime import date, time, timedelta

import pytest

from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import (
    Assignment,
    GridSlot,
    PlanningSnapshot,
    ScheduledLesson,
    SchedulingStrategy,
)
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.domain.oracle import (
    OracleBudgetExceededError,
    enumerate_candidates,
    optimal_candidate,
    oracle_objective,
)
from app.scheduler.domain.projection import ModuleRequirement, ModuleSlice

TZ = "Europe/Lisbon"
ORIGIN = date(2026, 9, 21)
PREFERRED = date(2026, 10, 30)
HARD_END = date(2026, 11, 30)
MONDAY = ORIGIN
WEDNESDAY = date(2026, 9, 23)


def _period(day, start=time(9), end=time(10)):
    return normalize_period(day, start, end, TZ)


PERIODS = (_period(MONDAY), _period(WEDNESDAY))
GRID = (GridSlot(0, time(9), time(10)), GridSlot(2, time(9), time(10)))


def _snapshot(*assignments: Assignment, **overrides) -> PlanningSnapshot:
    values = {
        "strategy": SchedulingStrategy.COMPLETE_GENERATION,
        "origin": ORIGIN,
        "preferred_end_date": PREFERRED,
        "hard_end_date": HARD_END,
        "timezone_name": TZ,
        "grid_slots": GRID,
        "assignments": assignments,
        "executed_minutes": {},
        "blocked_dates": frozenset(),
        "unavailable": (),
    }
    values.update(overrides)
    return PlanningSnapshot(**values)


def test_oracle_finds_the_only_complete_placement():
    snapshot = _snapshot(
        Assignment(1, (1,), 10, 100, frozenset({500}), (ModuleRequirement(1, 1, 100),))
    )

    result = enumerate_candidates(snapshot, PERIODS)

    assert result.feasible
    assert len(result.candidates) == 1
    assert [lesson.credit_minutes for lesson in result.candidates[0].lessons] == [60, 40]
    assert oracle_objective(snapshot, result.candidates[0]) == (2,)
    assert result.objective_scope == "COMPLETION_VECTOR_ONLY"


def test_oracle_proves_infeasibility_on_a_minimal_instance():
    snapshot = _snapshot(
        Assignment(1, (1,), 10, 100, frozenset({500}), (ModuleRequirement(1, 1, 200),))
    )

    result = enumerate_candidates(snapshot, PERIODS)

    assert not result.feasible
    assert optimal_candidate(snapshot, PERIODS) is None


def test_oracle_chooses_the_earliest_completion():
    snapshot = _snapshot(
        Assignment(1, (1,), 10, 100, frozenset({500}), (ModuleRequirement(1, 1, 50),))
    )

    result = enumerate_candidates(snapshot, PERIODS)
    best = optimal_candidate(snapshot, PERIODS)

    assert len(result.candidates) == 2
    assert best is not None
    assert best.lessons[0].period.school_date == MONDAY
    assert oracle_objective(snapshot, best) == (0,)


def test_oracle_filters_combinations_that_conflict_on_a_shared_teacher():
    snapshot = _snapshot(
        Assignment(1, (1,), 10, 100, frozenset({500}), (ModuleRequirement(1, 1, 50),)),
        Assignment(2, (2,), 20, 100, frozenset({501}), (ModuleRequirement(2, 1, 50),)),
    )

    result = enumerate_candidates(snapshot, PERIODS)

    assert len(result.candidates) == 2
    for candidate in result.candidates:
        dates = sorted(lesson.period.school_date for lesson in candidate.lessons)
        assert dates == [MONDAY, WEDNESDAY]
        assert oracle_objective(snapshot, candidate) == (2, 0)


def test_oracle_accepts_a_fully_protected_witness_without_duplicating_it():
    protected = ScheduledLesson(1, 1, _period(MONDAY), 500, 60, (ModuleSlice(1, 1, 0, 60),))
    snapshot = _snapshot(
        Assignment(1, (1,), 10, 100, frozenset({500}), (ModuleRequirement(1, 1, 60),)),
        protected_lessons=(protected,),
    )

    result = enumerate_candidates(snapshot, PERIODS)

    assert result.feasible
    assert result.candidates[0].lessons == (protected,)


def test_oracle_subtracts_half_protected_credit_before_enumerating():
    protected = ScheduledLesson(1, 1, _period(MONDAY), 500, 60, (ModuleSlice(1, 1, 0, 60),))
    snapshot = _snapshot(
        Assignment(1, (1,), 10, 100, frozenset({500}), (ModuleRequirement(1, 1, 120),)),
        protected_lessons=(protected,),
    )

    result = enumerate_candidates(snapshot, PERIODS)
    best = optimal_candidate(snapshot, PERIODS)

    assert result.feasible
    assert best is not None
    assert len(best.lessons) == 2
    assert best.lessons[1].period.school_date == WEDNESDAY
    assert [
        (row.module_id, row.offset_minutes, row.credit_minutes) for row in best.lessons[1].slices
    ] == [(1, 60, 60)]


def test_oracle_raises_an_explicit_budget_limit_not_infeasibility():
    days = [ORIGIN + timedelta(days=offset) for offset in range(4)]
    periods = tuple(
        normalize_period(day, start, end, TZ)
        for day in days
        for start, end in ((time(9), time(10)), (time(10), time(11)))
    )
    grid = tuple(
        GridSlot(day.weekday(), start, end)
        for day in days
        for start, end in ((time(9), time(10)), (time(10), time(11)))
    )
    snapshot = _snapshot(
        Assignment(1, (1,), 10, 100, frozenset({500, 501}), (ModuleRequirement(1, 1, 30),)),
        grid_slots=grid,
    )

    with pytest.raises(OracleBudgetExceededError):
        enumerate_candidates(snapshot, periods)


def test_oracle_matches_a_manually_derived_minimum():
    snapshot = _snapshot(
        Assignment(1, (1,), 10, 100, frozenset({500}), (ModuleRequirement(1, 1, 50),))
    )

    best = optimal_candidate(snapshot, PERIODS)

    assert best is not None
    assert best.lessons[0].period == _period(MONDAY)
    assert best.lessons[0].credit_minutes == 50
    assert [
        (row.module_id, row.offset_minutes, row.credit_minutes) for row in best.lessons[0].slices
    ] == [(1, 0, 50)]


def test_oracle_accepts_a_joint_unit_and_respects_its_precedence():
    joint = Assignment(1, (1, 2), 10, 100, frozenset({500}), (ModuleRequirement(1, 1, 50),))
    successor = Assignment(2, (2,), 10, 100, frozenset({500}), (ModuleRequirement(2, 1, 50),))
    snapshot = _snapshot(joint, successor, precedences=((1, 2),))

    best = optimal_candidate(snapshot, PERIODS)

    assert best is not None
    assert validate_candidate(snapshot, best).valid
    joint_lesson = next(lesson for lesson in best.lessons if lesson.assignment_id == 1)
    successor_lesson = next(lesson for lesson in best.lessons if lesson.assignment_id == 2)
    assert successor_lesson.period.start_utc >= joint_lesson.period.end_utc
