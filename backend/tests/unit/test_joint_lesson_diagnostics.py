"""Joint lesson solver diagnostics and deficit priority (WBS 3.4/3.9).

The only proven cause that earns ``JOINT_NO_COMMON_TIME`` is a single joint unit
with no eligible shared period. General deficits, cancellations and interrupted
searches keep their honest generic outcome. The deficit (``D``) unit is an
ordinary residual unit: it competes on the same priority every debt uses, so no
special identifier or snapshot metadata is required.
"""

from __future__ import annotations

from dataclasses import replace
from time import monotonic

from app.scheduler.application.generation import GenerationResult, generate_complete
from app.scheduler.application.recovery import RepairResult
from app.scheduler.domain.candidate import (
    Assignment,
    PlanningSnapshot,
    SchedulingStrategy,
    Unavailability,
    UnavailableResource,
)
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.domain.diagnostics import (
    Diagnosis,
    DiagnosisCode,
    EvidenceKind,
    diagnose_capacity,
    diagnose_joint_no_common_time,
    diagnose_scope_proof,
)
from app.scheduler.domain.projection import ModuleRequirement
from app.scheduler.domain.quality import SearchEvidence
from app.scheduler.domain.results import OUTCOME_CANCELLED, OUTCOME_INFEASIBLE
from app.scheduler.infrastructure.recovery_construction import construct_recovery
from app.scheduler.infrastructure.search import search_complete_schedule
from app.scheduler_v1_worker import _terminal_finish
from tests.unit.test_scheduler_resource_exclusivity_v1 import assignment, plan
from tests.unit.test_scheduler_w04_w05_regressions_v1 import period, snapshot

JOINT_ASSIGNMENT_ID = 10


def joint_unit(periods, *, unavailable=(), required=120):
    """One joint unit of classes 1 and 2 with no common free period."""
    unit = Assignment(
        JOINT_ASSIGNMENT_ID,
        (1, 2),
        1,
        7,
        frozenset({1, 2}),
        (ModuleRequirement(1, 1, required),),
    )
    return replace(
        snapshot(periods, minutes=required, count=2),
        assignments=(unit,),
        unavailable=tuple(unavailable),
    )


def test_isolated_joint_unit_is_diagnosed_as_no_common_time():
    periods = (period(0, start=9, end=10), period(0, start=10, end=11))
    target = joint_unit(
        periods,
        unavailable=(
            Unavailability(UnavailableResource.CLASS, 1, periods[0]),
            Unavailability(UnavailableResource.CLASS, 2, periods[1]),
        ),
    )

    diagnoses = diagnose_capacity(target, periods)

    assert diagnoses
    assert diagnoses[0].code is DiagnosisCode.JOINT_NO_COMMON_TIME
    assert diagnoses[0].affected_class_ids == (1, 2)
    assert diagnoses[0].scope == "JOINT_UNIT:1"
    assert "não têm horas livres em comum" in diagnoses[0].message
    assert "1" in diagnoses[0].message and "2" in diagnoses[0].message


def test_search_returns_infeasible_with_the_joint_message():
    periods = (period(0, start=9, end=10), period(0, start=10, end=11))
    target = joint_unit(
        periods,
        unavailable=(
            Unavailability(UnavailableResource.CLASS, 1, periods[0]),
            Unavailability(UnavailableResource.CLASS, 2, periods[1]),
        ),
    )

    outcome = search_complete_schedule(target, periods, time_limit_seconds=5)

    assert outcome.status == OUTCOME_INFEASIBLE
    expected = diagnose_joint_no_common_time("1", ("1", "2"))
    assert outcome.message == expected.message


def test_generate_complete_reports_an_isolated_joint_unit_with_code_and_message():
    periods = (period(0, start=9, end=10), period(0, start=10, end=11))
    target = joint_unit(
        periods,
        unavailable=(
            Unavailability(UnavailableResource.CLASS, 1, periods[0]),
            Unavailability(UnavailableResource.CLASS, 2, periods[1]),
        ),
    )

    result = generate_complete(
        target, periods, search=search_complete_schedule, time_limit_seconds=10
    )

    expected = diagnose_joint_no_common_time("1", ("1", "2"))
    assert result.outcome == OUTCOME_INFEASIBLE
    assert result.message == expected.message
    assert result.evidence is not None
    assert result.evidence.stop_reason == "JOINT_NO_COMMON_TIME"


def test_generate_complete_keeps_a_general_deficit_generic():
    periods = (period(0, start=9, end=10),)
    target = replace(
        snapshot(periods, minutes=120, count=2),
        unavailable=(
            Unavailability(UnavailableResource.CLASS, 1, periods[0]),
            Unavailability(UnavailableResource.CLASS, 2, periods[0]),
        ),
    )

    result = generate_complete(
        target, periods, search=search_complete_schedule, time_limit_seconds=10
    )

    assert result.outcome == OUTCOME_INFEASIBLE
    assert "Proven minimum deficit" in result.message
    assert result.evidence is None


def test_generate_complete_does_not_relabel_a_cancellation():
    periods = (period(0, start=9, end=10), period(0, start=10, end=11))
    target = joint_unit(periods)

    result = generate_complete(
        target,
        periods,
        search=search_complete_schedule,
        should_cancel=lambda: True,
        time_limit_seconds=10,
    )

    assert result.outcome == OUTCOME_CANCELLED
    assert result.evidence is None


