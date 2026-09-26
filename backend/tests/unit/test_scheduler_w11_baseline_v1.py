"""W11 baseline: candidate parameters and explicit decisions, no invented p95."""

from app.scheduler.lab.baseline import (
    BASELINE_VERSION,
    ROOM_GROUPING_DECISION,
    baseline_manifest,
    candidate_workers,
    families_from,
)
from app.scheduler.lab.performance import RunSample


def _sample(workers: int, wall: float, outcome: str = "COMPLETE", family: str = "C18", **metrics):
    return RunSample(
        case_id="case",
        family=family,
        workers=workers,
        repeat=0,
        seed=1,
        outcome=outcome,
        valid=outcome == "COMPLETE",
        wall_seconds=wall,
        search_seconds=wall,
        cpu_seconds=wall,
        peak_python_bytes=1,
        metrics=metrics,
    )


def test_candidate_workers_excludes_configurations_with_fewer_valid_runs():
    samples = (
        _sample(1, 20.0, "INCONCLUSIVE", objective_days=1),
        _sample(1, 18.0, "INCONCLUSIVE", objective_days=1),
        _sample(2, 12.0, objective_days=10),
        _sample(2, 18.0, objective_days=10),
        _sample(4, 11.0, objective_days=10),
        _sample(4, 13.0, objective_days=10),
    )

    assert candidate_workers(samples) == 4


def test_a_quality_dominated_configuration_loses_even_when_cheaper():
    samples = (
        _sample(1, 5.0, objective_days=50),
        _sample(2, 30.0, objective_days=10),
        _sample(4, 40.0, objective_days=10),
    )

    assert candidate_workers(samples) == 2


def test_cost_decides_between_equally_good_configurations():
    samples = (
        _sample(1, 30.0, objective_days=10),
        _sample(2, 10.0, objective_days=10),
        _sample(4, 10.0, objective_days=10),
    )

    assert candidate_workers(samples) == 2

    tie = (
        _sample(2, 10.0, objective_days=10),
        _sample(4, 10.0, objective_days=10),
    )
    assert candidate_workers(tie) == 2


def test_families_report_distributions_not_only_a_mean():
    samples = (
        _sample(1, 10.0, family="C18"),
        _sample(1, 30.0, family="C18"),
        _sample(1, 5.0, family="C19"),
    )

    families = families_from(samples)

    assert families["C18"]["runs"] == 2
    assert families["C18"]["median_wall_seconds"] == 20.0
    assert families["C18"]["p90_wall_seconds"] == 30.0


def test_the_baseline_has_no_invented_p95_target_and_an_explicit_room_decision():
    manifest = baseline_manifest()

    baseline = manifest["baseline"]
    assert baseline["version"] == BASELINE_VERSION
    assert baseline["target_p95_seconds"] is None
    assert "observed" in baseline["target_p95_note"].lower()
    assert baseline["room_grouping"]["decision"] == ROOM_GROUPING_DECISION["decision"]
    assert baseline["room_grouping"]["reason"]
    assert baseline["status"] == "experimental"


def test_the_baseline_records_evidence_when_measurements_exist():
    samples = (_sample(2, 10.0), _sample(2, 14.0))

    manifest = baseline_manifest(samples=samples)

    baseline = manifest["baseline"]
    assert baseline["candidate_workers"] == 2
    assert baseline["families"]["C18"]["runs"] == 2
    assert baseline["evidence"]["samples"] == 2
