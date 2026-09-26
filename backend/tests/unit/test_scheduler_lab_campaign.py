import json
from dataclasses import replace
from datetime import date, time

import pytest

from app.scheduler.domain.candidate import SchedulingStrategy
from app.scheduler.lab.campaign import (
    CampaignSelectionError,
    campaign_failures,
    case_passes,
    run_campaign_directory,
)
from app.scheduler.lab.fixtures import AssignmentSpec, CaseExpectation, FixtureSpec
from app.scheduler.lab.manifest import CaseSeeds, LabCase, to_manifest
from app.scheduler.lab.reports import CaseOutcome, CaseResult

ORIGIN = date(2026, 9, 21)
FEASIBLE_SPEC = FixtureSpec(
    strategy=SchedulingStrategy.COMPLETE_GENERATION,
    origin=ORIGIN,
    preferred_end_date=date(2026, 10, 30),
    hard_end_date=date(2026, 11, 30),
    timezone_name="Europe/Lisbon",
    grid_slots=((0, time(9), time(10)), (2, time(9), time(10))),
    periods=(
        (date(2026, 9, 21), time(9), time(10)),
        (date(2026, 9, 23), time(9), time(10)),
    ),
    assignments=(AssignmentSpec(1, 100, (100,), (500, 501)),),
)

SINGLE_LESSON_SPEC = FixtureSpec(
    **{
        **FEASIBLE_SPEC.__dict__,
        "assignments": (AssignmentSpec(1, 100, (60,), (500,)),),
        "periods": ((date(2026, 9, 21), time(9), time(10)),),
        "grid_slots": ((0, time(9), time(10)),),
    }
)

INVERTED_SPEC = FixtureSpec(**{**FEASIBLE_SPEC.__dict__, "preferred_end_date": date(2026, 12, 1)})

CASES = (
    LabCase(
        "case-feasible",
        "minimal",
        1,
        CaseExpectation.FEASIBLE_WITH_WITNESS,
        FEASIBLE_SPEC,
        CaseSeeds(1, 2, 3),
    ),
    LabCase(
        "case-infeasible",
        "frontier",
        1,
        CaseExpectation.INFEASIBLE_PROVEN,
        FixtureSpec(
            **{
                **FEASIBLE_SPEC.__dict__,
                "assignments": (AssignmentSpec(1, 100, (200,), (500,)),),
            }
        ),
        CaseSeeds(4, 5, 6),
    ),
    LabCase(
        "case-mutation",
        "minimal",
        1,
        CaseExpectation.FEASIBLE_WITH_WITNESS,
        FEASIBLE_SPEC,
        CaseSeeds(7, 8, 9),
        mutation="DROP_LESSON",
        expected_violations=("COVERAGE_MISMATCH",),
    ),
    LabCase(
        "case-invalid-input",
        "frontier",
        1,
        CaseExpectation.INVALID_INPUT,
        INVERTED_SPEC,
        CaseSeeds(10, 11, 12),
    ),
)


def test_campaign_runs_every_selected_case_and_collects_outputs(tmp_path):
    manifest = to_manifest("campaign-1", CASES)

    report = run_campaign_directory(manifest, tmp_path, commit="abc123")

    outcomes = {result.case_id: result.outcome for result in report.results}
    assert outcomes == {
        "case-feasible": CaseOutcome.VALID,
        "case-infeasible": CaseOutcome.INFEASIBLE,
        "case-mutation": CaseOutcome.INVALID,
        "case-invalid-input": CaseOutcome.INVALID,
    }
    assert campaign_failures(manifest, report) == ()
    stored = json.loads((tmp_path / "case-feasible.json").read_text(encoding="utf-8"))
    assert stored["provenance"]["input_digest"] == report.results[0].input_digest
    assert stored["result"]["expected_outcome"] == "VALID"


def test_campaign_selects_cases_by_identifier(tmp_path):
    manifest = to_manifest("campaign-1", CASES)

    report = run_campaign_directory(manifest, tmp_path, case_ids={"case-feasible"})

    assert [result.case_id for result in report.results] == ["case-feasible"]


