"""Coordinate an AdaptiveRecovery over a snapshot with a published baseline.

The application owns the safety budget and the diagnosis. The concrete search
belongs to the composition root. A complete candidate is always revalidated by
the independent validator and its adaptive metrics are recalculated outside the
solver. An interrupted search never becomes an impossibility claim, and a
baseline invalidated by new data is reported instead of being kept.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from time import monotonic

from app.scheduler.application.contracts import (
    AdaptiveSearch,
    RepairSummary,
)
from app.scheduler.domain.calendar import Period
from app.scheduler.domain.candidate import (
    CandidateSchedule,
    PlanningSnapshot,
    SchedulingStrategy,
)
from app.scheduler.domain.candidate_validation import ValidationReport, validate_candidate
from app.scheduler.domain.capacity import aggregate_capacity_check, residual_minutes
from app.scheduler.domain.diagnostics import (
    Diagnosis,
    diagnose_baseline_stale,
    diagnose_capacity,
    diagnose_failure,
    diagnose_inconclusive,
    diagnose_invalid_input,
    diagnose_scope_proof,
)
from app.scheduler.domain.quality import SearchEvidence
from app.scheduler.domain.recovery import (
    BaselineAssessment,
    RecoveryPolicy,
    RecoveryQualityMetrics,
    assess_baseline,
    measure_recovery_quality,
)
from app.scheduler.domain.results import (
    OUTCOME_CANCELLED,
    OUTCOME_COMPLETE,
    OUTCOME_FAILED,
    OUTCOME_INCONCLUSIVE,
    OUTCOME_INFEASIBLE,
    OUTCOME_INVALID_INPUT,
    SearchOutcome,
)
from app.scheduler.domain.stop import (
    BudgetPhase,
    ExecutionBudget,
    ExplorationPolicy,
)


@dataclass(frozen=True)
class RepairResult:
    outcome: str
    candidate: CandidateSchedule | None
    report: ValidationReport | None = None
    message: str = ""
    quality: RecoveryQualityMetrics | None = None
    evidence: SearchEvidence | None = None
    baseline: BaselineAssessment | None = None
    summary: RepairSummary | None = None
    diagnoses: tuple[Diagnosis, ...] = ()
    budget: ExecutionBudget | None = None
    wall_time_seconds: float = 0.0
    search_seconds: float = 0.0
    statistics: Mapping[str, int] = field(default_factory=dict)

    @property
    def within_budget(self) -> bool:
        return self.budget is None or self.budget.within_budget


def _summary(snapshot: PlanningSnapshot, quality: RecoveryQualityMetrics) -> RepairSummary:
    completion_dates = dict(quality.initial.completion_dates)
    latest = max(completion_dates.values())
    return RepairSummary(
        completion_dates=completion_dates,
        latest_completion_date=latest,
        preferred_end_date=snapshot.preferred_end_date,
        hard_end_date=snapshot.hard_end_date,
        classes_after_preferred=tuple(
            class_id
            for class_id, day in completion_dates.items()
            if day > snapshot.preferred_end_date
        ),
        excess_days=max(0, (latest - snapshot.preferred_end_date).days),
        disruption_cost=quality.disruption.total_cost,
        changed_lessons=len(quality.disruption.changes),
    )


def repair_schedule(
    snapshot: PlanningSnapshot,
    periods: tuple[Period, ...],
    baseline: CandidateSchedule,
    *,
    search: AdaptiveSearch,
    policy: RecoveryPolicy,
    prior_changes: frozenset[int] = frozenset(),
    exploration: ExplorationPolicy | None = None,
    should_cancel: Callable[[], bool] | None = None,
    trajectory_out: list | None = None,
    time_limit_seconds: float = 10.0,
    num_workers: int = 1,
    random_seed: int = 1,
    stop_at_first_complete: bool = False,
) -> RepairResult:
    """Produce a complete, independently validated repair or an honest outcome."""
    if type(snapshot) is not PlanningSnapshot:
        raise ValueError("Repair needs a planning snapshot.")
    if snapshot.strategy is not SchedulingStrategy.ADAPTIVE_RECOVERY:
        raise ValueError("Repair needs an ADAPTIVE_RECOVERY snapshot.")
    if type(baseline) is not CandidateSchedule:
        raise ValueError("Repair needs the published baseline candidate.")
    if type(policy) is not RecoveryPolicy:
        raise ValueError("Repair needs an explicit recovery policy.")
    started = monotonic()
    mark = started
    budget = ExecutionBudget(limit_seconds=time_limit_seconds)

    def charge(phase: BudgetPhase) -> None:
        nonlocal mark
        now = monotonic()
        budget.charge(phase, now - mark)
        mark = now

    baseline_assessment = assess_baseline(snapshot, baseline.lessons)
    for assignment in snapshot.assignments:
        if residual_minutes(snapshot, assignment.assignment_id) < 0:
            charge(BudgetPhase.CONSTRUCTION)
            return RepairResult(
                OUTCOME_INVALID_INPUT,
                None,
                message="Executed or protected credit exceeds an assignment requirement.",
                baseline=baseline_assessment,
                diagnoses=(diagnose_invalid_input("Recorded progress exceeds the demand."),),
                budget=budget,
                wall_time_seconds=monotonic() - started,
            )
    capacity = aggregate_capacity_check(snapshot, periods)
    charge(BudgetPhase.CONSTRUCTION)
    if capacity.proven_infeasible:
        return RepairResult(
            OUTCOME_INFEASIBLE,
            None,
            message="A repair cannot cover the demand with the current capacity.",
            baseline=baseline_assessment,
            diagnoses=diagnose_capacity(snapshot, capacity),
            budget=budget,
            wall_time_seconds=monotonic() - started,
        )
    if budget.remaining_seconds <= 0:
        budget.omit("SEARCH")
        return RepairResult(
            OUTCOME_INCONCLUSIVE,
            None,
            message="The time limit was consumed before the search.",
            baseline=baseline_assessment,
            diagnoses=(diagnose_inconclusive("The time limit was consumed before the search."),),
            budget=budget,
            wall_time_seconds=monotonic() - started,
        )
    outcome: SearchOutcome = search(
        snapshot,
        periods,
        baseline,
        policy,
        prior_changes=prior_changes,
        time_limit_seconds=budget.remaining_seconds,
        num_workers=num_workers,
        random_seed=random_seed,
        exploration=exploration,
        should_cancel=should_cancel,
        trajectory_out=trajectory_out,
        **({"stop_at_first_complete": True} if stop_at_first_complete else {}),
    )
    charge(BudgetPhase.SEARCH)
    search_seconds = outcome.wall_time_seconds
    if should_cancel is not None and should_cancel():
        return RepairResult(
            OUTCOME_CANCELLED,
            None,
            message="The request was cancelled before finalization.",
            baseline=baseline_assessment,
            evidence=outcome.evidence,
            budget=budget,
            wall_time_seconds=monotonic() - started,
            search_seconds=search_seconds,
            statistics=dict(outcome.statistics),
        )
    if outcome.status == OUTCOME_CANCELLED:
        return RepairResult(
            OUTCOME_CANCELLED,
            None,
            message=outcome.message or "The request was cancelled.",
            baseline=baseline_assessment,
            evidence=outcome.evidence,
            budget=budget,
            wall_time_seconds=monotonic() - started,
            search_seconds=search_seconds,
            statistics=dict(outcome.statistics),
        )
    if outcome.status == OUTCOME_COMPLETE and outcome.candidate is not None:
        report = validate_candidate(snapshot, outcome.candidate)
        if not report.valid:
            return RepairResult(
                OUTCOME_FAILED,
                None,
                report=report,
                message="The solver produced a candidate rejected by the validator.",
                baseline=baseline_assessment,
                evidence=outcome.evidence,
                diagnoses=(diagnose_failure("The repair candidate failed validation."),),
                budget=budget,
                wall_time_seconds=monotonic() - started,
                search_seconds=search_seconds,
                statistics=dict(outcome.statistics),
            )
        quality = measure_recovery_quality(
            snapshot,
            baseline,
            outcome.candidate,
            policy,
            prior_changes=prior_changes,
        )
        summary = _summary(snapshot, quality)
        charge(BudgetPhase.FINALIZATION)
        if should_cancel is not None and should_cancel():
            return RepairResult(
                OUTCOME_CANCELLED,
                None,
                message="The request was cancelled during finalization.",
                baseline=baseline_assessment,
                evidence=outcome.evidence,
                budget=budget,
                wall_time_seconds=monotonic() - started,
                search_seconds=search_seconds,
                statistics=dict(outcome.statistics),
            )
        message = outcome.message
        diagnoses: tuple[Diagnosis, ...] = ()
        if not budget.within_budget:
            budget.omit("CERTIFICATION")
            message = (
                f"The search returned a complete candidate, but the execution exceeded "
                f"its {budget.limit_seconds:.1f}s safety budget. {message}"
            )
        if baseline_assessment.requires_repair:
            diagnoses = (
                diagnose_baseline_stale(
                    baseline_assessment.missing_minutes, baseline_assessment.excess_minutes
                ),
            )
        return RepairResult(
            OUTCOME_COMPLETE,
            outcome.candidate,
            report=report,
            message=message,
            quality=quality,
            evidence=outcome.evidence,
            baseline=baseline_assessment,
            summary=summary,
            diagnoses=diagnoses,
            budget=budget,
            wall_time_seconds=monotonic() - started,
            search_seconds=search_seconds,
            statistics=dict(outcome.statistics),
        )
    if outcome.status == OUTCOME_INFEASIBLE:
        diagnoses = diagnose_capacity(snapshot, capacity)
        if not diagnoses:
            diagnoses = (diagnose_scope_proof(outcome.message),)
        return RepairResult(
            OUTCOME_INFEASIBLE,
            None,
            message=outcome.message,
            baseline=baseline_assessment,
            evidence=outcome.evidence,
            diagnoses=diagnoses,
            budget=budget,
            wall_time_seconds=monotonic() - started,
            search_seconds=search_seconds,
            statistics=dict(outcome.statistics),
        )
    if outcome.status == OUTCOME_FAILED:
        diagnoses = (diagnose_failure(outcome.message or "The repair failed."),)
        message = outcome.message or "The repair failed."
    else:
        diagnoses = (diagnose_inconclusive(outcome.message or "The search stopped."),)
        message = outcome.message
    return RepairResult(
        outcome.status,
        None,
        message=message,
        baseline=baseline_assessment,
        evidence=outcome.evidence,
        diagnoses=diagnoses,
        budget=budget,
        wall_time_seconds=monotonic() - started,
        search_seconds=search_seconds,
        statistics=dict(outcome.statistics),
    )
