"""W11 calibration: candidate stopping policies scored offline on trajectories.

Selection is an explicit rule, not a hidden weighted average: a lossless policy
wins on saved time; if every policy loses gain, the smallest loss wins and saved
time breaks ties. Training trajectories and the reserved evaluation set are
declared separately; reserved cases never participate in the choice.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.scheduler.domain.stop import ExplorationPolicy, TrajectoryPoint, replay_stop_policy
from app.scheduler.lab.manifest import SCHEMA_VERSION

POLICY_VERSION = "w11-experimental-1"

CALIBRATION_CANDIDATES: Mapping[str, ExplorationPolicy] = {
    "eager": ExplorationPolicy("w11-eager", 0.0, 0.0, 1, 0, minimum_solutions=1),
    "balanced": ExplorationPolicy("w11-balanced", 0.05, 0.05, 1, 0, minimum_solutions=2),
    "patient": ExplorationPolicy("w11-patient", 0.25, 1.0, 1, 3, minimum_solutions=3),
    "adaptive-a": ExplorationPolicy("w11-adaptive-a", 0.10, 0.5, 1, 2, minimum_solutions=2),
    "adaptive-b": ExplorationPolicy("w11-adaptive-b", 0.20, 1.0, 2, 3, minimum_solutions=3),
}

CANDIDATE_DESCRIPTIONS = {
    "eager": "Stop at the first complete solution; minimum effort.",
    "balanced": "Require two solutions and a short quiet window.",
    "patient": "Require three solutions and a longer quiet window.",
    "adaptive-a": "Two solutions with a medium quiet window and corpus gain expectation.",
    "adaptive-b": "Three solutions, longer window and a significant-gain threshold.",
}

TRAINING_CASES = (
    "c03-shared-cancel",
    "c08-intersection",
    "c10-margin",
    "c11-urgency",
    "c12-multi-mutation",
    "annual-10-loose-cancel",
)

RESERVED_CASES = (
    "c02-single-cancel",
    "c04-proven-impossible",
    "c05-multi-mutation",
    "c06-teacher-scarce",
    "c07-scarce-room",
    "c09-distant-weeks",
    "c13-partial-credit",
    "c14-reserved",
    "c15-protected-window",
)


@dataclass(frozen=True)
class PolicyCandidate:
    candidate_id: str
    exploration: ExplorationPolicy
    description: str


@dataclass(frozen=True)
class CandidateScore:
    candidate_id: str
    runs: int
    saved_seconds: float
    lost_gain: int
    reference_horizon_seconds: float
    early_stops: int = 0


def candidate_policies() -> tuple[PolicyCandidate, ...]:
    return tuple(
        PolicyCandidate(candidate_id, policy, CANDIDATE_DESCRIPTIONS[candidate_id])
        for candidate_id, policy in CALIBRATION_CANDIDATES.items()
    )


def score_stop_candidates(
    points: Sequence[TrajectoryPoint],
    candidates: Sequence[PolicyCandidate],
    reference_horizon_seconds: float,
) -> tuple[CandidateScore, ...]:
    if not points:
        raise ValueError("Scoring a stopping policy needs at least one trajectory.")
    if not candidates:
        raise ValueError("Scoring needs at least one candidate.")
    scores = []
    for candidate in candidates:
        replay = replay_stop_policy(
            points, candidate.exploration, reference_horizon_seconds=reference_horizon_seconds
        )
        scores.append(
            CandidateScore(
                candidate_id=candidate.candidate_id,
                runs=1,
                saved_seconds=round(replay.saved_seconds, 3),
                lost_gain=1 if replay.lost_gain else 0,
                reference_horizon_seconds=reference_horizon_seconds,
                early_stops=0 if replay.reason == "TRAJECTORY_EXHAUSTED" else 1,
            )
        )
    return tuple(scores)


def aggregate_scores(scores: Sequence[CandidateScore]) -> tuple[CandidateScore, ...]:
    groups: dict[str, list[CandidateScore]] = {}
    for score in scores:
        groups.setdefault(score.candidate_id, []).append(score)
    aggregated = []
    for candidate_id, rows in sorted(groups.items()):
        aggregated.append(
            CandidateScore(
                candidate_id=candidate_id,
                runs=sum(row.runs for row in rows),
                saved_seconds=round(sum(row.saved_seconds for row in rows), 3),
                lost_gain=sum(row.lost_gain for row in rows),
                reference_horizon_seconds=rows[0].reference_horizon_seconds,
                early_stops=sum(row.early_stops for row in rows),
            )
        )
    return tuple(aggregated)


def select_candidate(scores: Sequence[CandidateScore]) -> CandidateScore | None:
    """Adopt a stopping policy only with evidence of an early, lossless stop.

    A policy that never stopped before the reference horizon (exhausted
    trajectory) has no demonstrated saving. A lossy policy is a quality/time
    trade-off that requires explicit owner acceptance. In both cases the full
    safety budget remains active.
    """
    if not scores:
        raise ValueError("The selection needs at least one candidate score.")
    eligible = [
        score
        for score in scores
        if score.lost_gain == 0 and score.early_stops > 0 and score.saved_seconds > 0
    ]
    if not eligible:
        return None
    return max(eligible, key=lambda score: (score.saved_seconds, score.candidate_id))


def scores_from_report(
    report: Mapping[str, Any],
    *,
    reference_horizon_seconds: float,
    case_ids: Sequence[str] | None = None,
) -> tuple[CandidateScore, ...]:
    """Score every declared candidate over the trajectories of a campaign report."""
    selected_ids = None if case_ids is None else set(case_ids)
    raw: list[CandidateScore] = []
    for result in report.get("results", ()):
        if selected_ids is not None and result.get("case_id") not in selected_ids:
            continue
        payload = result.get("payload") or {}
        rows = payload.get("trajectory") or ()
        if not rows:
            continue
        points = [
            TrajectoryPoint(
                float(row["elapsed_seconds"]),
                tuple(int(value) for value in row["incumbent"]),
                True,
            )
            for row in rows
        ]
        raw.extend(score_stop_candidates(points, candidate_policies(), reference_horizon_seconds))
    if not raw:
        raise ValueError("The report contains no trajectory to calibrate against.")
    return aggregate_scores(raw)


def calibration_manifest(
    scores: Sequence[CandidateScore] = (),
) -> dict[str, Any]:
    chosen: CandidateScore | None = select_candidate(scores) if scores else None
    return {
        "schema_version": SCHEMA_VERSION,
        "calibration": {
            "policy_version": POLICY_VERSION,
            "status": "experimental",
            "selection_rule": (
                "lossless policy with the largest saved time; otherwise smallest "
                "lost gain, then largest saved time"
            ),
            "candidates": [
                {
                    "candidate_id": candidate.candidate_id,
                    "description": candidate.description,
                    "exploration": {
                        "policy_version": candidate.exploration.version,
                        "minimum_exploration_seconds": (
                            candidate.exploration.minimum_exploration_seconds
                        ),
                        "gain_window_seconds": candidate.exploration.gain_window_seconds,
                        "minimum_significant_gain_days": (
                            candidate.exploration.minimum_significant_gain_days
                        ),
                        "corpus_expected_gain_days": (
                            candidate.exploration.corpus_expected_gain_days
                        ),
                        "minimum_solutions": candidate.exploration.minimum_solutions,
                    },
                }
                for candidate in candidate_policies()
            ],
            "training_cases": list(TRAINING_CASES),
            "reserved_cases": list(RESERVED_CASES),
            "chosen": None
            if chosen is None
            else {
                "candidate_id": chosen.candidate_id,
                "runs": chosen.runs,
                "saved_seconds": chosen.saved_seconds,
                "lost_gain": chosen.lost_gain,
                "early_stops": chosen.early_stops,
                "reference_horizon_seconds": chosen.reference_horizon_seconds,
            },
            "blocked_reason": (
                None
                if chosen is not None
                else (
                    "No lossless stopping policy with a demonstrated early stop saves time "
                    "on the recorded trajectories. A lossy policy requires explicit owner "
                    "acceptance of the quality/time trade-off; the full safety budget "
                    "remains active."
                )
            ),
            "online_evaluation": (
                "Pending: run the owner-approved policy on reserved families and compare "
                "saved time against the lost product-vector gain before activation."
            ),
            "scores": [
                {
                    "candidate_id": score.candidate_id,
                    "runs": score.runs,
                    "saved_seconds": score.saved_seconds,
                    "lost_gain": score.lost_gain,
                    "early_stops": score.early_stops,
                    "reference_horizon_seconds": score.reference_horizon_seconds,
                }
                for score in scores
            ],
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline calibration of stopping policies.")
    parser.add_argument(
        "--report", required=True, action="append", help="Trajectory campaign report; repeatable."
    )
    parser.add_argument("--out", required=True)
    parser.add_argument("--horizon", type=float, required=True)
    parser.add_argument("--case", action="append", dest="case_ids")
    args = parser.parse_args(argv)
    scores: list[CandidateScore] = []
    for path in args.report:
        report = json.loads(Path(path).read_text(encoding="utf-8"))
        scores.extend(
            scores_from_report(
                report,
                reference_horizon_seconds=args.horizon,
                case_ids=args.case_ids,
            )
        )
    data = calibration_manifest(aggregate_scores(scores))
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    chosen = data["calibration"]["chosen"]
    print(f"[w11] calibration chosen={chosen['candidate_id'] if chosen else None}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