def test_unknown_or_empty_selection_is_an_explicit_error(tmp_path):
    manifest = to_manifest("campaign-1", CASES)

    with pytest.raises(CampaignSelectionError):
        run_campaign_directory(manifest, tmp_path, case_ids={"unknown-id"})
    with pytest.raises(CampaignSelectionError):
        run_campaign_directory(manifest, tmp_path, case_ids=set())


def test_valid_data_declared_as_invalid_input_fails_the_campaign(tmp_path):
    case = LabCase(
        "case-wrong-expectation",
        "frontier",
        1,
        CaseExpectation.INVALID_INPUT,
        FEASIBLE_SPEC,
        CaseSeeds(1, 2, 3),
    )
    manifest = to_manifest("campaign-1", (case,))

    report = run_campaign_directory(manifest, tmp_path)

    assert report.results[0].outcome is CaseOutcome.VALID
    assert campaign_failures(manifest, report) == ("case-wrong-expectation",)


def test_mutation_must_be_detected_by_the_declared_code():
    good = LabCase(
        "case-mutation",
        "minimal",
        1,
        CaseExpectation.FEASIBLE_WITH_WITNESS,
        FEASIBLE_SPEC,
        CaseSeeds(7, 8, 9),
        mutation="DROP_LESSON",
        expected_violations=("COVERAGE_MISMATCH",),
    )
    wrong = replace(good, expected_violations=("PROTECTED_LESSON_CHANGED",))
    detected = CaseResult(
        "case-mutation",
        "minimal",
        1,
        CaseOutcome.INVALID,
        "digest",
        violations=("COVERAGE_MISMATCH",),
        expected_outcome=CaseOutcome.INVALID,
    )

    assert case_passes(good, detected)
    assert not case_passes(wrong, detected)


def test_repair_provenance_includes_the_perturbed_snapshot_digest(tmp_path):
    case = LabCase(
        "case-repair-resume",
        "minimal",
        1,
        CaseExpectation.FEASIBLE_WITH_WITNESS,
        FEASIBLE_SPEC,
        CaseSeeds(1, 0, 1),
    )
    manifest = to_manifest("campaign-1", (case,))

    first = run_campaign_directory(manifest, tmp_path, mode="repair", time_limit_seconds=5)
    stored = json.loads((tmp_path / "case-repair-resume.json").read_text(encoding="utf-8"))
    assert stored["provenance"]["input_digest"]
    assert first.results[0].input_digest == stored["provenance"]["input_digest"]

    revised = to_manifest("campaign-1", (replace(case, events=(1,)),))
    second = run_campaign_directory(
        revised, tmp_path, mode="repair", time_limit_seconds=5, resume=True
    )

    assert second.results[0].input_digest != first.results[0].input_digest


