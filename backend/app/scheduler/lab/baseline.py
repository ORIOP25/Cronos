"""W11 baseline: versioned candidate parameters and explicit product decisions.

No fixed p95 target exists (D05/D06): the observed p90 is reported for the local
sample and the remote baseline is established separately in W13. The equivalent
room grouping is a decision recorded with its reason, not a silent default.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.scheduler.lab.manifest import SCHEMA_VERSION
from app.scheduler.lab.performance import RunSample, sample_from_dict

BASELINE_VERSION = "w11-baseline-1"

ROOM_GROUPING_DECISION = {
    "decision": "not-adopted",
    "reason": (
        "Room matching is not the dominant measured phase and equivalent rooms keep "
        "distinct physical identities; grouping would weaken publication and audit "
        "without a measured gain."
    ),
}


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def _median_quality(rows: Sequence[RunSample]) -> float | None:
    for key in ("objective_days", "excess_days"):
        values = [row.metrics[key] for row in rows if key in row.metrics]
        if values:
            return statistics.median(values)
    return None


def candidate_workers(samples: Sequence[RunSample]) -> int | None:
    """Validity first, then quality (dominated configurations drop out), then cost.

    Among configurations with the best validity, any whose median completion
    metric is worse than the best observed is dominated and discarded; the
    cheapest remaining configuration (CPU per run, then median wall, then fewer
    workers) wins. Quality decides the shortlist, cost decides the winner.
    """
    if not samples:
        return None
    groups: dict[int, list[RunSample]] = {}
    for sample in samples:
        groups.setdefault(sample.workers, []).append(sample)
    best_validity = max(sum(row.valid for row in rows) for rows in groups.values())
    eligible = {
        workers: rows
        for workers, rows in groups.items()
        if sum(row.valid for row in rows) == best_validity
    }
    qualities = {workers: _median_quality(rows) for workers, rows in eligible.items()}
    known = [value for value in qualities.values() if value is not None]
    if known:
        best_quality = min(known)
        competitive = {
            workers: rows
            for workers, rows in eligible.items()
            if qualities[workers] is None or qualities[workers] <= best_quality
        }
    else:
        competitive = eligible

    def cost_per_run(rows: list[RunSample]) -> float:
        return sum(row.cpu_seconds for row in rows) / len(rows)

    return min(
        competitive,
        key=lambda workers: (
            cost_per_run(competitive[workers]),
            statistics.median(row.wall_seconds for row in competitive[workers]),
            workers,
        ),
    )


def families_from(samples: Sequence[RunSample]) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[RunSample]] = {}
    for sample in samples:
        groups.setdefault(sample.family, []).append(sample)
    families: dict[str, dict[str, Any]] = {}
    for family, rows in sorted(groups.items()):
        walls = [row.wall_seconds for row in rows]
        families[family] = {
            "runs": len(rows),
            "valid": sum(row.valid for row in rows),
            "median_wall_seconds": statistics.median(walls),
            "p90_wall_seconds": _percentile(walls, 0.9),
            "total_cpu_seconds": round(sum(row.cpu_seconds for row in rows), 3),
        }
    return families


def baseline_manifest(
    *,
    samples: Sequence[RunSample] = (),
    calibration: Mapping[str, Any] | None = None,
    stop_policy: str | None = None,
) -> dict[str, Any]:
    chosen_stop = stop_policy
    if chosen_stop is None and calibration is not None:
        chosen = (calibration.get("calibration") or {}).get("chosen")
        chosen_stop = None if chosen is None else chosen.get("candidate_id")
    baseline: dict[str, Any] = {
        "version": BASELINE_VERSION,
        "status": "experimental",
        "environment": "local-docker",
        "target_p95_seconds": None,
        "target_p95_note": (
            "No p95 target exists; p90 is an observed local result and the remote "
            "baseline is established separately in W13."
        ),
        "candidate_workers": candidate_workers(samples),
        "room_grouping": dict(ROOM_GROUPING_DECISION),
        "recovery_policy": "v1-uncalibrated",
        "stop_policy": chosen_stop,
        "stop_policy_status": (
            "not-calibrated" if chosen_stop is None else "candidate-unconfirmed"
        ),
        "stop_policy_note": (
            "The stopping policy is an offline candidate only. Online evaluation on a "
            "reserved family did not confirm a saving at the tested budget, so it is not "
            "activated and the full safety budget remains in force; adoption requires "
            "owner acceptance and a confirming reserved experiment."
        ),
        "families": families_from(samples),
        "evidence": {"samples": len(samples)},
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "baseline": baseline,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the versioned W11 baseline manifest.")
    parser.add_argument(
        "--samples",
        required=True,
        action="append",
        help="Performance report JSON; repeat for several reports.",
    )
    parser.add_argument("--calibration", default=None, help="Calibration manifest JSON.")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    samples = [
        sample_from_dict(row)
        for path in args.samples
        for row in json.loads(Path(path).read_text(encoding="utf-8"))["samples"]
    ]
    calibration = (
        None
        if args.calibration is None
        else json.loads(Path(args.calibration).read_text(encoding="utf-8"))
    )
    manifest = baseline_manifest(samples=samples, calibration=calibration)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    baseline = manifest["baseline"]
    print(
        f"[w11] baseline {baseline['version']}: workers={baseline['candidate_workers']} "
        f"stop_policy={baseline['stop_policy']} samples={baseline['evidence']['samples']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
