"""Deterministic campaign runner over lab manifests.

Select cases by ID, validate the selection, collect one result per case,
resume only when the full provenance key matches, persist failures as ERROR
results with atomic writes, and fail the campaign when a case does not satisfy
its declared expectation.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from app.scheduler.composition import generate_schedule, repair_published_schedule
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.domain.oracle import OracleBudgetExceededError
from app.scheduler.domain.quality import measure_initial_quality
from app.scheduler.domain.serialization import (
    candidate_digest,
    candidate_to_dict,
    lesson_to_dict,
    period_to_dict,
    snapshot_to_dict,
)
from app.scheduler.domain.stop import (
    ExplorationPolicy,
    TrajectoryPoint,
    replay_stop_policy,
)
from app.scheduler.infrastructure.search import search_adaptive_schedule
from app.scheduler.lab.fixtures import (
    CaseExpectation,
    Fixture,
    expected_violations_for,
    witness_report,
)
from app.scheduler.lab.longitudinal import replay_annual_events, replay_to_dict
from app.scheduler.lab.manifest import (
    SCHEMA_VERSION,
    LabCase,
    build_case,
    from_manifest,
    input_digest,
)
from app.scheduler.lab.payload import (
    baseline_to_dict,
    completion_to_dict,
    diagnoses_to_dict,
    evidence_to_dict,
    quality_to_dict,
    recovery_quality_to_dict,
    repair_summary_to_dict,
    validation_to_dict,
)
from app.scheduler.lab.recovery import (
    RecoveryCase,
    build_constructed_recovery_case,
    build_recovery_case,
    laboratory_policy,
    perturb_constructed_fixture,
)
from app.scheduler.lab.reports import (
    CampaignReport,
    CaseOutcome,
    CaseResult,
    case_result_from_dict,
    case_result_to_dict,
    report_to_dict,
)

MODE_WITNESS = "witness"
MODE_GENERATOR = "generator"
MODE_REPAIR = "repair"
MODE_TRAJECTORY = "trajectory"
MODE_LONGITUDINAL = "longitudinal"
VALID_MODES = (
    MODE_WITNESS,
    MODE_GENERATOR,
    MODE_REPAIR,
    MODE_TRAJECTORY,
    MODE_LONGITUDINAL,
)

C19_POLICIES = {
    "eager": ExplorationPolicy("lab-eager", 0.0, 0.0, 1, 0, minimum_solutions=1),
    "balanced": ExplorationPolicy("lab-balanced", 0.05, 0.05, 1, 0, minimum_solutions=2),
    "patient": ExplorationPolicy("lab-patient", 0.25, 1.0, 1, 3, minimum_solutions=3),
}


class CampaignSelectionError(ValueError):
    """The requested selection is unknown or resolves to no case."""


def expected_outcome(case: LabCase) -> CaseOutcome | None:
    if case.mutation is not None:
        return CaseOutcome.INVALID
    return {
        CaseExpectation.FEASIBLE_WITH_WITNESS: CaseOutcome.VALID,
        CaseExpectation.INFEASIBLE_PROVEN: CaseOutcome.INFEASIBLE,
        CaseExpectation.INVALID_INPUT: CaseOutcome.INVALID,
        CaseExpectation.EXPLORATORY_UNKNOWN: None,
    }[case.expectation]


def _provenance(
    case: LabCase,
    digest: str | None,
    code_identity: str,
    policy_version: str,
    mode: str,
    time_limit_seconds: float,
    workers: int,
) -> dict:
    outcome = expected_outcome(case)
    return {
        "case_id": case.case_id,
        "family": case.family,
        "version": case.version,
        "schema_version": SCHEMA_VERSION,
        "input_digest": digest,
        "mutation": case.mutation,
        "expected_violations": list(case.expected_violations),
        "expected_outcome": None if outcome is None else outcome.value,
        "events": list(case.events),
        "annual_events": None if case.annual is None else case.annual.events,
        "code_identity": code_identity,
        "policy_version": policy_version,
        "mode": mode,
        "time_limit_seconds": time_limit_seconds,
        "workers": workers,
        "seeds": {
            "fixture_seed": case.seeds.fixture_seed,
            "event_seed": case.seeds.event_seed,
            "solver_seed": case.seeds.solver_seed,
        },
    }


def _result(
    case: LabCase,
    outcome: CaseOutcome,
    digest: str,
    policy_version: str,
    *,
    violations: tuple[str, ...] = (),
    metrics: dict[str, int] | None = None,
    error: str = "",
    payload: dict | None = None,
) -> CaseResult:
    return CaseResult(
        case_id=case.case_id,
        family=case.family,
        version=case.version,
        outcome=outcome,
        input_digest=digest,
        metrics=metrics or {},
        violations=violations,
        error=error,
        expected_outcome=expected_outcome(case),
        policy_version=policy_version,
        payload=payload or {},
    )


def _generator_payload(
    case: LabCase,
    fixture: Fixture,
    generated,
    time_limit_seconds: float,
    workers: int,
) -> dict:
    payload = {
        "case_id": case.case_id,
        "snapshot": snapshot_to_dict(fixture.snapshot),
        "periods": [period_to_dict(period) for period in fixture.periods],
        "candidate": candidate_to_dict(generated.candidate),
        "candidate_digest": candidate_digest(generated.candidate),
        "limits": {"time_limit_seconds": time_limit_seconds, "workers": workers},
        "statistics": dict(generated.statistics),
    }
    if generated.report is not None:
        payload["validation"] = validation_to_dict(generated.report)
    if generated.quality is not None:
        payload["quality"] = quality_to_dict(generated.quality)
    if generated.evidence is not None:
        payload["evidence"] = evidence_to_dict(generated.evidence)
    if generated.completion is not None:
        payload["completion"] = completion_to_dict(generated.completion)
    return payload


def _evaluate_generator(
    case: LabCase,
    fixture: Fixture,
    digest: str,
    policy_version: str,
    time_limit_seconds: float,
    workers: int,
) -> CaseResult:
    if case.mutation is not None:
        return _result(
            case,
            CaseOutcome.ERROR,
            digest,
            policy_version,
            error="Generator mode does not evaluate candidate mutations.",
        )
    generated = generate_schedule(
        fixture.snapshot,
        fixture.periods,
        time_limit_seconds=time_limit_seconds,
        num_workers=workers,
        random_seed=case.seeds.solver_seed,
    )
    metrics = {
        "wall_time_ms": int(generated.wall_time_seconds * 1000),
        "search_time_ms": int(generated.search_seconds * 1000),
    }
    for key in ("build_ms", "solve_ms", "room_ms", "variables", "windows"):
        if key in generated.statistics:
            metrics[key] = generated.statistics[key]
    if generated.report is not None:
        metrics["total_credit_minutes"] = generated.report.total_credit_minutes
    if generated.objective_days is not None:
        metrics["objective_days"] = generated.objective_days
    if generated.quality is not None:
        metrics["teacher_gap_minutes"] = generated.quality.teacher_gap_minutes
        metrics["class_gap_minutes"] = generated.quality.class_gap_minutes
        metrics["preference_cost_minutes"] = generated.quality.preference_cost_minutes
        metrics["room_change_cost"] = generated.quality.room_change_cost
    if generated.evidence is not None:
        metrics["certified_stages"] = generated.evidence.certified_stages
        metrics["feedback_rounds"] = generated.evidence.rounds
        if generated.evidence.relaxation_bound is not None:
            metrics["relaxation_bound"] = generated.evidence.relaxation_bound
    if generated.completion is not None:
        metrics["margin_days"] = generated.completion.margin_days
        metrics["classes_after_preferred"] = len(generated.completion.classes_after_preferred)
    if generated.outcome == "COMPLETE":
        return _result(
            case,
            CaseOutcome.VALID,
            digest,
            policy_version,
            metrics=metrics,
            payload=_generator_payload(case, fixture, generated, time_limit_seconds, workers),
        )
    if generated.outcome == "INFEASIBLE":
        return _result(case, CaseOutcome.INFEASIBLE, digest, policy_version, metrics=metrics)
    if generated.outcome == "INCONCLUSIVE":
        return _result(
            case,
            CaseOutcome.INCONCLUSIVE,
            digest,
            policy_version,
            metrics=metrics,
            error=generated.message,
        )
    outcome = CaseOutcome.ERROR if generated.outcome == "FAILED" else CaseOutcome.INVALID
    violations = ()
    if generated.report is not None:
        violations = tuple(
            sorted({violation.code.value for violation in generated.report.violations})
        )
    return _result(
        case,
        outcome,
        digest,
        policy_version,
        violations=violations,
        metrics=metrics,
        error=generated.message,
    )


def recovery_case_for(case: LabCase, fixture: Fixture | None):
    if case.witness_mode == "constructed":
        if case.spec is None:
            raise ValueError("A constructed witness case needs an explicit spec.")
        return build_constructed_recovery_case(
            case.case_id,
            case.spec,
            family=case.family,
            version=case.version,
            fixture_seed=case.seeds.fixture_seed,
            event_seed=case.seeds.event_seed,
            extra_events=case.events,
            solver_seed=case.seeds.solver_seed,
        )
    if case.spec is not None:
        return build_recovery_case(
            case.case_id,
            case.spec,
            family=case.family,
            version=case.version,
            fixture_seed=case.seeds.fixture_seed,
            event_seed=case.seeds.event_seed,
            extra_events=case.events,
            solver_seed=case.seeds.solver_seed,
        )
    if fixture is not None:
        return perturb_constructed_fixture(
            fixture,
            event_seed=case.seeds.event_seed,
            extra_events=case.events,
            case_id=case.case_id,
            family=case.family,
            version=case.version,
        )
    raise ValueError("A recovery case needs either a spec or a built fixture.")


def _recovery_expectation(expectation: CaseExpectation) -> CaseOutcome | None:
    return {
        CaseExpectation.FEASIBLE_WITH_WITNESS: CaseOutcome.VALID,
        CaseExpectation.INFEASIBLE_PROVEN: CaseOutcome.INFEASIBLE,
        CaseExpectation.INVALID_INPUT: CaseOutcome.INVALID,
        CaseExpectation.EXPLORATORY_UNKNOWN: None,
    }[expectation]


@dataclass(frozen=True)
class _Prepared:
    """Everything a case needs before the solver runs, plus its provenance digest."""

    fixture: Fixture | None
    recovery: RecoveryCase | None
    digest: str | None


def _recovery_fixture(case: LabCase, recovery: RecoveryCase) -> Fixture:
    return Fixture(
        case_id=case.case_id,
        family=case.family,
        version=case.version,
        expectation=recovery.expectation,
        snapshot=recovery.snapshot,
        periods=recovery.periods,
        witness=None,
        fixture_seed=case.seeds.fixture_seed,
        event_seed=case.seeds.event_seed,
        solver_seed=case.seeds.solver_seed,
    )


def prepare_case(case: LabCase, mode: str) -> _Prepared:
    """Build the mathematical inputs (and digest) without running the solver.

    Resume checks the provenance of this result before spending any search
    effort, including for repair and trajectory cases where the digest depends
    on the perturbed snapshot rather than on the base spec.
    """
    if mode in (MODE_REPAIR, MODE_TRAJECTORY):
        if case.mutation is not None:
            return _Prepared(None, None, None)
        fixture = None if case.spec is not None else build_case(case)
        recovery = recovery_case_for(case, fixture)
        return _Prepared(fixture, recovery, input_digest(_recovery_fixture(case, recovery)))
    fixture = build_case(case)
    return _Prepared(fixture, None, input_digest(fixture))


def _evaluate_repair(
    case: LabCase,
    recovery: RecoveryCase | None,
    digest: str | None,
    policy_version: str,
    time_limit_seconds: float,
    workers: int,
) -> CaseResult:
    if case.mutation is not None:
        return _result(
            case,
            CaseOutcome.ERROR,
            digest or "",
            policy_version,
            error="Repair mode does not evaluate candidate mutations.",
        )
    if recovery is None:
        return _result(
            case,
            CaseOutcome.ERROR,
            digest or "",
            policy_version,
            error="The repair case was not prepared.",
        )
    recovery_digest = digest or input_digest(_recovery_fixture(case, recovery))
    policy = laboratory_policy(recovery.snapshot)
    repaired = repair_published_schedule(
        recovery.snapshot,
        recovery.periods,
        recovery.baseline,
        policy,
        time_limit_seconds=time_limit_seconds,
        num_workers=workers,
        random_seed=case.seeds.solver_seed,
    )
    expected = _recovery_expectation(recovery.expectation)
    metrics = {
        "wall_time_ms": int(repaired.wall_time_seconds * 1000),
        "search_time_ms": int(repaired.search_seconds * 1000),
    }
    for key in ("build_ms", "solve_ms", "room_ms", "variables", "windows"):
        if key in repaired.statistics:
            metrics[key] = repaired.statistics[key]
    if repaired.quality is not None:
        metrics["disruption_cost"] = repaired.quality.disruption.total_cost
        metrics["changed_lessons"] = len(repaired.quality.disruption.changes)
        metrics["teacher_gap_minutes"] = repaired.quality.initial.teacher_gap_minutes
        metrics["class_gap_minutes"] = repaired.quality.initial.class_gap_minutes
    if repaired.summary is not None:
        metrics["excess_days"] = repaired.summary.excess_days
    if repaired.evidence is not None:
        metrics["certified_stages"] = repaired.evidence.certified_stages
        metrics["feedback_rounds"] = repaired.evidence.rounds
    payload = {
        "case_id": case.case_id,
        "event": recovery.event,
        "baseline": [lesson_to_dict(row) for row in recovery.baseline.lessons],
        "candidate": None if repaired.candidate is None else candidate_to_dict(repaired.candidate),
        "baseline_assessment": None
        if repaired.baseline is None
        else baseline_to_dict(repaired.baseline),
        "diagnoses": diagnoses_to_dict(repaired.diagnoses),
    }
    if repaired.candidate is not None:
        payload["candidate_digest"] = candidate_digest(repaired.candidate)
    if repaired.report is not None:
        payload["validation"] = validation_to_dict(repaired.report)
    if repaired.quality is not None:
        payload["quality"] = recovery_quality_to_dict(repaired.quality)
    if repaired.evidence is not None:
        payload["evidence"] = evidence_to_dict(repaired.evidence)
    if repaired.summary is not None:
        payload["summary"] = repair_summary_to_dict(repaired.summary)
    if repaired.budget is not None:
        payload["budget"] = dict(repaired.budget.as_dict())
    if repaired.outcome == "COMPLETE":
        result = _result(
            case,
            CaseOutcome.VALID,
            recovery_digest,
            policy.version,
            metrics=metrics,
            payload=payload,
        )
    elif repaired.outcome == "INFEASIBLE":
        result = _result(
            case,
            CaseOutcome.INFEASIBLE,
            recovery_digest,
            policy.version,
            metrics=metrics,
            payload=payload,
        )
    elif repaired.outcome == "INCONCLUSIVE":
        result = _result(
            case,
            CaseOutcome.INCONCLUSIVE,
            recovery_digest,
            policy.version,
            metrics=metrics,
            error=repaired.message,
            payload=payload,
        )
    else:
        outcome = CaseOutcome.ERROR if repaired.outcome == "FAILED" else CaseOutcome.INVALID
        result = _result(
            case,
            outcome,
            recovery_digest,
            policy.version,
            metrics=metrics,
            error=repaired.message,
            payload=payload,
        )
    return replace(result, expected_outcome=expected)


def _evaluate_trajectory(
    case: LabCase,
    recovery: RecoveryCase | None,
    digest: str | None,
    policy_version: str,
    time_limit_seconds: float,
    workers: int,
) -> CaseResult:
    """C19: record one repair trajectory and replay explicit stopping policies."""
    if case.mutation is not None:
        return _result(
            case,
            CaseOutcome.ERROR,
            digest or "",
            policy_version,
            error="Trajectory mode does not evaluate candidate mutations.",
        )
    if recovery is None:
        return _result(
            case,
            CaseOutcome.ERROR,
            digest or "",
            policy_version,
            error="The trajectory case was not prepared.",
        )
    policy = laboratory_policy(recovery.snapshot)
    points: list[TrajectoryPoint] = []
    outcome = search_adaptive_schedule(
        recovery.snapshot,
        recovery.periods,
        recovery.baseline,
        policy,
        time_limit_seconds=time_limit_seconds,
        num_workers=workers,
        random_seed=case.seeds.solver_seed,
        trajectory_out=points,
    )
    report = (
        validate_candidate(recovery.snapshot, outcome.candidate)
        if outcome.candidate is not None
        else None
    )
    if any(
        points[index].incumbent >= points[index - 1].incumbent for index in range(1, len(points))
    ):
        return _result(
            case,
            CaseOutcome.ERROR,
            digest or "",
            policy_version,
            error="Trajectory points are not strictly improving incumbents.",
        )
    replays = (
        {
            name: replay_stop_policy(
                points, replay_policy, reference_horizon_seconds=time_limit_seconds
            )
            for name, replay_policy in C19_POLICIES.items()
        }
        if points
        else {}
    )
    payload = {
        "case_id": case.case_id,
        "event": recovery.event,
        "outcome": outcome.status,
        "trajectory": [
            {"elapsed_seconds": point.elapsed_seconds, "incumbent": list(point.incumbent)}
            for point in points
        ],
        "replays": {
            name: {
                "reason": replay.reason,
                "stopped_seconds": replay.stopped_seconds,
                "final_vector": list(replay.final_vector),
                "best_vector": list(replay.best_vector),
                "lost_gain": replay.lost_gain,
                "saved_seconds": replay.saved_seconds,
            }
            for name, replay in replays.items()
        },
    }
    if report is not None:
        payload["validation"] = validation_to_dict(report)
    metrics = {
        "trajectory_points": len(points),
        "wall_time_ms": int(outcome.wall_time_seconds * 1000),
    }
    for name, replay in replays.items():
        metrics[f"{name}_lost_gain"] = int(replay.lost_gain)
        metrics[f"{name}_saved_ms"] = int(replay.saved_seconds * 1000)
        metrics[f"{name}_stopped_ms"] = int(replay.stopped_seconds * 1000)
    expected = _recovery_expectation(recovery.expectation)
    if outcome.status == "COMPLETE" and report is not None and report.valid:
        outcome_case = CaseOutcome.VALID
    elif outcome.status == "INFEASIBLE":
        outcome_case = CaseOutcome.INFEASIBLE
    elif outcome.status == "INCONCLUSIVE":
        outcome_case = CaseOutcome.INCONCLUSIVE
    else:
        outcome_case = CaseOutcome.INVALID
    result = _result(
        case,
        outcome_case,
        digest or "",
        policy.version,
        metrics=metrics,
        error=""
        if outcome_case in (CaseOutcome.VALID, CaseOutcome.INFEASIBLE)
        else outcome.message,
        payload=payload,
    )
    return replace(result, expected_outcome=expected)


def _evaluate_longitudinal(
    case: LabCase,
    fixture: Fixture | None,
    digest: str,
    policy_version: str,
    time_limit_seconds: float,
    workers: int,
) -> CaseResult:
    """C14: accumulate a deterministic event sequence over an annual baseline."""
    if case.annual is None:
        return _result(
            case,
            CaseOutcome.ERROR,
            digest,
            policy_version,
            error="Longitudinal mode requires an annual case.",
        )
    if fixture is None or fixture.witness is None:
        return _result(
            case,
            CaseOutcome.ERROR,
            digest,
            policy_version,
            error="The annual fixture needs a constructed witness baseline.",
        )
    from app.scheduler.lab.annual import AnnualFixture

    annual = AnnualFixture(
        class_count=case.annual.class_count,
        profile=case.annual.profile,
        seed=case.annual.seed,
        snapshot=fixture.snapshot,
        periods=fixture.periods,
        witness=fixture.witness,
    )
    replay = replay_annual_events(
        annual,
        event_count=case.annual.events,
        event_seed=case.seeds.event_seed,
        step_days=case.annual.step_days,
        time_limit_seconds=time_limit_seconds,
        solver_seed=case.seeds.solver_seed,
        workers=workers,
        case_id=case.case_id,
    )
    payload = {
        "case_id": case.case_id,
        "replay": replay_to_dict(replay),
        "final_candidate_digest": (
            None if replay.final_candidate is None else candidate_digest(replay.final_candidate)
        ),
    }
    metrics = {
        "events_declared": replay.event_count,
        "events_completed": len(replay.steps),
        "executed_minutes": replay.executed_minutes,
        "planned_minutes": replay.planned_minutes,
    }
    if replay.completed and replay.conserved:
        outcome = CaseOutcome.VALID
        error = ""
    elif replay.completed:
        outcome = CaseOutcome.INVALID
        error = f"Conservation failed: {replay.stopped_reason}"
    else:
        outcome = CaseOutcome.INCONCLUSIVE
        error = replay.stopped_reason
    result = _result(
        case,
        outcome,
        digest,
        policy_version,
        metrics=metrics,
        error=error,
        payload=payload,
    )
    expected = _recovery_expectation(case.expectation)
    if outcome is CaseOutcome.INVALID:
        # A conservation or validation violation is a domain failure even for an
        # exploratory case; an honest INCONCLUSIVE stays without expectation.
        expected = CaseOutcome.VALID
    return replace(result, expected_outcome=expected)


def _evaluate_fixture(
    case: LabCase,
    fixture: Fixture,
    digest: str,
    policy_version: str,
    mode: str,
    time_limit_seconds: float,
    workers: int,
) -> CaseResult:
    if mode == MODE_GENERATOR:
        return _evaluate_generator(
            case, fixture, digest, policy_version, time_limit_seconds, workers
        )
    if case.mutation is not None:
        if fixture.witness is None:
            return _result(
                case,
                CaseOutcome.ERROR,
                digest,
                policy_version,
                error="A mutation case needs a witness to corrupt.",
            )
        report = witness_report(fixture)
        return _result(
            case,
            CaseOutcome.INVALID if not report.valid else CaseOutcome.VALID,
            digest,
            policy_version,
            violations=tuple(sorted({violation.code.value for violation in report.violations})),
            metrics={"total_credit_minutes": report.total_credit_minutes},
        )
    if case.expectation is CaseExpectation.FEASIBLE_WITH_WITNESS:
        if fixture.witness is None:
            return _result(
                case, CaseOutcome.ERROR, digest, policy_version, error="Missing witness."
            )
        report = witness_report(fixture)
        return _result(
            case,
            CaseOutcome.VALID if report.valid else CaseOutcome.INVALID,
            digest,
            policy_version,
            violations=tuple(sorted({violation.code.value for violation in report.violations})),
            metrics={"total_credit_minutes": report.total_credit_minutes},
            payload={
                "case_id": case.case_id,
                "snapshot": snapshot_to_dict(fixture.snapshot),
                "periods": [period_to_dict(period) for period in fixture.periods],
                "candidate": candidate_to_dict(fixture.witness),
                "candidate_digest": candidate_digest(fixture.witness),
                "validation": validation_to_dict(report),
                "quality": quality_to_dict(
                    measure_initial_quality(fixture.snapshot, fixture.witness)
                ),
            },
        )
    if case.expectation is CaseExpectation.INFEASIBLE_PROVEN:
        return _result(
            case,
            CaseOutcome.INFEASIBLE if fixture.witness is None else CaseOutcome.VALID,
            digest,
            policy_version,
        )
    if case.expectation is CaseExpectation.INVALID_INPUT:
        if fixture.witness is None:
            return _result(case, CaseOutcome.INVALID, digest, policy_version)
        report = witness_report(fixture)
        return _result(
            case,
            CaseOutcome.VALID if report.valid else CaseOutcome.INVALID,
            digest,
            policy_version,
            violations=tuple(sorted({violation.code.value for violation in report.violations})),
            metrics={"total_credit_minutes": report.total_credit_minutes},
        )
    return _result(case, CaseOutcome.INCONCLUSIVE, digest, policy_version)


def _evaluate_prepared(
    case: LabCase,
    prepared: _Prepared,
    policy_version: str,
    mode: str,
    time_limit_seconds: float,
    workers: int,
) -> CaseResult:
    if mode == MODE_LONGITUDINAL:
        return _evaluate_longitudinal(
            case,
            prepared.fixture,
            prepared.digest or "",
            policy_version,
            time_limit_seconds,
            workers,
        )
    if mode == MODE_TRAJECTORY:
        return _evaluate_trajectory(
            case, prepared.recovery, prepared.digest, policy_version, time_limit_seconds, workers
        )
    if mode == MODE_REPAIR:
        return _evaluate_repair(
            case, prepared.recovery, prepared.digest, policy_version, time_limit_seconds, workers
        )
    if prepared.fixture is None:
        return _result(
            case,
            CaseOutcome.ERROR,
            prepared.digest or "",
            policy_version,
            error="The case fixture was not prepared.",
        )
    return _evaluate_fixture(
        case,
        prepared.fixture,
        prepared.digest or "",
        policy_version,
        mode,
        time_limit_seconds,
        workers,
    )


def _prepare_error_result(case: LabCase, exc: Exception, policy_version: str) -> CaseResult:
    outcome = (
        CaseOutcome.INVALID
        if case.expectation is CaseExpectation.INVALID_INPUT and case.mutation is None
        else CaseOutcome.ERROR
    )
    return _result(
        case,
        outcome,
        "",
        policy_version,
        violations=("INVALID_INPUT",) if outcome is CaseOutcome.INVALID else (),
        error=f"{type(exc).__name__}: {exc}",
    )


def case_passes(case: LabCase, result: CaseResult) -> bool:
    """Fail closed: an unsettled or failed outcome never passes as success.

    A declared expectation decides VALID/INFEASIBLE/INVALID. Without one
    (exploratory), only settled results count as concluded; errors, omissions
    and inconclusive searches block the campaign.
    """
    if result.outcome in (CaseOutcome.ERROR, CaseOutcome.OMITTED):
        return False
    if result.passed is False:
        return False
    if case.mutation is not None:
        required = set(case.expected_violations) or set(expected_violations_for(case.mutation))
        if not required <= set(result.violations):
            return False
    if result.passed is True:
        return True
    return result.settled


def _atomic_write(path: Path, text: str) -> None:
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def run_campaign_directory(
    manifest: dict,
    out_dir: str | Path,
    *,
    case_ids: Iterable[str] | None = None,
    commit: str = "unknown",
    code_identity: str = "unknown",
    policy_version: str = "",
    mode: str = MODE_WITNESS,
    time_limit_seconds: float = 10.0,
    workers: int = 1,
    resume: bool = False,
) -> CampaignReport:
    if mode not in VALID_MODES:
        raise CampaignSelectionError(f"Unknown campaign mode: {mode}")
    campaign_id, cases = from_manifest(manifest)
    if case_ids is None:
        selected = list(cases)
    else:
        requested = set(case_ids)
        known = {case.case_id for case in cases}
        unknown = sorted(requested - known)
        if unknown:
            raise CampaignSelectionError(f"Unknown case IDs: {unknown}")
        selected = [case for case in cases if case.case_id in requested]
    if not selected:
        raise CampaignSelectionError("The campaign selection is empty.")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    results: list[CaseResult] = []
    for case in selected:
        result_path = out / f"{case.case_id}.json"
        try:
            prepared = prepare_case(case, mode)
        except ValueError as exc:
            result = _prepare_error_result(case, exc, policy_version)
            provenance = _provenance(
                case, None, code_identity, policy_version, mode, time_limit_seconds, workers
            )
            _atomic_write(
                result_path,
                json.dumps(
                    {"provenance": provenance, "result": case_result_to_dict(result)},
                    indent=2,
                )
                + "\n",
            )
            results.append(result)
            continue
        except OracleBudgetExceededError as exc:
            result = _result(
                case,
                CaseOutcome.ERROR,
                "",
                policy_version,
                error=f"{type(exc).__name__}: {exc}",
            )
            provenance = _provenance(
                case, None, code_identity, policy_version, mode, time_limit_seconds, workers
            )
            _atomic_write(
                result_path,
                json.dumps(
                    {"provenance": provenance, "result": case_result_to_dict(result)},
                    indent=2,
                )
                + "\n",
            )
            results.append(result)
            continue
        provenance = _provenance(
            case,
            prepared.digest,
            code_identity,
            policy_version,
            mode,
            time_limit_seconds,
            workers,
        )
        if resume and result_path.exists():
            try:
                stored = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                stored = None
            if stored is not None and stored.get("provenance") == provenance:
                results.append(case_result_from_dict(stored["result"]))
                continue
        result = _evaluate_prepared(
            case, prepared, policy_version, mode, time_limit_seconds, workers
        )
        _atomic_write(
            result_path,
            json.dumps(
                {"provenance": provenance, "result": case_result_to_dict(result)},
                indent=2,
            )
            + "\n",
        )
        results.append(result)
    report = CampaignReport(
        campaign_id,
        commit,
        tuple(results),
        code_identity=code_identity,
        schema_version=SCHEMA_VERSION,
    )
    _atomic_write(out / "report.json", json.dumps(report_to_dict(report), indent=2) + "\n")
    return report


def campaign_failures(manifest: dict, report: CampaignReport) -> tuple[str, ...]:
    _, cases = from_manifest(manifest)
    by_id = {case.case_id: case for case in cases}
    return tuple(
        result.case_id
        for result in report.results
        if result.case_id in by_id and not case_passes(by_id[result.case_id], result)
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a scheduler lab campaign.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--commit", default="unknown")
    parser.add_argument("--code-identity", default="unknown")
    parser.add_argument("--policy-version", default="")
    parser.add_argument("--mode", choices=VALID_MODES, default=MODE_WITNESS)
    parser.add_argument("--time-limit", type=float, default=10.0)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    try:
        report = run_campaign_directory(
            manifest,
            args.out,
            case_ids=args.case_ids,
            commit=args.commit,
            code_identity=args.code_identity,
            policy_version=args.policy_version,
            mode=args.mode,
            time_limit_seconds=args.time_limit,
            workers=args.workers,
            resume=args.resume,
        )
    except CampaignSelectionError as exc:
        print(f"[campaign] selection error: {exc}")
        return 2
    failures = campaign_failures(manifest, report)
    counts: dict[str, int] = {}
    for result in report.results:
        counts[result.outcome.value] = counts.get(result.outcome.value, 0) + 1
    print(f"[campaign] {report.campaign_id}: {len(report.results)} case(s) {counts}")
    if failures:
        print(f"[campaign] failing cases: {', '.join(failures)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
