"""W11 performance harness: internal workers comparison and phase profiling.

The harness measures the complete pipeline per run, interleaves configuration
order to reduce warm-up bias, and reports wall time, CPU seconds, Python-level
peak memory and per-phase statistics. It never hides failures: every outcome is
recorded and summarised.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import tracemalloc
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.scheduler.composition import generate_schedule, repair_published_schedule
from app.scheduler.domain.stop import ExplorationPolicy
from app.scheduler.lab.calibration import CALIBRATION_CANDIDATES
from app.scheduler.lab.campaign import recovery_case_for
from app.scheduler.lab.manifest import LabCase, build_case, from_manifest
from app.scheduler.lab.recovery import laboratory_policy

PHASE_KEYS = ("build_ms", "solve_ms", "room_ms", "variables", "windows")


@dataclass(frozen=True)
class RunSample:
    case_id: str
    family: str
    workers: int
    repeat: int
    seed: int
    outcome: str
    valid: bool
    wall_seconds: float
    search_seconds: float
    cpu_seconds: float
    peak_python_bytes: int
    mode: str = "generator"
    peak_rss_bytes: int | None = None
    phases: Mapping[str, int] = field(default_factory=dict)
    metrics: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkerSummary:
    workers: int
    runs: int
    settled: int
    valid: int
    failures: int
    median_wall_seconds: float
    p90_wall_seconds: float
    total_cpu_seconds: float
    median_objective_days: float | None = None
    median_excess_days: float | None = None
    median_rss_bytes: float | None = None

    @property
    def speedup_cpu(self) -> float:
        return self.total_cpu_seconds


def interleaved_schedule(workers: Sequence[int], repeats: int) -> tuple[tuple[int, int], ...]:
    """Round-robin configurations: one repeat of every worker before the next."""
    return tuple((worker, repeat) for repeat in range(repeats) for worker in workers)


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def _rss_high_water_bytes() -> int | None:
    """Process high-water RSS (Linux only); a monotonic ceiling, not per-run."""
    try:
        with open("/proc/self/status", encoding="ascii") as handle:
            for line in handle:
                if line.startswith("VmHWM:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError):
        return None
    return None


def _median_quality(rows: Sequence[RunSample], key: str) -> float | None:
    values = [row.metrics[key] for row in rows if key in row.metrics]
    return statistics.median(values) if values else None


def summarize_workers(samples: Sequence[RunSample]) -> tuple[WorkerSummary, ...]:
    groups: dict[int, list[RunSample]] = {}
    for sample in samples:
        groups.setdefault(sample.workers, []).append(sample)
    summaries = []
    for workers, rows in sorted(groups.items()):
        walls = [row.wall_seconds for row in rows]
        rss = [row.peak_rss_bytes for row in rows if row.peak_rss_bytes]
        summaries.append(
            WorkerSummary(
                workers=workers,
                runs=len(rows),
                settled=sum(row.outcome in ("COMPLETE", "INFEASIBLE") for row in rows),
                valid=sum(row.valid for row in rows),
                failures=sum(row.outcome not in ("COMPLETE", "INFEASIBLE") for row in rows),
                median_wall_seconds=statistics.median(walls),
                p90_wall_seconds=_percentile(walls, 0.9),
                total_cpu_seconds=round(sum(row.cpu_seconds for row in rows), 3),
                median_objective_days=_median_quality(rows, "objective_days"),
                median_excess_days=_median_quality(rows, "excess_days"),
                median_rss_bytes=statistics.median(rss) if rss else None,
            )
        )
    return tuple(summaries)


def family_summaries(samples: Sequence[RunSample]) -> tuple[dict[str, Any], ...]:
    """Per-family, per-worker distributions instead of one global median."""
    groups: dict[tuple[str, int], list[RunSample]] = {}
    for sample in samples:
        groups.setdefault((sample.family, sample.workers), []).append(sample)
    rows = []
    for (family, workers), group in sorted(groups.items()):
        walls = [row.wall_seconds for row in group]
        rows.append(
            {
                "family": family,
                "workers": workers,
                "mode": group[0].mode,
                "runs": len(group),
                "valid": sum(row.valid for row in group),
                "failures": sum(row.outcome not in ("COMPLETE", "INFEASIBLE") for row in group),
                "median_wall_seconds": statistics.median(walls),
                "p90_wall_seconds": _percentile(walls, 0.9),
                "total_cpu_seconds": round(sum(row.cpu_seconds for row in group), 3),
                "median_objective_days": _median_quality(group, "objective_days"),
                "median_excess_days": _median_quality(group, "excess_days"),
                "median_rss_bytes": statistics.median(
                    [row.peak_rss_bytes for row in group if row.peak_rss_bytes]
                )
                if any(row.peak_rss_bytes for row in group)
                else None,
            }
        )
    return tuple(rows)


def _sample_metrics(stats: Mapping[str, int]) -> dict[str, int]:
    return {key: int(stats[key]) for key in PHASE_KEYS if key in stats}


def measure_case(
    case: LabCase,
    *,
    workers: int,
    repeat: int,
    time_limit_seconds: float,
    solver_seed: int,
    mode: str = "generator",
    exploration: ExplorationPolicy | None = None,
) -> RunSample:
    """Measure one run of one case configuration."""
    if mode == "repair":
        fixture = None if case.spec is not None else build_case(case)
        recovery = recovery_case_for(case, fixture)
        snapshot = recovery.snapshot
        baseline = recovery.baseline
        policy = laboratory_policy(snapshot)
    else:
        fixture = build_case(case)
        snapshot = fixture.snapshot
        baseline = None
        policy = None
    tracemalloc.start()
    started = time.perf_counter()
    cpu_started = time.process_time()
    if mode == "repair":
        outcome = repair_published_schedule(
            snapshot,
            recovery.periods,
            baseline,
            policy,
            exploration=exploration,
            time_limit_seconds=time_limit_seconds,
            num_workers=workers,
            random_seed=solver_seed,
        )
    else:
        outcome = generate_schedule(
            snapshot,
            fixture.periods,
            time_limit_seconds=time_limit_seconds,
            num_workers=workers,
            random_seed=solver_seed,
        )
    cpu_seconds = time.process_time() - cpu_started
    wall_seconds = time.perf_counter() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    metrics: dict[str, int] = {}
    if mode == "repair":
        if outcome.quality is not None:
            metrics["disruption_cost"] = outcome.quality.disruption.total_cost
            metrics["changed_lessons"] = len(outcome.quality.disruption.changes)
        if outcome.summary is not None:
            metrics["excess_days"] = outcome.summary.excess_days
    else:
        if outcome.objective_days is not None:
            metrics["objective_days"] = outcome.objective_days
        if outcome.quality is not None:
            metrics["teacher_gap_minutes"] = outcome.quality.teacher_gap_minutes
            metrics["class_gap_minutes"] = outcome.quality.class_gap_minutes
    return RunSample(
        case_id=case.case_id,
        family=case.family,
        workers=workers,
        repeat=repeat,
        seed=solver_seed,
        outcome=outcome.outcome,
        valid=bool(outcome.report is not None and outcome.report.valid),
        wall_seconds=round(wall_seconds, 3),
        search_seconds=round(outcome.search_seconds, 3),
        cpu_seconds=round(cpu_seconds, 3),
        peak_python_bytes=peak,
        mode=mode,
        peak_rss_bytes=_rss_high_water_bytes(),
        phases=_sample_metrics(outcome.statistics),
        metrics=metrics,
    )


def run_matrix(
    manifest: Mapping[str, Any],
    *,
    case_ids: Sequence[str] | None = None,
    workers: Sequence[int] = (1,),
    repeats: int = 1,
    seeds: Sequence[int] = (1,),
    time_limit_seconds: float = 30.0,
    solver_seed: int = 1,
    mode: str = "generator",
    exploration: ExplorationPolicy | None = None,
) -> tuple[RunSample, ...]:
    if repeats < 1:
        raise ValueError("At least one repeat is required.")
    if not seeds:
        raise ValueError("At least one solver seed is required.")
    _campaign_id, cases = from_manifest(manifest)
    selected = [case for case in cases if case_ids is None or case.case_id in set(case_ids)]
    if not selected:
        raise ValueError("The performance selection is empty.")
    samples: list[RunSample] = []
    for case in selected:
        for seed in seeds:
            for worker_count, repeat in interleaved_schedule(workers, repeats):
                samples.append(
                    measure_case(
                        case,
                        workers=worker_count,
                        repeat=repeat,
                        time_limit_seconds=time_limit_seconds,
                        solver_seed=seed,
                        mode=mode,
                        exploration=exploration,
                    )
                )
    return tuple(samples)


def sample_to_dict(sample: RunSample) -> dict[str, Any]:
    return {
        "case_id": sample.case_id,
        "family": sample.family,
        "workers": sample.workers,
        "repeat": sample.repeat,
        "seed": sample.seed,
        "mode": sample.mode,
        "outcome": sample.outcome,
        "valid": sample.valid,
        "wall_seconds": sample.wall_seconds,
        "search_seconds": sample.search_seconds,
        "cpu_seconds": sample.cpu_seconds,
        "peak_python_bytes": sample.peak_python_bytes,
        "peak_rss_bytes": sample.peak_rss_bytes,
        "phases": dict(sample.phases),
        "metrics": dict(sample.metrics),
    }


def sample_from_dict(data: Mapping[str, Any]) -> RunSample:
    return RunSample(
        case_id=data["case_id"],
        family=data["family"],
        workers=int(data["workers"]),
        repeat=int(data["repeat"]),
        seed=int(data["seed"]),
        outcome=data["outcome"],
        valid=bool(data["valid"]),
        wall_seconds=float(data["wall_seconds"]),
        search_seconds=float(data["search_seconds"]),
        cpu_seconds=float(data["cpu_seconds"]),
        peak_python_bytes=int(data["peak_python_bytes"]),
        mode=data.get("mode", "generator"),
        peak_rss_bytes=(
            None if data.get("peak_rss_bytes") is None else int(data["peak_rss_bytes"])
        ),
        phases=dict(data.get("phases", {})),
        metrics=dict(data.get("metrics", {})),
    )


def phase_summary(samples: Sequence[RunSample]) -> dict[str, Any]:
    """Aggregate observed phases and name the dominant measured cost."""
    totals: dict[str, int] = {}
    for sample in samples:
        for key, value in sample.phases.items():
            if key in ("build_ms", "solve_ms", "room_ms"):
                totals[key] = totals.get(key, 0) + int(value)
    total = sum(totals.values())
    dominant = max(totals, key=lambda key: totals[key]) if totals else None
    return {
        **{key: totals.get(key, 0) for key in ("build_ms", "solve_ms", "room_ms")},
        "total_ms": total,
        "dominant_phase": dominant,
    }


def report_to_dict(campaign_id: str, commit: str, samples: Sequence[RunSample]) -> dict[str, Any]:
    return {
        "campaign_id": campaign_id,
        "commit": commit,
        "samples": [sample_to_dict(sample) for sample in samples],
        "summaries": [
            {
                "workers": summary.workers,
                "runs": summary.runs,
                "settled": summary.settled,
                "valid": summary.valid,
                "failures": summary.failures,
                "median_wall_seconds": summary.median_wall_seconds,
                "p90_wall_seconds": summary.p90_wall_seconds,
                "total_cpu_seconds": summary.total_cpu_seconds,
                "median_objective_days": summary.median_objective_days,
                "median_excess_days": summary.median_excess_days,
                "median_rss_bytes": summary.median_rss_bytes,
            }
            for summary in summarize_workers(samples)
        ],
        "families": list(family_summaries(samples)),
        "phases": phase_summary(samples),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure internal worker configurations.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--workers", default="1,2,4,8")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--seeds", default="1")
    parser.add_argument("--time-limit", type=float, default=30.0)
    parser.add_argument("--mode", choices=("generator", "repair"), default="generator")
    parser.add_argument(
        "--exploration",
        default=None,
        choices=sorted(CALIBRATION_CANDIDATES),
        help="Apply a declared stopping policy to repair runs.",
    )
    parser.add_argument("--commit", default="unknown")
    args = parser.parse_args(argv)
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    workers = tuple(int(value) for value in args.workers.split(","))
    seeds = tuple(int(value) for value in args.seeds.split(","))
    samples = run_matrix(
        manifest,
        case_ids=args.case_ids,
        workers=workers,
        repeats=args.repeats,
        seeds=seeds,
        time_limit_seconds=args.time_limit,
        mode=args.mode,
        exploration=(
            None if args.exploration is None else CALIBRATION_CANDIDATES[args.exploration]
        ),
    )
    data = report_to_dict(manifest.get("campaign_id", "performance"), args.commit, samples)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    for summary in summarize_workers(samples):
        print(
            f"[w11] workers={summary.workers}: valid={summary.valid}/{summary.runs} "
            f"median_wall={summary.median_wall_seconds}s cpu={summary.total_cpu_seconds}s"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
