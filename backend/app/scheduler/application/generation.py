"""Coordinate an authorized CompleteGeneration over a snapshot.

The application depends only on the domain and on the injected search
operation; the concrete CP-SAT search belongs to the composition root.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from time import monotonic

from app.scheduler.application.contracts import (
    DEMONSTRATED,
    IMPOSSIBLE_PROVEN,
    INCONCLUSIVE,
    NOT_ASSESSED,
    CompletionReport,
    RecoveryAssessment,
    ScheduleSearch,
)
from app.scheduler.domain.calendar import Period
from app.scheduler.domain.candidate import (
    CandidateSchedule,
    PlanningSnapshot,
    Unavailability,
    UnavailableResource,
)
from app.scheduler.domain.candidate_validation import ValidationReport, validate_candidate
from app.scheduler.domain.capacity import aggregate_capacity_check, residual_minutes
from app.scheduler.domain.quality import (
    InitialQualityMetrics,
    SearchEvidence,
    measure_initial_quality,
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

RECOVERY_SCENARIO = "CANCEL_LATEST_PLANNED_LESSON"


@dataclass(frozen=True)
class GenerationResult:
    outcome: str
    candidate: CandidateSchedule | None
    report: ValidationReport | None = None
    message: str = ""
    objective_days: int | None = None
    wall_time_seconds: float = 0.0
    search_seconds: float = 0.0
    quality: InitialQualityMetrics | None = None
    evidence: SearchEvidence | None = None
    completion: CompletionReport | None = None
    statistics: Mapping[str, int] = field(default_factory=dict)


def _completion_report(
    snapshot: PlanningSnapshot,
    quality: InitialQualityMetrics,
    recovery: RecoveryAssessment,
) -> CompletionReport:
    completion_dates = dict(quality.completion_dates)
    latest = max(completion_dates.values())
    return CompletionReport(
        completion_dates=completion_dates,
        latest_completion_date=latest,
        preferred_end_date=snapshot.preferred_end_date,
        margin_days=(snapshot.preferred_end_date - latest).days,
        classes_after_preferred=tuple(
            sorted(
                class_id
                for class_id, day in completion_dates.items()
                if day > snapshot.preferred_end_date
            )
        ),
        recovery=recovery,
    )


def recovery_assessment(
    snapshot: PlanningSnapshot,
    periods: tuple[Period, ...],
    candidate: CandidateSchedule,
    *,
    search: ScheduleSearch,
    time_limit_seconds: float = 10.0,
    num_workers: int = 1,
    random_seed: int = 1,
) -> RecoveryAssessment:
    """Remove the latest planned lesson and test recomposition for that scenario."""
    protected_ids = {lesson.lesson_id for lesson in snapshot.protected_lessons}
    planned = [lesson for lesson in candidate.lessons if lesson.lesson_id not in protected_ids]
    if not planned:
        return RecoveryAssessment(RECOVERY_SCENARIO, NOT_ASSESSED, "No planned lesson exists.")
    target = max(planned, key=lambda lesson: lesson.period.start_utc)
    assignment = snapshot.assignment_for(target.assignment_id)
    if assignment is None:
        return RecoveryAssessment(RECOVERY_SCENARIO, NOT_ASSESSED, "Unknown assignment.")
    perturbed = replace(
        snapshot,
        unavailable=(
            *snapshot.unavailable,
            Unavailability(UnavailableResource.CLASS, assignment.class_id, target.period),
            Unavailability(UnavailableResource.TEACHER, assignment.teacher_id, target.period),
        ),
    )
    outcome = search(
        perturbed,
        periods,
        time_limit_seconds=time_limit_seconds,
        num_workers=num_workers,
        random_seed=random_seed,
    )
    if outcome.status == OUTCOME_COMPLETE:
        return RecoveryAssessment(
            RECOVERY_SCENARIO,
            DEMONSTRATED,
            "A complete schedule exists after cancelling that lesson.",
        )
    if outcome.status == OUTCOME_INFEASIBLE:
        return RecoveryAssessment(
            RECOVERY_SCENARIO,
            IMPOSSIBLE_PROVEN,
            "No complete schedule exists after cancelling that lesson.",
        )
    return RecoveryAssessment(RECOVERY_SCENARIO, INCONCLUSIVE, outcome.message)


def generate_complete(
    snapshot: PlanningSnapshot,
    periods: tuple[Period, ...],
    *,
    search: ScheduleSearch,
    assess_recovery: bool = False,
    should_cancel: Callable[[], bool] | None = None,
    recovery_time_limit_seconds: float | None = None,
    time_limit_seconds: float = 10.0,
    num_workers: int = 1,
    random_seed: int = 1,
) -> GenerationResult:
    """Produce a complete, independently validated schedule or an honest outcome."""
    if type(snapshot) is not PlanningSnapshot:
        raise ValueError("Generation needs a planning snapshot.")
    started = monotonic()
    for assignment in snapshot.assignments:
        if residual_minutes(snapshot, assignment.assignment_id) < 0:
            return GenerationResult(
                OUTCOME_INVALID_INPUT,
                None,
                message="Executed or protected credit exceeds an assignment requirement.",
            )
    capacity = aggregate_capacity_check(snapshot, periods)
    if capacity.proven_infeasible:
        details = ", ".join(
            f"assignment {assignment_id}: {minutes} minute(s)"
            for assignment_id, minutes in sorted(capacity.deficits.items())
        )
        return GenerationResult(
            OUTCOME_INFEASIBLE,
            None,
            message=f"Proven minimum deficit: {details}.",
        )
    remaining_seconds = time_limit_seconds - (monotonic() - started)
    if remaining_seconds <= 0:
        return GenerationResult(
            OUTCOME_INCONCLUSIVE,
            None,
            message="The time limit was consumed before the search.",
            wall_time_seconds=monotonic() - started,
        )
    outcome: SearchOutcome = search(
        snapshot,
        periods,
        time_limit_seconds=remaining_seconds,
        num_workers=num_workers,
        random_seed=random_seed,
        should_cancel=should_cancel,
    )
    search_seconds = outcome.wall_time_seconds
    if should_cancel is not None and should_cancel():
        return GenerationResult(
            OUTCOME_CANCELLED,
            None,
            message="The request was cancelled before finalization.",
            wall_time_seconds=monotonic() - started,
            search_seconds=search_seconds,
            evidence=outcome.evidence,
            statistics=dict(outcome.statistics),
        )
    if outcome.status == OUTCOME_CANCELLED:
        return GenerationResult(
            OUTCOME_CANCELLED,
            None,
            message=outcome.message or "The request was cancelled.",
            wall_time_seconds=monotonic() - started,
            search_seconds=search_seconds,
            evidence=outcome.evidence,
            statistics=dict(outcome.statistics),
        )
    if outcome.status == OUTCOME_COMPLETE and outcome.candidate is not None:
        report = validate_candidate(snapshot, outcome.candidate)
        if not report.valid:
            return GenerationResult(
                OUTCOME_FAILED,
                None,
                report=report,
                message="The solver produced a candidate rejected by the validator.",
                wall_time_seconds=monotonic() - started,
                search_seconds=search_seconds,
                evidence=outcome.evidence,
            )
        quality = measure_initial_quality(snapshot, outcome.candidate)
        recovery_budget = time_limit_seconds - (monotonic() - started)
        if recovery_time_limit_seconds is not None:
            recovery_budget = min(recovery_budget, recovery_time_limit_seconds)
        if assess_recovery and recovery_budget > 0:
            recovery = recovery_assessment(
                snapshot,
                periods,
                outcome.candidate,
                search=search,
                time_limit_seconds=recovery_budget,
                num_workers=num_workers,
                random_seed=random_seed,
            )
        else:
            recovery = RecoveryAssessment(RECOVERY_SCENARIO, NOT_ASSESSED, "Not tested.")
        return GenerationResult(
            OUTCOME_COMPLETE,
            outcome.candidate,
            report=report,
            objective_days=outcome.objective_days,
            wall_time_seconds=monotonic() - started,
            search_seconds=search_seconds,
            quality=quality,
            statistics=dict(outcome.statistics),
            evidence=outcome.evidence,
            completion=_completion_report(snapshot, quality, recovery),
        )
    if outcome.status == OUTCOME_INFEASIBLE:
        return GenerationResult(
            OUTCOME_INFEASIBLE,
            None,
            message=outcome.message,
            wall_time_seconds=monotonic() - started,
            search_seconds=search_seconds,
            evidence=outcome.evidence,
        )
    return GenerationResult(
        outcome.status,
        None,
        message=outcome.message,
        wall_time_seconds=monotonic() - started,
        search_seconds=search_seconds,
        evidence=outcome.evidence,
    )
