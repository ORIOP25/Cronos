"""W06 lab: recovery fixtures, baseline serialization and repair campaign mode."""

import json
from pathlib import Path

from app.scheduler.domain.candidate import SchedulingStrategy
from app.scheduler.domain.serialization import snapshot_from_dict, snapshot_to_dict
from app.scheduler.lab.campaign import run_campaign_directory
from app.scheduler.lab.recovery import (
    EVENTS,
    build_recovery_case,
    laboratory_policy,
    recovery_event,
)
from tests.unit.test_scheduler_recovery_solver_v1 import _spec

MANIFEST = Path(__file__).resolve().parents[1] / "scheduler_lab" / "repair_manifest.json"


def test_a_recovery_case_carries_an_adaptive_baseline_and_a_known_event():
    case = build_recovery_case("lab-recovery", _spec(), event_seed=0)

    assert case.snapshot.strategy is SchedulingStrategy.ADAPTIVE_RECOVERY
    assert case.snapshot.baseline_lessons == case.baseline.lessons
    assert case.event in EVENTS
    assert recovery_event(0) == EVENTS[0]
    assert case.expectation.value in {"FEASIBLE_WITH_WITNESS", "INFEASIBLE_PROVEN"}


def test_the_laboratory_policy_covers_exactly_the_preference_horizon():
    case = build_recovery_case("lab-policy", _spec(), event_seed=1)

    policy = laboratory_policy(case.snapshot)

    days = (case.snapshot.preferred_end_date - case.snapshot.origin).days
    assert len(policy.daily_slopes) == days
    assert policy.version == "laboratory-default"


def test_the_baseline_survives_snapshot_serialization():
    case = build_recovery_case("lab-roundtrip", _spec(), event_seed=2)

    restored = snapshot_from_dict(snapshot_to_dict(case.snapshot))

    assert restored.baseline_lessons == case.snapshot.baseline_lessons


def test_the_trajectory_campaign_replays_stopping_policies(tmp_path):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    report = run_campaign_directory(
        manifest,
        tmp_path,
        case_ids=("c08-intersection",),
        commit="test",
        mode="trajectory",
        time_limit_seconds=10,
    )

    result = report.results[0]
    assert result.outcome.value in {"VALID", "INCONCLUSIVE"}
    if result.outcome.value == "VALID":
        assert result.metrics["trajectory_points"] >= 1
        assert {"eager", "balanced", "patient"} <= set(result.payload["replays"])
        replay = result.payload["replays"]["patient"]
        assert replay["best_vector"] <= replay["final_vector"]
        assert replay["saved_seconds"] >= 0


def test_the_repair_campaign_serializes_evidence_and_budget(tmp_path):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    report = run_campaign_directory(
        manifest,
        tmp_path,
        case_ids=("c02-single-cancel",),
        commit="test",
        mode="repair",
        time_limit_seconds=10,
    )

    payload = report.results[0].payload
    assert payload["validation"]["valid"] is True
    assert payload["baseline_assessment"]["valid"] is False
    assert payload["quality"]["disruption_cost"] >= 0
    assert "within_budget" in payload["budget"]
    assert report.results[0].metrics["disruption_cost"] >= 0
