from app.scheduler.lab.reports import (
    CampaignReport,
    CaseOutcome,
    CaseResult,
    compare_reports,
    report_from_dict,
    report_to_dict,
    scenario_coverage,
)


def _result(
    case_id, family, outcome, expected, metrics=None, violations=(), digest=None, version=1
):
    return CaseResult(
        case_id=case_id,
        family=family,
        version=version,
        outcome=CaseOutcome(outcome),
        input_digest=digest or f"digest-{case_id}",
        metrics=metrics or {},
        violations=tuple(violations),
        expected_outcome=CaseOutcome(expected),
    )


BASELINE = CampaignReport(
    "campaign-1",
    "commit-a",
    (
        _result("A", "f1", "VALID", "VALID", {"objective": 5}),
        _result("B", "f1", "INFEASIBLE", "INFEASIBLE"),
        _result("C", "f2", "INVALID", "INVALID", violations=("COVERAGE_MISMATCH",)),
    ),
)

CANDIDATE = CampaignReport(
    "campaign-1",
    "commit-b",
    (
        _result("A", "f1", "VALID", "VALID", {"objective": 5}),
        _result("B", "f1", "INVALID", "INFEASIBLE", violations=("COVERAGE_MISMATCH",)),
        _result("D", "f2", "INCONCLUSIVE", "VALID"),
    ),
)


def test_comparison_identifies_regressions_omissions_and_inconclusive_runs():
    comparison = compare_reports(BASELINE, CANDIDATE)

    assert comparison.regressed_case_ids == ("B",)
    assert comparison.omitted_case_ids == ("C",)
    assert comparison.added_case_ids == ("D",)
    assert comparison.inconclusive_case_ids == ("D",)
    assert not comparison.clean


def test_comparison_groups_findings_by_family():
    comparison = compare_reports(BASELINE, CANDIDATE)
    by_family = {row.family: row for row in comparison.by_family}

    assert by_family["f1"].regressed_case_ids == ("B",)
    assert by_family["f2"].omitted_case_ids == ("C",)
    assert by_family["f2"].inconclusive_case_ids == ("D",)


def test_regression_is_detected_against_the_case_expectation():
    before = CampaignReport(
        "audit", "old", (_result("x", "f", "INVALID", "INVALID", digest="old-digest"),)
    )
    after = CampaignReport(
        "audit",
        "new",
        (_result("x", "f", "VALID", "INVALID", digest="different-digest"),),
    )

    comparison = compare_reports(before, after)

    assert comparison.regressed_case_ids == ("x",)
    assert comparison.incomparable_case_ids == ("x",)
    assert not comparison.clean


def test_changed_inputs_without_version_change_are_incomparable():
    before = CampaignReport("c", "old", (_result("x", "f", "VALID", "VALID", digest="a"),))
    after = CampaignReport("c", "new", (_result("x", "f", "VALID", "VALID", digest="b"),))

    comparison = compare_reports(before, after)

    assert comparison.incomparable_case_ids == ("x",)
    assert not comparison.clean


def test_disappearing_metrics_and_policy_changes_are_visible():
    before = CampaignReport(
        "c",
        "old",
        (
            CaseResult(
                "x", "f", 1, CaseOutcome.VALID, "digest", {"objective": 5}, policy_version="p1"
            ),
        ),
    )
    after = CampaignReport(
        "c",
        "new",
        (CaseResult("x", "f", 1, CaseOutcome.VALID, "digest", {}, policy_version="p2"),),
    )

    comparison = compare_reports(before, after)

    assert comparison.missing_metrics_case_ids == ("x",)
    assert comparison.policy_change_case_ids == ("x",)
    assert not comparison.clean


def test_identical_reports_are_clean():
    comparison = compare_reports(BASELINE, BASELINE)

    assert comparison.clean
    assert comparison.by_family == ()


def test_a_worse_product_vector_is_not_clean_even_when_valid():
    before = CampaignReport(
        "c",
        "old",
        (_result("x", "f", "VALID", "VALID", {"objective_days": 5, "teacher_gap_minutes": 0}),),
    )
    after = CampaignReport(
        "c",
        "new",
        (_result("x", "f", "VALID", "VALID", {"objective_days": 50, "teacher_gap_minutes": 0}),),
    )

    comparison = compare_reports(before, after)

    assert comparison.quality_regressed_case_ids == ("x",)
    assert comparison.quality_changes["x"]["objective_days"] == (5, 50)
    assert not comparison.clean
    assert comparison.metric_changes["x"]["objective_days"] == 45


def test_an_explicit_family_tolerance_allows_a_declared_degradation():
    before = CampaignReport(
        "c", "old", (_result("x", "f1", "VALID", "VALID", {"objective_days": 5}),)
    )
    after = CampaignReport(
        "c", "new", (_result("x", "f1", "VALID", "VALID", {"objective_days": 50}),)
    )

    strict = compare_reports(before, after)
    tolerated = compare_reports(before, after, tolerances={"f1": {"objective_days": 60}})

    assert strict.quality_regressed_case_ids == ("x",)
    assert tolerated.quality_regressed_case_ids == ()
    assert tolerated.clean


def test_an_improvement_at_a_higher_priority_shields_lower_priorities():
    before = CampaignReport(
        "c",
        "old",
        (_result("x", "f", "VALID", "VALID", {"objective_days": 50, "teacher_gap_minutes": 0}),),
    )
    after = CampaignReport(
        "c",
        "new",
        (_result("x", "f", "VALID", "VALID", {"objective_days": 5, "teacher_gap_minutes": 900}),),
    )

    comparison = compare_reports(before, after)

    assert comparison.quality_regressed_case_ids == ()
    assert comparison.clean


def test_a_lower_margin_regresses_quality():
    before = CampaignReport("c", "old", (_result("x", "f", "VALID", "VALID", {"margin_days": 40}),))
    after = CampaignReport("c", "new", (_result("x", "f", "VALID", "VALID", {"margin_days": 5}),))

    comparison = compare_reports(before, after)

    assert comparison.quality_regressed_case_ids == ("x",)
    assert comparison.quality_changes["x"]["margin_days"] == (40, 5)


def test_report_round_trips_through_json_serializable_mapping():
    assert report_from_dict(report_to_dict(BASELINE)) == BASELINE


def test_scenario_coverage_counts_executed_omitted_and_duplicate_cases():
    coverage = scenario_coverage(CANDIDATE, {"f1": ["A", "B"], "f2": ["C"]})
    families = {row.family: row for row in coverage.families}

    assert families["f1"].executed == 2
    assert families["f1"].omitted_case_ids == ()
    assert families["f2"].executed == 0
    assert families["f2"].omitted_case_ids == ("C",)
    assert coverage.total_expected == 3
    assert coverage.total_executed == 2
    assert not coverage.complete

    duplicated = CampaignReport("c", "commit", (CANDIDATE.results[0], CANDIDATE.results[0]))
    assert scenario_coverage(duplicated, {"f1": ["A"]}).duplicate_case_ids == ("A",)
