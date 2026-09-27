"""W11 calibration: offline stopping-policy scoring with a reserved split."""

import pytest

from app.scheduler.domain.stop import TrajectoryPoint
from app.scheduler.lab.calibration import (
    CALIBRATION_CANDIDATES,
    CandidateScore,
    calibration_manifest,
    candidate_policies,
    score_stop_candidates,
    select_candidate,
)

HORIZON = 30.0


def _points(*rows: tuple[float, tuple[int, ...]]) -> list[TrajectoryPoint]:
    return [TrajectoryPoint(elapsed, incumbent, True) for elapsed, incumbent in rows]


def test_eager_stops_early_and_loses_gain_while_patient_keeps_it():
    points = _points(
        (1.0, (5,)),  # early improvement
        (25.0, (1,)),  # late improvement after a long stagnation
    )

    scores = score_stop_candidates(points, candidate_policies(), HORIZON)

    by_id = {score.candidate_id: score for score in scores}
    assert by_id["eager"].saved_seconds > by_id["patient"].saved_seconds
    assert by_id["eager"].lost_gain > 0
    assert by_id["patient"].lost_gain == 0


def test_candidate_without_loss_is_preferred_with_the_largest_saving():
    scores = (
        CandidateScore("lossy", 1, 20.0, 3, HORIZON, early_stops=1),
        CandidateScore("safe-slow", 1, 5.0, 0, HORIZON, early_stops=1),
        CandidateScore("safe-fast", 1, 15.0, 0, HORIZON, early_stops=1),
    )

    chosen = select_candidate(scores)

    assert chosen is not None
    assert chosen.candidate_id == "safe-fast"


def test_a_lossless_policy_that_never_stopped_early_is_not_adopted():
    scores = (
        CandidateScore("exhausted", 1, 200.0, 0, HORIZON, early_stops=0),
        CandidateScore("stopped", 1, 10.0, 0, HORIZON, early_stops=1),
    )

    chosen = select_candidate(scores)

    assert chosen is not None
    assert chosen.candidate_id == "stopped"


def test_a_lossy_candidate_is_never_adopted_automatically():
    scores = (
        CandidateScore("lossy", 1, 20.0, 3, HORIZON),
        CandidateScore("careful", 1, 10.0, 1, HORIZON),
        CandidateScore("careless", 1, 25.0, 5, HORIZON),
    )

    assert select_candidate(scores) is None


def test_no_candidate_that_saves_nothing_is_chosen():
    scores = (
        CandidateScore("a", 1, 0.0, 0, HORIZON),
        CandidateScore("b", 1, 0.0, 0, HORIZON),
    )

    assert select_candidate(scores) is None


def test_scoring_requires_trajectories_and_known_candidates():
    with pytest.raises(ValueError, match="trajectory"):
        score_stop_candidates([], candidate_policies(), HORIZON)
    with pytest.raises(ValueError, match="candidate"):
        score_stop_candidates(_points((1.0, (1,))), (), HORIZON)


def test_declared_candidates_are_explicit_and_versioned():
    candidates = candidate_policies()

    assert len(candidates) >= 3
    assert len({candidate.candidate_id for candidate in candidates}) == len(candidates)
    assert all(candidate.exploration.version for candidate in candidates)
    assert CALIBRATION_CANDIDATES["patient"].minimum_solutions >= 1


def test_the_manifest_declares_training_and_reserved_cases_without_overlap():
    manifest = calibration_manifest()

    training = set(manifest["calibration"]["training_cases"])
    reserved = set(manifest["calibration"]["reserved_cases"])
    assert training
    assert reserved
    assert training.isdisjoint(reserved)
    assert manifest["calibration"]["policy_version"].startswith("w11-")
    declared = {row["candidate_id"] for row in manifest["calibration"]["candidates"]}
    assert declared == {candidate.candidate_id for candidate in candidate_policies()}
    assert manifest["calibration"]["status"] == "experimental"
