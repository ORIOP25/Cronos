"""W10 manifests: declared matrix, drift protection and campaign integration."""

import json
from pathlib import Path

from app.scheduler.lab.campaign import run_campaign_directory
from app.scheduler.lab.combined import (
    annual_replay_manifest,
    boundary_manifest,
    combined_manifest,
    reserved_annual_manifest,
    reserved_repair_manifest,
)
from app.scheduler.lab.manifest import from_manifest
from app.scheduler.lab.matrix import (
    pairwise_coverage,
    parse_matrix,
    validate_matrix,
)

LAB = Path(__file__).resolve().parents[1] / "scheduler_lab"


def _load(name: str) -> dict:
    return json.loads((LAB / name).read_text(encoding="utf-8"))


def test_the_checked_in_manifests_match_their_generators():
    assert _load("combined_manifest.json") == combined_manifest()
    assert _load("boundary_manifest.json") == boundary_manifest()
    assert _load("annual_replay_manifest.json") == annual_replay_manifest()
    assert _load("reserved_manifest.json") == reserved_repair_manifest()
    assert _load("reserved_annual_manifest.json") == reserved_annual_manifest()


def test_the_declared_matrix_is_coherent_and_complete_when_executed():
    manifest = combined_manifest()
    _campaign_id, cases = from_manifest(manifest)
    executed = {case.case_id for case in cases}

    assert validate_matrix(manifest, campaign_case_ids=executed) == ()

    coverage = pairwise_coverage(parse_matrix(manifest), executed)

    assert coverage.complete
    assert len(coverage.pairs) > 0
    assert len(manifest["matrix"]["axes"]) >= 8
    assert manifest["coverage"]["critical_interactions"]


def test_every_declared_matrix_case_has_a_constructive_witness():
    from app.scheduler.lab.campaign import prepare_case

    manifest = combined_manifest()
    _campaign_id, cases = from_manifest(manifest)

    for case in cases:
        prepared = prepare_case(case, "repair")
        assert prepared.digest, case.case_id
        assert prepared.recovery is not None, case.case_id
        assert prepared.recovery.expectation.value == "FEASIBLE_WITH_WITNESS", case.case_id


def test_the_boundary_matrix_covers_pressure_and_restoration_pairs():
    manifest = boundary_manifest()
    _campaign_id, cases = from_manifest(manifest)
    executed = {case.case_id for case in cases}

    coverage = pairwise_coverage(parse_matrix(manifest), executed)

    assert validate_matrix(manifest, campaign_case_ids=executed) == ()
    assert coverage.complete
    assert all(len(pair.covered_by) == 1 for pair in coverage.pairs)


def test_the_annual_replay_manifest_declares_the_mandatory_scales():
    manifest = annual_replay_manifest()

    assert manifest["replay"]["scales"] == [10, 30, 45, 60]
    _campaign_id, cases = from_manifest(manifest)

    assert {case.annual.class_count for case in cases} == {10, 30, 45, 60}
    assert all(case.annual.events >= 1 for case in cases)


def test_a_pair_case_runs_end_to_end_in_repair_mode(tmp_path):
    manifest = combined_manifest()

    report = run_campaign_directory(
        manifest,
        tmp_path,
        case_ids=("w10-pair-01",),
        commit="test",
        mode="repair",
        time_limit_seconds=10,
    )

    result = report.results[0]
    assert result.outcome.value in {"VALID", "INFEASIBLE", "INCONCLUSIVE"}
    if result.outcome.value == "VALID":
        assert result.payload["validation"]["valid"] is True
