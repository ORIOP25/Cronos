import pytest

from app.scheduler.lab.fixtures import CaseExpectation
from app.scheduler.lab.matrix import (
    MatrixExclusion,
    MatrixFormatError,
    campaign_matrix_report,
    coverage_to_dict,
    covering_array,
    pairwise_coverage,
    parse_matrix,
    validate_matrix,
)
from tests.unit.test_scheduler_lab_campaign import FEASIBLE_SPEC


def _manifest(**overrides):
    matrix = {
        "axes": {"scale": ["10", "30"], "space": ["ample", "tight"]},
        "cases": [
            {"case_id": "c-small-ample", "levels": {"scale": "10", "space": "ample"}},
            {"case_id": "c-small-tight", "levels": {"scale": "10", "space": "tight"}},
            {"case_id": "c-big-ample", "levels": {"scale": "30", "space": "ample"}},
        ],
        "exclusions": [],
    }
    matrix.update(overrides)
    return {"schema_version": "scheduler-lab-v3", "campaign_id": "x", "cases": [], "matrix": matrix}


def test_every_valid_pair_is_covered_or_excluded():
    manifest = _manifest(
        exclusions=[
            {
                "axes": ["scale", "space"],
                "levels": ["30", "tight"],
                "reason": "30 classes cannot fit a tight topology by construction.",
            }
        ]
    )
    matrix = parse_matrix(manifest)

    coverage = pairwise_coverage(matrix, {"c-small-ample", "c-small-tight", "c-big-ample"})

    assert coverage.complete
    assert coverage.missing_pairs == ()
    excluded = [pair for pair in coverage.pairs if pair.exclusion is not None]
    assert len(excluded) == 1
    assert excluded[0].levels == ("30", "tight")

    # An excluded pair may also be executed; it still counts as justified.
    coverage = pairwise_coverage(
        matrix, {"c-small-ample", "c-small-tight", "c-big-ample", "c-big-tight"}
    )
    assert coverage.complete


def test_a_missing_pair_keeps_coverage_incomplete():
    matrix = parse_matrix(_manifest())

    coverage = pairwise_coverage(matrix, {"c-small-ample", "c-small-tight", "c-big-ample"})

    assert not coverage.complete
    assert coverage.missing_pairs == (("30", "tight"),)


def test_coverage_names_the_cases_that_cover_each_pair():
    matrix = parse_matrix(_manifest())

    coverage = pairwise_coverage(matrix, {"c-small-ample", "c-small-tight", "c-big-ample"})

    by_levels = {pair.levels: pair for pair in coverage.pairs}
    assert by_levels[("10", "ample")].covered_by == ("c-small-ample",)
    assert by_levels[("30", "ample")].covered_by == ("c-big-ample",)
    assert by_levels[("30", "tight")].covered_by == ()
    assert by_levels[("10", "tight")].covered_by == ("c-small-tight",)


def test_unexecuted_or_unknown_cases_do_not_cover_pairs():
    matrix = parse_matrix(_manifest())

    coverage = pairwise_coverage(matrix, {"c-small-ample", "unknown-case"})

    assert not coverage.complete
    assert ("30", "tight") in [pair.levels for pair in coverage.uncovered_pairs]


def test_coverage_is_computed_across_every_axis_pair():
    manifest = _manifest(
        axes={"scale": ["10", "30"], "space": ["ample", "tight"], "rooms": ["ample", "scarce"]},
        cases=[
            {"case_id": "a", "levels": {"scale": "10", "space": "ample", "rooms": "ample"}},
            {"case_id": "b", "levels": {"scale": "10", "space": "tight", "rooms": "scarce"}},
            {"case_id": "c", "levels": {"scale": "30", "space": "ample", "rooms": "scarce"}},
            {"case_id": "d", "levels": {"scale": "30", "space": "tight", "rooms": "ample"}},
        ],
        exclusions=[],
    )
    matrix = parse_matrix(manifest)

    coverage = pairwise_coverage(matrix, {"a", "b", "c", "d"})

    assert {pair.axes for pair in coverage.pairs} == {
        ("rooms", "scale"),
        ("rooms", "space"),
        ("scale", "space"),
    }
    assert coverage.complete


def test_validate_matrix_flags_unknown_axes_levels_and_cases():
    manifest = _manifest(
        cases=[
            {"case_id": "c-small-ample", "levels": {"scale": "10", "space": "ample"}},
            {"case_id": "c-unknown", "levels": {"scale": "99", "space": "ample", "ghost": "x"}},
        ],
        exclusions=[
            {
                "axes": ["scale", "ghost"],
                "levels": ["30", "y"],
                "reason": "unknown axis",
            }
        ],
    )

    problems = validate_matrix(manifest, campaign_case_ids={"c-small-ample"})

    assert any("c-unknown" in problem for problem in problems)
    assert any("ghost" in problem for problem in problems)
    assert not problems == ()


def test_parse_matrix_rejects_unknown_shape():
    with pytest.raises(MatrixFormatError):
        parse_matrix({"cases": []})
    with pytest.raises(MatrixFormatError):
        parse_matrix(_manifest(axes={}))
    with pytest.raises(MatrixFormatError):
        parse_matrix(_manifest(exclusions=[{"axes": ["scale"], "levels": ["10"], "reason": "x"}]))


