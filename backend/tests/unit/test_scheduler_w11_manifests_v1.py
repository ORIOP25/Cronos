"""W11 versioned artifacts: calibration and baseline manifest invariants."""

import json
from pathlib import Path

from app.scheduler.lab.baseline import BASELINE_VERSION, ROOM_GROUPING_DECISION
from app.scheduler.lab.calibration import candidate_policies

LAB = Path(__file__).resolve().parents[1] / "scheduler_lab"


def _load(name: str) -> dict:
    return json.loads((LAB / name).read_text(encoding="utf-8"))


def test_the_calibration_manifest_matches_the_declared_candidates():
    calibration = _load("w11_calibration_manifest.json")["calibration"]

    declared = {row["candidate_id"] for row in calibration["candidates"]}
    assert declared == {candidate.candidate_id for candidate in candidate_policies()}
    assert calibration["status"] == "experimental"
    assert set(calibration["training_cases"]).isdisjoint(calibration["reserved_cases"])
    assert calibration["selection_rule"]


def test_the_calibration_keeps_the_explicit_verdict_even_when_inconclusive():
    calibration = _load("w11_calibration_manifest.json")["calibration"]

    if calibration["chosen"] is None:
        assert calibration["blocked_reason"]
        assert calibration["online_evaluation"]
        assert all(
            row["saved_seconds"] <= 0 or row["lost_gain"] > 0 for row in calibration["scores"]
        )
    else:
        assert calibration["chosen"]["lost_gain"] == 0
        assert calibration["chosen"]["saved_seconds"] > 0


def test_the_reserved_evaluation_is_disjoint_from_calibration_cases():
    calibration = _load("w11_calibration_manifest.json")["calibration"]
    reserved_repair = _load("reserved_manifest.json")
    reserved_annual = _load("reserved_annual_manifest.json")

    reserved_ids = {row["case_id"] for row in reserved_repair["cases"]} | {
        row["case_id"] for row in reserved_annual["cases"]
    }
    known = set(calibration["training_cases"]) | set(calibration["reserved_cases"])
    assert reserved_ids.isdisjoint(known)


def test_the_baseline_manifest_has_no_invented_target_and_explicit_decisions():
    baseline = _load("w11_baseline_manifest.json")["baseline"]

    assert baseline["version"] == BASELINE_VERSION
    assert baseline["status"] == "experimental"
    assert baseline["target_p95_seconds"] is None
    assert baseline["room_grouping"]["decision"] == ROOM_GROUPING_DECISION["decision"]
    assert baseline["room_grouping"]["reason"]
    assert baseline["candidate_workers"] in (None, 1, 2, 4, 8)
    assert baseline["families"]
    assert baseline["evidence"]["samples"] >= 1