def test_general_infeasibility_is_not_labelled_as_joint():
    periods = (period(0, start=9, end=10),)
    target = replace(
        snapshot(periods, minutes=120, count=2),
        unavailable=(
            Unavailability(UnavailableResource.CLASS, 1, periods[0]),
            Unavailability(UnavailableResource.CLASS, 2, periods[0]),
        ),
    )

    diagnoses = diagnose_capacity(target, periods)

    assert all(diagnosis.code is not DiagnosisCode.JOINT_NO_COMMON_TIME for diagnosis in diagnoses)
    assert {diagnosis.code for diagnosis in diagnoses} == {DiagnosisCode.INSUFFICIENT_INTERSECTION}


def test_a_cancelled_search_is_never_labelled_as_joint():
    periods = (period(0, start=9, end=10), period(0, start=10, end=11))
    target = joint_unit(
        periods,
        unavailable=(
            Unavailability(UnavailableResource.CLASS, 1, periods[0]),
            Unavailability(UnavailableResource.CLASS, 2, periods[1]),
        ),
    )

    outcome = search_complete_schedule(target, periods, should_cancel=lambda: True)

    assert outcome.status == OUTCOME_CANCELLED
    assert "não têm horas livres em comum" not in outcome.message


def test_a_shared_free_period_is_not_isolated():
    periods = (period(0, start=9, end=10), period(0, start=10, end=11))
    target = joint_unit(
        periods,
        unavailable=(Unavailability(UnavailableResource.CLASS, 1, periods[0]),),
        required=60,
    )

    assert diagnose_capacity(target, periods) == ()


def test_deficit_unit_priority_is_the_residual_priority():
    periods = (period(0, start=9, end=10), period(0, start=10, end=11))
    ordinary = assignment(1, 1, 1, {1}, 120)
    deficit = assignment(2, 1, 1, {1}, 60)
    target = replace(
        plan(periods, [ordinary, deficit]),
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        executed_minutes={1: {1: 60}},
    )

    candidate = construct_recovery(target, periods, deadline=monotonic() + 20)

    assert candidate is not None
    assert validate_candidate(target, candidate).valid
    # The deficit needs all 60 of its 60 remaining minutes (fraction 1.0), ahead
    # of a unit that needs 60 of 120 (fraction 0.5): the ordinary residual
    # priority, computed from the deficit exactly like any open debt.
    positions = {lesson.assignment_id: lesson.period for lesson in candidate.lessons}
    assert positions[2] == periods[0]
    assert positions[1] == periods[1]


def _joint_evidence() -> SearchEvidence:
    return SearchEvidence(
        objective_scope="JOINT_UNIT_CAPACITY",
        stages=(),
        certified_stages=0,
        stop_reason="JOINT_NO_COMMON_TIME",
    )


def test_worker_propagates_the_complete_generation_joint_code():
    result = GenerationResult(
        OUTCOME_INFEASIBLE, None, message="As turmas 1, 2 ...", evidence=_joint_evidence()
    )

    assert _terminal_finish(result) == (
        "INFEASIBLE",
        "JOINT_NO_COMMON_TIME",
        "JOINT_NO_COMMON_TIME",
    )


def test_worker_propagates_the_recovery_joint_diagnosis_code():
    result = RepairResult(
        OUTCOME_INFEASIBLE,
        None,
        diagnoses=(diagnose_joint_no_common_time("1", ("1", "2")),),
    )

    assert _terminal_finish(result) == (
        "INFEASIBLE",
        "JOINT_NO_COMMON_TIME",
        "JOINT_NO_COMMON_TIME",
    )


def test_worker_keeps_a_generic_infeasible_generic():
    result = GenerationResult(
        OUTCOME_INFEASIBLE, None, message="Proven minimum deficit: assignment 1: 60 minute(s)."
    )

    assert _terminal_finish(result) == ("INFEASIBLE", "INFEASIBLE", "INFEASIBLE")


def test_worker_keeps_a_no_joint_recovery_diagnosis_generic():
    result = RepairResult(
        OUTCOME_INFEASIBLE,
        None,
        diagnoses=(
            Diagnosis(
                code=DiagnosisCode.INSUFFICIENT_INTERSECTION,
                evidence_kind=EvidenceKind.PROVEN_LOWER_BOUND,
                message="At least 60 minute(s) of demand have no eligible period.",
                scope="ASSIGNMENT:1",
            ),
        ),
    )

    assert _terminal_finish(result) == ("INFEASIBLE", "INFEASIBLE", "INFEASIBLE")


def test_worker_keeps_a_scope_proof_diagnosis_generic():
    result = RepairResult(
        OUTCOME_INFEASIBLE,
        None,
        diagnoses=(diagnose_scope_proof("The annual quota relaxation is infeasible."),),
    )

    assert _terminal_finish(result) == ("INFEASIBLE", "INFEASIBLE", "INFEASIBLE")


def test_worker_keeps_an_unrelated_evidence_stop_reason_generic():
    result = GenerationResult(
        OUTCOME_INFEASIBLE,
        None,
        message="The search stopped.",
        evidence=SearchEvidence(
            objective_scope="ANNUAL_QUOTA_RELAXATION",
            stages=(),
            certified_stages=0,
            stop_reason="EXHAUSTED",
        ),
    )

    assert _terminal_finish(result) == ("INFEASIBLE", "INFEASIBLE", "INFEASIBLE")


def test_worker_does_not_relabel_other_outcomes():
    result = GenerationResult(OUTCOME_CANCELLED, None, message="The request was cancelled.")

    assert _terminal_finish(result) == ("CANCELLED", "CANCELLED", "CANCELLED")


def test_joint_unit_dataclass_is_plain_domain_data():
    periods = (period(0, start=9, end=10),)
    target: PlanningSnapshot = joint_unit(periods)

    unit = target.assignments[0]
    assert unit.class_ids == (1, 2)
    assert not hasattr(unit, "teaching_unit_key")