def test_coverage_dict_serializes_pairs_for_reports():
    matrix = parse_matrix(
        _manifest(
            exclusions=[
                {
                    "axes": ["scale", "space"],
                    "levels": ["30", "tight"],
                    "reason": "declared impossible",
                }
            ]
        )
    )
    coverage = pairwise_coverage(matrix, {"c-small-ample", "c-small-tight", "c-big-ample"})

    data = coverage_to_dict(coverage)

    assert data["complete"] is True
    assert data["valid_pairs"] == 4
    assert data["covered_pairs"] == 3
    assert data["excluded_pairs"] == 1
    assert data["missing_pairs"] == []
    assert data["exclusions"][0] == {
        "axes": ["scale", "space"],
        "levels": ["30", "tight"],
        "reason": "declared impossible",
    }


def test_exclusion_requires_a_reason():
    with pytest.raises(MatrixFormatError):
        MatrixExclusion("scale", "10", "space", "tight", "  ")


def test_covering_array_covers_every_pair_with_few_cases():
    axes = {"a": ("1", "2", "3"), "b": ("x", "y"), "c": ("p", "q"), "d": ("m", "n")}

    combinations = covering_array(axes)

    assert len(combinations) <= 12
    for row in combinations:
        assert set(row) == set(axes)
    seen = set()
    for row in combinations:
        axis_names = sorted(axes)
        for index, axis_a in enumerate(axis_names):
            for axis_b in axis_names[index + 1 :]:
                seen.add((axis_a, row[axis_a], axis_b, row[axis_b]))
    expected = {
        (axis_a, level_a, axis_b, level_b)
        for index, axis_a in enumerate(sorted(axes))
        for axis_b in sorted(axes)[index + 1 :]
        for level_a in axes[axis_a]
        for level_b in axes[axis_b]
    }
    assert seen == expected


def test_covering_array_rejects_a_single_level_axis():
    with pytest.raises(MatrixFormatError):
        covering_array({"a": ("only",), "b": ("x", "y")})


def test_matrix_coverage_separates_executed_from_concluded_cases():
    from app.scheduler.lab.manifest import CaseSeeds, LabCase, to_manifest
    from app.scheduler.lab.reports import CampaignReport, CaseOutcome, CaseResult

    manifest = _manifest()
    manifest["cases"] = to_manifest(
        "x",
        (
            LabCase(
                "c-small-ample",
                "minimal",
                1,
                CaseExpectation.EXPLORATORY_UNKNOWN,
                FEASIBLE_SPEC,
                CaseSeeds(1, 1, 1),
            ),
            LabCase(
                "c-small-tight",
                "minimal",
                1,
                CaseExpectation.EXPLORATORY_UNKNOWN,
                FEASIBLE_SPEC,
                CaseSeeds(1, 1, 1),
            ),
        ),
    )["cases"]
    report = CampaignReport(
        "x",
        "commit",
        (
            CaseResult("c-small-ample", "minimal", 1, CaseOutcome.VALID, "d"),
            CaseResult("c-small-tight", "minimal", 1, CaseOutcome.ERROR, "d", error="boom"),
        ),
    )

    data = campaign_matrix_report(manifest, report)

    assert data["complete"] is False
    assert data["blocking_cases"] == ["c-small-tight"]
    assert data["concluded_cases"] == ["c-small-ample"]
    assert data["executed_cases"] == ["c-small-ample", "c-small-tight"]
    assert data["outcomes"]["ERROR"] == 1
    assert {tuple(pair["levels"]) for pair in data["missing_pairs"]} == {
        ("10", "tight"),
        ("30", "ample"),
        ("30", "tight"),
    }
    assert data["executed_covered_pairs"] == 2
    assert data["concluded_covered_pairs"] == 1


def test_a_settled_campaign_with_every_declared_case_concludes_completely():
    from app.scheduler.lab.manifest import CaseSeeds, LabCase, to_manifest
    from app.scheduler.lab.reports import CampaignReport, CaseOutcome, CaseResult

    manifest = _manifest(
        exclusions=[
            {
                "axes": ["scale", "space"],
                "levels": ["30", "tight"],
                "reason": "declared impossible",
            }
        ]
    )
    ids = ("c-small-ample", "c-small-tight", "c-big-ample")
    manifest["cases"] = to_manifest(
        "x",
        tuple(
            LabCase(
                case_id,
                "minimal",
                1,
                CaseExpectation.EXPLORATORY_UNKNOWN,
                FEASIBLE_SPEC,
                CaseSeeds(1, 1, 1),
            )
            for case_id in ids
        ),
    )["cases"]
    report = CampaignReport(
        "x",
        "commit",
        tuple(CaseResult(case_id, "minimal", 1, CaseOutcome.VALID, "d") for case_id in ids),
    )

    data = campaign_matrix_report(manifest, report)

    assert data["complete"] is True
    assert data["blocking_cases"] == []
    assert data["covered_pairs"] == 3
    assert data["excluded_pairs"] == 1
    assert len(data["executed_cases"]) == 3
