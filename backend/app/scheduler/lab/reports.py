"""Campaign report comparison and executed scenario coverage."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

SETTLED_OUTCOMES = frozenset({"VALID", "INFEASIBLE"})

# Ordered by domain priority: completion excess first, then gaps, then
# preferences and room churn. Lower is better unless declared otherwise.
QUALITY_METRICS: Mapping[str, str] = {
    "objective_days": "min",
    "excess_days": "min",
    "classes_after_preferred": "min",
    "margin_days": "max",
    "teacher_gap_minutes": "min",
    "class_gap_minutes": "min",
    "preference_cost_minutes": "min",
    "room_change_cost": "min",
    "disruption_cost": "min",
    "changed_lessons": "min",
}


class CaseOutcome(StrEnum):
    VALID = "VALID"
    INVALID = "INVALID"
    INFEASIBLE = "INFEASIBLE"
    INCONCLUSIVE = "INCONCLUSIVE"
    ERROR = "ERROR"
    OMITTED = "OMITTED"


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    family: str
    version: int
    outcome: CaseOutcome
    input_digest: str
    metrics: Mapping[str, int] = field(default_factory=dict)
    violations: tuple[str, ...] = ()
    error: str = ""
    expected_outcome: CaseOutcome | None = None
    policy_version: str = ""
    payload: Mapping[str, Any] = field(default_factory=dict)

    @property
    def settled(self) -> bool:
        return self.outcome.value in SETTLED_OUTCOMES

    @property
    def passed(self) -> bool | None:
        if self.expected_outcome is None:
            return None
        return self.outcome is self.expected_outcome


@dataclass(frozen=True)
class CampaignReport:
    campaign_id: str
    commit: str
    results: tuple[CaseResult, ...]
    code_identity: str = ""
    schema_version: str = ""


@dataclass(frozen=True)
class FamilyRegression:
    family: str
    regressed_case_ids: tuple[str, ...]
    omitted_case_ids: tuple[str, ...]
    inconclusive_case_ids: tuple[str, ...]
    incomparable_case_ids: tuple[str, ...]
    quality_regressed_case_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReportComparison:
    omitted_case_ids: tuple[str, ...]
    added_case_ids: tuple[str, ...]
    regressed_case_ids: tuple[str, ...]
    inconclusive_case_ids: tuple[str, ...]
    incomparable_case_ids: tuple[str, ...]
    missing_metrics_case_ids: tuple[str, ...]
    policy_change_case_ids: tuple[str, ...]
    by_family: tuple[FamilyRegression, ...]
    metric_changes: Mapping[str, Mapping[str, int]]
    quality_regressed_case_ids: tuple[str, ...] = ()
    quality_changes: Mapping[str, Mapping[str, tuple[int, int]]] = field(default_factory=dict)

    @property
    def clean(self) -> bool:
        return not (
            self.omitted_case_ids
            or self.regressed_case_ids
            or self.inconclusive_case_ids
            or self.incomparable_case_ids
            or self.missing_metrics_case_ids
            or self.policy_change_case_ids
            or self.quality_regressed_case_ids
        )


def case_result_to_dict(result: CaseResult) -> dict[str, Any]:
    return {
        "case_id": result.case_id,
        "family": result.family,
        "version": result.version,
        "outcome": result.outcome.value,
        "input_digest": result.input_digest,
        "metrics": dict(result.metrics),
        "violations": list(result.violations),
        "error": result.error,
        "expected_outcome": None
        if result.expected_outcome is None
        else result.expected_outcome.value,
        "policy_version": result.policy_version,
        "payload": dict(result.payload),
    }


def case_result_from_dict(data: Mapping[str, Any]) -> CaseResult:
    expected = data.get("expected_outcome")
    return CaseResult(
        case_id=data["case_id"],
        family=data["family"],
        version=data["version"],
        outcome=CaseOutcome(data["outcome"]),
        input_digest=data["input_digest"],
        metrics=dict(data.get("metrics", {})),
        violations=tuple(data.get("violations", ())),
        error=data.get("error", ""),
        expected_outcome=None if expected is None else CaseOutcome(expected),
        policy_version=data.get("policy_version", ""),
        payload=dict(data.get("payload", {})),
    )


def duplicate_input_digests(report: CampaignReport) -> dict[str, list[str]]:
    """Cases that re-executed an identical mathematical input."""
    groups: dict[str, list[str]] = defaultdict(list)
    for result in report.results:
        groups[result.input_digest].append(result.case_id)
    return {
        digest: sorted(case_ids) for digest, case_ids in sorted(groups.items()) if len(case_ids) > 1
    }


def report_to_dict(report: CampaignReport) -> dict[str, Any]:
    return {
        "campaign_id": report.campaign_id,
        "commit": report.commit,
        "code_identity": report.code_identity,
        "schema_version": report.schema_version,
        "duplicate_input_digests": duplicate_input_digests(report),
        "results": [case_result_to_dict(result) for result in report.results],
    }


def report_from_dict(data: Mapping[str, Any]) -> CampaignReport:
    return CampaignReport(
        campaign_id=data["campaign_id"],
        commit=data["commit"],
        results=tuple(case_result_from_dict(row) for row in data["results"]),
        code_identity=data.get("code_identity", ""),
        schema_version=data.get("schema_version", ""),
    )


def _regressed(baseline: CaseResult, candidate: CaseResult) -> bool:
    if candidate.passed is not None or baseline.passed is not None:
        return candidate.passed is False and baseline.passed is not False
    return baseline.settled and not candidate.settled


def _quality_regression(
    before: CaseResult, after: CaseResult, allowances: Mapping[str, float]
) -> str | None:
    """First metric where the candidate is worse than the baseline.

    Lexicographic by domain priority: an improvement at a higher priority
    shields lower priorities, matching the product vector.
    """
    for metric, direction in QUALITY_METRICS.items():
        if metric not in before.metrics or metric not in after.metrics:
            continue
        old, new = int(before.metrics[metric]), int(after.metrics[metric])
        allowance = float(allowances.get(metric, 0.0))
        if direction == "min":
            if new > old + allowance:
                return metric
            if new < old:
                return None
        else:
            if new < old - allowance:
                return metric
            if new > old:
                return None
    return None


def compare_reports(
    baseline: CampaignReport,
    candidate: CampaignReport,
    *,
    tolerances: Mapping[str, Mapping[str, float]] | None = None,
) -> ReportComparison:
    """Compare two campaign reports by family, provenance, pass state and quality.

    ``tolerances`` declares per-family allowances on the ordered quality
    metrics; without an entry the default is zero, so any degradation blocks.
    """
    before = {result.case_id: result for result in baseline.results}
    after = {result.case_id: result for result in candidate.results}
    omitted = tuple(sorted(set(before) - set(after)))
    added = tuple(sorted(set(after) - set(before)))
    declared = tolerances or {}

    regressed: list[str] = []
    incomparable: list[str] = []
    missing_metrics: list[str] = []
    policy_changes: list[str] = []
    quality_regressed: list[str] = []
    metric_changes: dict[str, dict[str, int]] = {}
    quality_changes: dict[str, dict[str, tuple[int, int]]] = {}
    for case_id in sorted(set(before) & set(after)):
        old, new = before[case_id], after[case_id]
        if old.version != new.version or old.input_digest != new.input_digest:
            incomparable.append(case_id)
        if _regressed(old, new):
            regressed.append(case_id)
        missing = sorted(set(old.metrics) - set(new.metrics))
        if missing:
            missing_metrics.append(case_id)
        if old.policy_version != new.policy_version:
            policy_changes.append(case_id)
        changes = {
            key: new.metrics[key] - old.metrics[key]
            for key in old.metrics
            if key in new.metrics and new.metrics[key] != old.metrics[key]
        }
        if changes:
            metric_changes[case_id] = changes
        allowances = declared.get(new.family, {})
        worse = _quality_regression(old, new, allowances)
        if worse is not None:
            quality_regressed.append(case_id)
            quality_changes[case_id] = {worse: (int(old.metrics[worse]), int(new.metrics[worse]))}
    inconclusive = sorted(
        case_id
        for case_id, result in after.items()
        if result.outcome in (CaseOutcome.INCONCLUSIVE, CaseOutcome.ERROR)
    )

    by_family: dict[str, dict[str, list[str]]] = defaultdict(
        lambda: {
            "regressed": [],
            "omitted": [],
            "inconclusive": [],
            "incomparable": [],
            "quality": [],
        }
    )
    for case_id in regressed:
        by_family[after[case_id].family]["regressed"].append(case_id)
    for case_id in omitted:
        by_family[before[case_id].family]["omitted"].append(case_id)
    for case_id in inconclusive:
        by_family[after[case_id].family]["inconclusive"].append(case_id)
    for case_id in incomparable:
        by_family[after[case_id].family]["incomparable"].append(case_id)
    for case_id in quality_regressed:
        by_family[after[case_id].family]["quality"].append(case_id)

    return ReportComparison(
        omitted_case_ids=omitted,
        added_case_ids=added,
        regressed_case_ids=tuple(regressed),
        inconclusive_case_ids=tuple(inconclusive),
        incomparable_case_ids=tuple(incomparable),
        missing_metrics_case_ids=tuple(missing_metrics),
        policy_change_case_ids=tuple(policy_changes),
        by_family=tuple(
            FamilyRegression(
                family,
                tuple(sorted(rows["regressed"])),
                tuple(sorted(rows["omitted"])),
                tuple(sorted(rows["inconclusive"])),
                tuple(sorted(rows["incomparable"])),
                tuple(sorted(rows["quality"])),
            )
            for family, rows in sorted(by_family.items())
        ),
        metric_changes=metric_changes,
        quality_regressed_case_ids=tuple(quality_regressed),
        quality_changes=quality_changes,
    )


@dataclass(frozen=True)
class FamilyCoverage:
    family: str
    expected: int
    executed: int
    omitted_case_ids: tuple[str, ...]


@dataclass(frozen=True)
class ScenarioCoverage:
    families: tuple[FamilyCoverage, ...]
    total_expected: int
    total_executed: int
    duplicate_case_ids: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return self.total_expected == self.total_executed and not self.duplicate_case_ids


def scenario_coverage(
    report: CampaignReport,
    expected_case_ids_by_family: Mapping[str, Sequence[str]],
) -> ScenarioCoverage:
    """Measure executed scenario coverage per family against a declared manifest."""
    identifiers = [result.case_id for result in report.results]
    duplicates = sorted({case_id for case_id in identifiers if identifiers.count(case_id) > 1})
    executed: dict[str, set[str]] = defaultdict(set)
    for result in report.results:
        executed[result.family].add(result.case_id)
    families = []
    total_expected = 0
    total_executed = 0
    for family, expected_ids in sorted(expected_case_ids_by_family.items()):
        expected = set(expected_ids)
        covered = executed.get(family, set()) & expected
        omitted = tuple(sorted(expected - covered))
        families.append(FamilyCoverage(family, len(expected), len(covered), omitted))
        total_expected += len(expected)
        total_executed += len(covered)
    return ScenarioCoverage(tuple(families), total_expected, total_executed, tuple(duplicates))
