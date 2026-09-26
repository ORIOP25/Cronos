"""Factor-matrix declaration and pairwise coverage for combined campaigns.

The semantic matrix is declared in the manifest, separate from the hardware
matrix. A pair of levels is covered when at least one executed case declares
both levels, or explicitly excluded with a reason. Coverage is computed from
the campaign report, so declaring a case does not equal executing it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations, product
from typing import Any


class MatrixFormatError(ValueError):
    """The declared factor matrix is malformed."""


@dataclass(frozen=True)
class MatrixExclusion:
    axis_a: str
    level_a: str
    axis_b: str
    level_b: str
    reason: str

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise MatrixFormatError("An excluded pair needs a written reason.")
        if self.axis_a == self.axis_b:
            raise MatrixFormatError("An exclusion needs two different axes.")

    @property
    def axes(self) -> tuple[str, str]:
        return (
            (self.axis_a, self.axis_b) if self.axis_a < self.axis_b else (self.axis_b, self.axis_a)
        )

    @property
    def levels(self) -> tuple[str, str]:
        if self.axes == (self.axis_a, self.axis_b):
            return (self.level_a, self.level_b)
        return (self.level_b, self.level_a)


@dataclass(frozen=True)
class MatrixCase:
    case_id: str
    levels: Mapping[str, str]


@dataclass(frozen=True)
class Matrix:
    axes: Mapping[str, tuple[str, ...]]
    cases: tuple[MatrixCase, ...]
    exclusions: tuple[MatrixExclusion, ...]


@dataclass(frozen=True)
class PairStatus:
    axes: tuple[str, str]
    levels: tuple[str, str]
    covered_by: tuple[str, ...]
    exclusion: MatrixExclusion | None

    @property
    def covered(self) -> bool:
        return bool(self.covered_by)

    @property
    def justified(self) -> bool:
        return self.covered or self.exclusion is not None


@dataclass(frozen=True)
class MatrixCoverage:
    pairs: tuple[PairStatus, ...]

    @property
    def complete(self) -> bool:
        return all(pair.justified for pair in self.pairs)

    @property
    def covered_pairs(self) -> tuple[PairStatus, ...]:
        return tuple(pair for pair in self.pairs if pair.covered)

    @property
    def excluded_pairs(self) -> tuple[PairStatus, ...]:
        return tuple(pair for pair in self.pairs if not pair.covered and pair.exclusion is not None)

    @property
    def uncovered_pairs(self) -> tuple[PairStatus, ...]:
        return tuple(pair for pair in self.pairs if not pair.justified)

    @property
    def missing_pairs(self) -> tuple[tuple[str, str], ...]:
        return tuple(pair.levels for pair in self.uncovered_pairs)


def parse_matrix(manifest: Mapping[str, Any]) -> Matrix:
    data = manifest.get("matrix")
    if not isinstance(data, Mapping):
        raise MatrixFormatError("The manifest has no matrix section.")
    raw_axes = data.get("axes")
    if not isinstance(raw_axes, Mapping) or not raw_axes:
        raise MatrixFormatError("The matrix needs at least one axis with levels.")
    axes: dict[str, tuple[str, ...]] = {}
    for axis, levels in raw_axes.items():
        if not isinstance(axis, str) or not axis:
            raise MatrixFormatError("Axis names must be non-empty strings.")
        if not isinstance(levels, Sequence) or isinstance(levels, str) or len(levels) < 2:
            raise MatrixFormatError(f"Axis '{axis}' needs at least two levels.")
        values = tuple(str(level) for level in levels)
        if len(set(values)) != len(values):
            raise MatrixFormatError(f"Axis '{axis}' repeats a level.")
        axes[axis] = values
    cases = []
    for row in data.get("cases", ()):
        if not isinstance(row, Mapping) or not row.get("case_id") or not row.get("levels"):
            raise MatrixFormatError("Every matrix case needs an id and its levels.")
        cases.append(MatrixCase(str(row["case_id"]), dict(row["levels"])))
    exclusions = []
    for row in data.get("exclusions", ()):
        try:
            axes_pair = tuple(row["axes"])
            levels_pair = tuple(row["levels"])
            if len(axes_pair) != 2 or len(levels_pair) != 2:
                raise KeyError
            exclusions.append(
                MatrixExclusion(
                    axes_pair[0],
                    levels_pair[0],
                    axes_pair[1],
                    levels_pair[1],
                    str(row["reason"]),
                )
            )
        except (KeyError, TypeError):
            raise MatrixFormatError(
                "An exclusion needs two axes, two levels and a reason."
            ) from None
    return Matrix(axes, tuple(cases), tuple(exclusions))


def validate_matrix(
    manifest: Mapping[str, Any], campaign_case_ids: set[str] | None = None
) -> tuple[str, ...]:
    """Return explicit problems in the declared matrix, empty when coherent."""
    try:
        matrix = parse_matrix(manifest)
    except MatrixFormatError as exc:
        return (str(exc),)
    problems: list[str] = []
    declared_cases = None
    if isinstance(manifest.get("cases"), list):
        declared_cases = {str(row.get("case_id")) for row in manifest["cases"]}
    for case in matrix.cases:
        if declared_cases is not None and case.case_id not in declared_cases:
            problems.append(f"Matrix case '{case.case_id}' is not a campaign case.")
        if campaign_case_ids is not None and case.case_id not in campaign_case_ids:
            problems.append(f"Matrix case '{case.case_id}' is not in the campaign selection.")
        for axis, level in case.levels.items():
            if axis not in matrix.axes:
                problems.append(f"Case '{case.case_id}' uses unknown axis '{axis}'.")
            elif level not in matrix.axes[axis]:
                problems.append(
                    f"Case '{case.case_id}' uses unknown level '{level}' on axis '{axis}'."
                )
    for exclusion in matrix.exclusions:
        for axis, level in zip(exclusion.axes, exclusion.levels, strict=True):
            if axis not in matrix.axes:
                problems.append(f"Exclusion references unknown axis '{axis}'.")
            elif level not in matrix.axes[axis]:
                problems.append(f"Exclusion references unknown level '{level}' on axis '{axis}'.")
    return tuple(problems)


def _pairs(matrix: Matrix) -> list[tuple[str, str, str, str]]:
    rows = []
    for axis_a, axis_b in combinations(sorted(matrix.axes), 2):
        for level_a in matrix.axes[axis_a]:
            for level_b in matrix.axes[axis_b]:
                rows.append((axis_a, level_a, axis_b, level_b))
    return rows


def _exclusion_for(
    exclusions: Sequence[MatrixExclusion], axis_a: str, level_a: str, axis_b: str, level_b: str
) -> MatrixExclusion | None:
    for exclusion in exclusions:
        if exclusion.axes == (axis_a, axis_b) and exclusion.levels == (level_a, level_b):
            return exclusion
    return None


def pairwise_coverage(matrix: Matrix, executed_case_ids: set[str]) -> MatrixCoverage:
    cases = {case.case_id: case for case in matrix.cases if case.case_id in executed_case_ids}
    pairs = []
    for axis_a, level_a, axis_b, level_b in _pairs(matrix):
        covered_by = tuple(
            sorted(
                case.case_id
                for case in cases.values()
                if case.levels.get(axis_a) == level_a and case.levels.get(axis_b) == level_b
            )
        )
        pairs.append(
            PairStatus(
                (axis_a, axis_b),
                (level_a, level_b),
                covered_by,
                _exclusion_for(matrix.exclusions, axis_a, level_a, axis_b, level_b),
            )
        )
    return MatrixCoverage(tuple(pairs))


def coverage_to_dict(coverage: MatrixCoverage) -> dict[str, Any]:
    return {
        "complete": coverage.complete,
        "valid_pairs": len(coverage.pairs),
        "covered_pairs": len(coverage.covered_pairs),
        "excluded_pairs": len(coverage.excluded_pairs),
        "missing_pairs": [
            {"axes": list(pair.axes), "levels": list(pair.levels)}
            for pair in coverage.uncovered_pairs
        ],
        "covered": [
            {
                "axes": list(pair.axes),
                "levels": list(pair.levels),
                "covered_by": list(pair.covered_by),
            }
            for pair in coverage.covered_pairs
        ],
        "exclusions": [
            {
                "axes": list(pair.exclusion.axes),
                "levels": list(pair.exclusion.levels),
                "reason": pair.exclusion.reason,
            }
            for pair in coverage.excluded_pairs
            if pair.exclusion is not None
        ],
    }


def _pair_keys(levels: Mapping[str, str]) -> set[tuple[str, str, str, str]]:
    names = sorted(levels)
    return {
        (axis_a, levels[axis_a], axis_b, levels[axis_b])
        for axis_a, axis_b in combinations(names, 2)
    }


def covering_array(axes: Mapping[str, Sequence[str]]) -> tuple[dict[str, str], ...]:
    """A deterministic greedy pairwise covering array over the declared axes.

    Enumerating the combinations is not executing them; the campaign report is
    the only source of coverage.
    """
    if not axes or any(len(levels) < 2 for levels in axes.values()):
        raise MatrixFormatError("Every axis needs at least two levels.")
    candidates = [dict(zip(axes, values, strict=True)) for values in product(*axes.values())]
    universe: set[tuple[str, str, str, str]] = set()
    for candidate in candidates:
        universe |= _pair_keys(candidate)
    uncovered = universe
    selected: list[dict[str, str]] = []
    while uncovered:
        best = max(candidates, key=lambda candidate: len(_pair_keys(candidate) & uncovered))
        uncovered -= _pair_keys(best)
        selected.append(best)
        candidates.remove(best)
    return tuple(selected)


def campaign_matrix_report(manifest: Mapping[str, Any], report) -> dict[str, Any]:
    """Coverage of the declared matrix by the cases actually present in a report.

    Executed coverage counts every result present; concluded coverage counts
    only cases that pass the fail-closed runner rule. Blocking outcomes
    (errors, omissions and unsettled searches) keep the report incomplete.
    """
    from app.scheduler.lab.campaign import case_passes
    from app.scheduler.lab.manifest import from_manifest

    _campaign_id, cases = from_manifest(manifest)
    by_id = {case.case_id: case for case in cases}
    executed = {result.case_id for result in report.results} & set(by_id)
    outcomes: dict[str, int] = {}
    for result in report.results:
        outcomes[result.outcome.value] = outcomes.get(result.outcome.value, 0) + 1
    blocking = tuple(
        sorted(
            result.case_id
            for result in report.results
            if result.case_id in by_id and not case_passes(by_id[result.case_id], result)
        )
    )
    concluded = executed - set(blocking)
    problems = validate_matrix(manifest, campaign_case_ids=executed)
    try:
        matrix = parse_matrix(manifest)
    except MatrixFormatError as exc:
        return {
            "campaign_id": manifest.get("campaign_id"),
            "complete": False,
            "problems": [str(exc)],
            "executed_cases": sorted(executed),
            "concluded_cases": sorted(concluded),
            "blocking_cases": list(blocking),
            "outcomes": outcomes,
        }
    concluded_coverage = pairwise_coverage(matrix, concluded)
    executed_coverage = pairwise_coverage(matrix, executed)
    data = coverage_to_dict(concluded_coverage)
    data["campaign_id"] = manifest.get("campaign_id")
    data["executed_cases"] = sorted(executed)
    data["concluded_cases"] = sorted(concluded)
    data["blocking_cases"] = list(blocking)
    data["outcomes"] = outcomes
    data["problems"] = list(problems)
    data["executed_covered_pairs"] = len(executed_coverage.covered_pairs)
    data["concluded_covered_pairs"] = len(concluded_coverage.covered_pairs)
    data["complete"] = bool(concluded_coverage.complete and not problems and not blocking)
    return data


def main(argv: Sequence[str] | None = None) -> int:
    import argparse
    import json
    from pathlib import Path

    from app.scheduler.lab.reports import report_from_dict

    parser = argparse.ArgumentParser(description="Coverage report for a lab matrix campaign.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    report = report_from_dict(json.loads(Path(args.report).read_text(encoding="utf-8")))
    data = campaign_matrix_report(manifest, report)
    Path(args.out).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(
        f"[matrix] {data.get('campaign_id')}: complete={data.get('complete')} "
        f"problems={len(data.get('problems', []))}"
    )
    return 0 if data.get("complete") and not data.get("problems") else 1


if __name__ == "__main__":
    raise SystemExit(main())
