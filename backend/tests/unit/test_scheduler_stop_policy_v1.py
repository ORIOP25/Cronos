"""W07: budget honesty, adaptive stopping and C19 offline trajectory replay."""

import pytest

from app.scheduler.domain.stop import (
    STOP_CANCELLED,
    STOP_LOW_EXPECTED_RETURN,
    STOP_SAFETY_LIMIT,
    BudgetPhase,
    ExecutionBudget,
    ExplorationPolicy,
    TrajectoryPoint,
    decide_stop,
    replay_stop_policy,
)

POLICY = ExplorationPolicy(
    version="laboratory-example",
    minimum_exploration_seconds=10.0,
    gain_window_seconds=5.0,
    minimum_significant_gain_days=1,
    corpus_expected_gain_days=0,
    minimum_solutions=2,
)


def _point(elapsed: float, incumbent: tuple[int, ...], *, complete: bool = True):
    return TrajectoryPoint(elapsed, incumbent, complete=complete)


def test_the_budget_counts_every_phase_and_never_hides_an_overflow():
    budget = ExecutionBudget(limit_seconds=10.0)

    budget.charge(BudgetPhase.CONSTRUCTION, 3.0)
    budget.charge(BudgetPhase.SEARCH, 6.0)

    assert budget.within_budget
    assert budget.remaining_seconds == pytest.approx(1.0)

    budget.charge(BudgetPhase.FINALIZATION, 2.0)

    assert not budget.within_budget
    assert budget.remaining_seconds == 0.0
    assert budget.as_dict()["within_budget"] is False


def test_an_omitted_stage_is_recorded_and_a_bad_charge_is_rejected():
    budget = ExecutionBudget(limit_seconds=5.0)
    budget.omit("ROOM_CONTINUITY_STAGE")

    assert budget.omitted_stages == ["ROOM_CONTINUITY_STAGE"]
    with pytest.raises(ValueError):
        budget.charge(BudgetPhase.SEARCH, -1)
    with pytest.raises(ValueError):
        ExecutionBudget(limit_seconds=0)


def test_stopping_for_quality_requires_a_complete_solution():
    decision = decide_stop((_point(30.0, (5,), complete=False),), POLICY)

    assert decision.stop is False
    assert decision.reason == "NO_COMPLETE_SOLUTION"


def test_stopping_requires_more_than_the_first_explored_solution():
    decision = decide_stop((_point(30.0, (5,)),), POLICY)

    assert decision.stop is False
    assert decision.reason == "REQUIRE_MORE_SOLUTIONS"


def test_the_minimum_exploration_runs_from_the_first_solution():
    points = (_point(2.0, (9,)), _point(3.0, (8,)))

    decision = decide_stop(points, POLICY)

    assert decision.stop is False
    assert decision.reason == "MINIMUM_EXPLORATION"


def test_recent_progress_keeps_the_search_alive():
    points = (_point(4.0, (9,)), _point(14.0, (8,)))

    decision = decide_stop(points, POLICY)

    assert decision.stop is False
    assert decision.reason == "RECENT_IMPROVEMENT"


def test_low_expected_return_stops_after_the_gain_window():
    points = (_point(4.0, (9,)), _point(30.0, (9,)))

    decision = decide_stop(points, POLICY)

    assert decision.stop is True
    assert decision.reason == STOP_LOW_EXPECTED_RETURN


def test_corpus_gain_above_the_threshold_justifies_more_effort():
    policy = ExplorationPolicy(
        "calibrated",
        10.0,
        5.0,
        minimum_significant_gain_days=1,
        corpus_expected_gain_days=3,
        minimum_solutions=2,
    )
    points = (_point(4.0, (9,)), _point(30.0, (9,)))

    decision = decide_stop(points, policy)

    assert decision.stop is False
    assert decision.reason == "CORPUS_EXPECTS_GAIN"


def test_safety_and_cancellation_stop_with_their_own_reasons():
    points = (_point(12.0, (9,)),)

    assert decide_stop(points, POLICY, cancelled=True).reason == STOP_CANCELLED
    assert decide_stop(points, POLICY, safety_limit_reached=True).reason == STOP_SAFETY_LIMIT


def test_c19_replay_measures_lost_gain_and_saved_effort():
    points = (
        _point(1.0, (10,)),
        _point(8.0, (9,)),
        _point(40.0, (9,)),
        _point(80.0, (7,)),
    )

    replay = replay_stop_policy(points, POLICY, reference_horizon_seconds=120.0)

    assert replay.reason == STOP_LOW_EXPECTED_RETURN
    assert replay.final_vector == (9,)
    assert replay.best_vector == (7,)
    assert replay.lost_gain is True
    assert replay.saved_seconds == pytest.approx(80.0)


def test_a_patient_policy_captures_the_late_improvement():
    points = (
        _point(1.0, (10,)),
        _point(8.0, (9,)),
        _point(40.0, (9,)),
        _point(80.0, (7,)),
    )
    patient = ExplorationPolicy("patient", 10.0, 60.0, 1, 3, minimum_solutions=2)

    replay = replay_stop_policy(points, patient, reference_horizon_seconds=120.0)

    assert replay.lost_gain is False
    assert replay.best_vector == (7,)