def test_resume_does_not_run_the_solver_again(tmp_path, monkeypatch):
    import app.scheduler.lab.campaign as campaign_module

    calls = {"count": 0}
    original = campaign_module._evaluate_prepared

    def counting(*args, **kwargs):
        calls["count"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(campaign_module, "_evaluate_prepared", counting)
    manifest = to_manifest("campaign-1", (CASES[0],))

    run_campaign_directory(manifest, tmp_path, commit="abc", code_identity="tree-1")
    assert calls["count"] == 1

    run_campaign_directory(manifest, tmp_path, commit="abc", code_identity="tree-1", resume=True)
    assert calls["count"] == 1


def test_resume_reuses_only_identical_provenance(tmp_path):
    manifest = to_manifest("campaign-1", (CASES[0],))
    first = run_campaign_directory(manifest, tmp_path, commit="abc", code_identity="tree-1")
    reused = run_campaign_directory(
        manifest, tmp_path, commit="abc", code_identity="tree-1", resume=True
    )
    reseeded = run_campaign_directory(
        manifest, tmp_path, commit="abc", code_identity="tree-2", resume=True
    )

    assert first.results[0].input_digest == reused.results[0].input_digest
    stored = json.loads((tmp_path / "case-feasible.json").read_text(encoding="utf-8"))
    assert stored["provenance"]["code_identity"] == "tree-2"
    assert reseeded.results[0].input_digest == first.results[0].input_digest


def test_resume_does_not_reuse_stale_evidence_after_inputs_change(tmp_path):
    manifest = to_manifest("campaign-1", (CASES[0],))
    run_campaign_directory(manifest, tmp_path, commit="original")
    changed = replace(
        CASES[0],
        spec=FixtureSpec(
            **{
                **FEASIBLE_SPEC.__dict__,
                "assignments": (AssignmentSpec(1, 100, (200,), (500,)),),
            }
        ),
    )
    revised = to_manifest("campaign-1", (changed,))

    resumed = run_campaign_directory(revised, tmp_path, commit="different", resume=True)

    assert resumed.results[0].outcome is not CaseOutcome.VALID
    assert campaign_failures(revised, resumed) == ("case-feasible",)


def test_truncated_result_files_are_not_reused(tmp_path):
    manifest = to_manifest("campaign-1", (CASES[0],))
    run_campaign_directory(manifest, tmp_path, commit="abc")
    (tmp_path / "case-feasible.json").write_text("{ truncated", encoding="utf-8")

    resumed = run_campaign_directory(manifest, tmp_path, commit="abc", resume=True)

    assert resumed.results[0].outcome is CaseOutcome.VALID


def test_case_exceptions_become_error_results_without_aborting_the_campaign(tmp_path):
    error_case = LabCase(
        "case-error",
        "minimal",
        1,
        CaseExpectation.FEASIBLE_WITH_WITNESS,
        SINGLE_LESSON_SPEC,
        CaseSeeds(1, 2, 3),
        mutation="RESOURCE_CONFLICT",
        expected_violations=("RESOURCE_CONFLICT",),
    )
    manifest = to_manifest("campaign-1", (error_case, CASES[0]))

    report = run_campaign_directory(manifest, tmp_path)

    outcomes = {result.case_id: result.outcome for result in report.results}
    assert outcomes["case-error"] is CaseOutcome.ERROR
    assert outcomes["case-feasible"] is CaseOutcome.VALID
    assert report.results[0].error != ""
    assert campaign_failures(manifest, report) == ("case-error",)


def test_an_error_blocks_a_campaign_even_with_an_exploratory_expectation():
    case = LabCase(
        "case-exploratory",
        "minimal",
        1,
        CaseExpectation.EXPLORATORY_UNKNOWN,
        FEASIBLE_SPEC,
        CaseSeeds(1, 2, 3),
    )
    error = CaseResult(
        "case-exploratory",
        "minimal",
        1,
        CaseOutcome.ERROR,
        "digest",
        error="boom",
    )

    assert case_passes(case, error) is False


def test_inconclusive_and_invalid_block_an_exploratory_case():
    case = LabCase(
        "case-exploratory",
        "minimal",
        1,
        CaseExpectation.EXPLORATORY_UNKNOWN,
        FEASIBLE_SPEC,
        CaseSeeds(1, 2, 3),
    )

    for outcome in (CaseOutcome.INCONCLUSIVE, CaseOutcome.INVALID, CaseOutcome.OMITTED):
        result = CaseResult("case-exploratory", "minimal", 1, outcome, "digest")
        assert case_passes(case, result) is False, outcome


def test_settled_exploratory_outcomes_still_pass():
    case = LabCase(
        "case-exploratory",
        "minimal",
        1,
        CaseExpectation.EXPLORATORY_UNKNOWN,
        FEASIBLE_SPEC,
        CaseSeeds(1, 2, 3),
    )

    for outcome in (CaseOutcome.VALID, CaseOutcome.INFEASIBLE):
        result = CaseResult("case-exploratory", "minimal", 1, outcome, "digest")
        assert case_passes(case, result) is True, outcome
