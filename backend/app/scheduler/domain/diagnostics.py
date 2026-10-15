"""Honest diagnoses: minimum deficits only when demonstrated, estimates labelled.

The aggregate precheck proves a lower bound of missing minutes for one
assignment intersection (class, teacher, room, calendar). That quantity is
reported as proven; anything softer is an estimate or unknown. A search
interruption never becomes an impossibility claim.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

from app.scheduler.domain.calendar import Period
from app.scheduler.domain.candidate import Assignment, PlanningSnapshot
from app.scheduler.domain.capacity import (
    aggregate_capacity_check,
    eligible_periods,
    residual_minutes,
)


class DiagnosisCode(StrEnum):
    INSUFFICIENT_INTERSECTION = "INSUFFICIENT_INTERSECTION"
    INFEASIBLE_PROVEN = "INFEASIBLE_PROVEN"
    SEARCH_INCONCLUSIVE = "SEARCH_INCONCLUSIVE"
    BASELINE_STALE = "BASELINE_STALE"
    EXCESS_EXECUTED_CREDIT = "EXCESS_EXECUTED_CREDIT"
    EXECUTION_FAILURE = "EXECUTION_FAILURE"
    JOINT_NO_COMMON_TIME = "JOINT_NO_COMMON_TIME"


class EvidenceKind(StrEnum):
    PROVEN_LOWER_BOUND = "PROVEN_LOWER_BOUND"
    PROVEN_SCOPE = "PROVEN_SCOPE"
    ESTIMATE = "ESTIMATE"
    UNKNOWN = "UNKNOWN"


REVIEW_AVAILABILITY = "REVIEW_AVAILABILITY"
REVIEW_END_DATE = "REVIEW_END_DATE"
REVIEW_RECORDED_PROGRESS = "REVIEW_RECORDED_PROGRESS"
REVIEW_ROOMS = "REVIEW_ROOMS"
REVIEW_SAFETY_LIMIT = "REVIEW_SAFETY_LIMIT"


@dataclass(frozen=True)
class Diagnosis:
    code: DiagnosisCode
    evidence_kind: EvidenceKind
    message: str
    scope: str
    minimum_missing_minutes: int | None = None
    affected_class_ids: tuple[int, ...] = ()
    suggestions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.message or not self.scope:
            raise ValueError("A diagnosis needs a message and a scope.")
        if self.minimum_missing_minutes is not None:
            if self.evidence_kind is not EvidenceKind.PROVEN_LOWER_BOUND:
                raise ValueError("Only a proven lower bound carries a minimum deficit.")
            if type(self.minimum_missing_minutes) is not int or self.minimum_missing_minutes <= 0:
                raise ValueError("A minimum deficit must be positive minutes.")


def diagnose_capacity(
    snapshot: PlanningSnapshot, periods: tuple[Period, ...]
) -> tuple[Diagnosis, ...]:
    """Proven lower bounds of missing minutes for assignments that cannot fit.

    When the only unit left with no eligible period is a single joint unit, its
    isolation is the proven cause and is reported as ``JOINT_NO_COMMON_TIME``
    (WBS 3.9). Every other proven deficit keeps its generic diagnosis, so a
    general infeasibility is never relabelled.
    """
    check = aggregate_capacity_check(snapshot, periods)
    classes = {row.assignment_id: tuple(row.class_ids) for row in snapshot.assignments}
    isolated = _isolated_joint_unit(snapshot, periods)
    diagnoses: list[Diagnosis] = []
    if isolated is not None:
        diagnoses.append(joint_diagnosis(isolated))
    for assignment_id, deficit in sorted(check.deficits.items()):
        if deficit <= 0 or (isolated is not None and assignment_id == isolated.assignment_id):
            continue
        diagnoses.append(
            Diagnosis(
                code=DiagnosisCode.INSUFFICIENT_INTERSECTION,
                evidence_kind=EvidenceKind.PROVEN_LOWER_BOUND,
                message=(
                    f"At least {deficit} minute(s) of demand have no eligible period "
                    "given class, teacher, room, calendar and date limits."
                ),
                scope=f"ASSIGNMENT:{assignment_id}",
                minimum_missing_minutes=deficit,
                affected_class_ids=classes[assignment_id],
                suggestions=(REVIEW_AVAILABILITY, REVIEW_ROOMS, REVIEW_END_DATE),
            )
        )
    return tuple(diagnoses)


def _isolated_joint_unit(
    snapshot: PlanningSnapshot, periods: tuple[Period, ...]
) -> Assignment | None:
    """The single joint unit left without any eligible period, if it is alone."""
    blocked = [
        assignment
        for assignment in snapshot.assignments
        if residual_minutes(snapshot, assignment.assignment_id) > 0
        and not eligible_periods(snapshot, assignment, periods)
    ]
    if len(blocked) == 1 and len(blocked[0].class_ids) > 1:
        return blocked[0]
    return None


def joint_diagnosis(unit: Assignment) -> Diagnosis:
    """``JOINT_NO_COMMON_TIME`` for an isolated joint unit, with its classes.

    The snapshot carries no names, so the message uses ids and the structured
    ``affected_class_ids`` and ``scope`` carry the unit context (WBS 3.9).
    """
    return replace(
        diagnose_joint_no_common_time(
            str(unit.subject_id), tuple(str(class_id) for class_id in unit.class_ids)
        ),
        affected_class_ids=tuple(unit.class_ids),
        scope=f"JOINT_UNIT:{unit.subject_id}",
    )


def diagnose_joint_isolation(
    snapshot: PlanningSnapshot, periods: tuple[Period, ...]
) -> Diagnosis | None:
    """The joint isolation diagnosis when one joint unit alone has no period."""
    unit = _isolated_joint_unit(snapshot, periods)
    return None if unit is None else joint_diagnosis(unit)


def diagnose_joint_no_common_time(discipline: str, class_names: Sequence[str]) -> Diagnosis:
    """A joint unit with no shared free period, proven by isolation (WBS 3.9)."""
    joined = ", ".join(class_names)
    return Diagnosis(
        code=DiagnosisCode.JOINT_NO_COMMON_TIME,
        evidence_kind=EvidenceKind.PROVEN_SCOPE,
        message=f"As turmas {joined} não têm horas livres em comum para {discipline}.",
        scope="JOINT_UNIT",
        suggestions=(REVIEW_AVAILABILITY, REVIEW_END_DATE),
    )


def diagnose_scope_proof(message: str) -> Diagnosis:
    """A proof that covers the authorized scope without a per-resource minimum."""
    return Diagnosis(
        code=DiagnosisCode.INFEASIBLE_PROVEN,
        evidence_kind=EvidenceKind.PROVEN_SCOPE,
        message=message,
        scope="GLOBAL",
        suggestions=(REVIEW_AVAILABILITY, REVIEW_ROOMS, REVIEW_END_DATE),
    )


def diagnose_baseline_stale(missing_minutes: int, excess_minutes: int) -> Diagnosis:
    return Diagnosis(
        code=DiagnosisCode.BASELINE_STALE,
        evidence_kind=EvidenceKind.PROVEN_SCOPE,
        message=(
            "The published baseline no longer matches the current data "
            f"({missing_minutes} missing and {excess_minutes} excess published minute(s)); "
            "the repair was computed from the current state."
        ),
        scope="GLOBAL",
        suggestions=(REVIEW_RECORDED_PROGRESS, REVIEW_AVAILABILITY),
    )


def diagnose_inconclusive(message: str) -> Diagnosis:
    return Diagnosis(
        code=DiagnosisCode.SEARCH_INCONCLUSIVE,
        evidence_kind=EvidenceKind.UNKNOWN,
        message=(
            f"{message} The search did not prove that a complete schedule is impossible."
        ).strip(),
        scope="GLOBAL",
        suggestions=(REVIEW_SAFETY_LIMIT,),
    )


def diagnose_invalid_input(message: str) -> Diagnosis:
    return Diagnosis(
        code=DiagnosisCode.EXCESS_EXECUTED_CREDIT,
        evidence_kind=EvidenceKind.UNKNOWN,
        message=message,
        scope="GLOBAL",
        suggestions=(REVIEW_RECORDED_PROGRESS,),
    )


def diagnose_failure(message: str) -> Diagnosis:
    return Diagnosis(
        code=DiagnosisCode.EXECUTION_FAILURE,
        evidence_kind=EvidenceKind.UNKNOWN,
        message=message,
        scope="GLOBAL",
        suggestions=(REVIEW_SAFETY_LIMIT,),
    )
