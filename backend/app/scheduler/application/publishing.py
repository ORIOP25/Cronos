"""Pure construction of proposal payloads: product metrics and the diff.

The persisted proposal separates physical changes (positions and rooms) from
modular projections, so the school interface can explain "the lesson moved" in
a different way from "the planned module changed". Nothing here touches the
database, the solver or the clock.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    PlanningSnapshot,
    ScheduledLesson,
)
from app.scheduler.domain.candidate_validation import ValidationReport
from app.scheduler.domain.capacity import is_physically_protected
from app.scheduler.domain.debt import RecoveryAllocation
from app.scheduler.domain.diagnostics import Diagnosis
from app.scheduler.domain.quality import InitialQualityMetrics, SearchEvidence
from app.scheduler.domain.recovery import RecoveryQualityMetrics

WARNING_AFTER_PREFERENCE = "COMPLETION_AFTER_PREFERENCE"
WARNING_SEARCH_INTERRUPTED = "SEARCH_INTERRUPTED"


@dataclass(frozen=True)
class ProposalPayload:
    """Everything the persistence layer needs to store one proposal."""

    metrics: Mapping[str, Any]
    diff: Mapping[str, Any]


def _lesson_position(lesson: ScheduledLesson) -> tuple[Any, Any, Any]:
    return (
        lesson.period.school_date,
        lesson.period.start_local,
        lesson.period.end_local,
    )


def _lesson_summary(lesson: ScheduledLesson | None) -> dict[str, Any] | None:
    if lesson is None:
        return None
    return {
        "lesson_id": lesson.lesson_id,
        "date": lesson.period.school_date.isoformat(),
        "start": lesson.period.start_local.strftime("%H:%M"),
        "end": lesson.period.end_local.strftime("%H:%M"),
        "room_id": lesson.room_id,
        "credit_minutes": lesson.credit_minutes,
    }


def _slices_summary(lesson: ScheduledLesson) -> list[dict[str, int]]:
    return [
        {
            "module_id": row.module_id,
            "offset_minutes": row.offset_minutes,
            "minutes": row.credit_minutes,
        }
        for row in sorted(lesson.slices, key=lambda row: (row.offset_minutes, row.module_id))
    ]


def _same_position(left: ScheduledLesson, right: ScheduledLesson) -> bool:
    return (
        left.assignment_id == right.assignment_id
        and left.period.start_utc == right.period.start_utc
        and left.period.end_utc == right.period.end_utc
    )


def _class_entries(assignment: Assignment) -> list[dict[str, Any]]:
    """One diff row per member class; joint rows also list every sibling class."""
    class_ids = list(assignment.class_ids)
    if len(class_ids) == 1:
        return [{"class_id": class_ids[0]}]
    return [{"class_id": class_id, "joint_class_ids": class_ids} for class_id in class_ids]


def build_diff(snapshot: PlanningSnapshot, candidate: CandidateSchedule) -> dict[str, Any]:
    """Physical changes and modular projection updates against the baseline."""
    assignments = {row.assignment_id: row for row in snapshot.assignments}
    protected = {lesson.lesson_id for lesson in snapshot.protected_lessons}
    base = [lesson for lesson in snapshot.baseline_lessons if lesson.lesson_id not in protected]
    planned = [lesson for lesson in candidate.lessons if lesson.lesson_id not in protected]
    unmatched = list(base)
    physical: list[dict[str, Any]] = []
    modular: list[dict[str, Any]] = []
    counts = {
        "added": 0,
        "removed": 0,
        "moved": 0,
        "room_changed": 0,
        "modular_updates": 0,
    }
    for lesson in planned:
        source = None
        if lesson.source_lesson_id is not None:
            source = next(
                (row for row in unmatched if row.lesson_id == lesson.source_lesson_id), None
            )
        if source is None:
            source = next((row for row in unmatched if row.lesson_id == lesson.lesson_id), None)
        if source is None:
            source = next((row for row in unmatched if _same_position(row, lesson)), None)
        assignment = assignments.get(lesson.assignment_id)
        if assignment is None:
            continue
        if source is None:
            counts["added"] += 1
            for entry in _class_entries(assignment):
                physical.append(
                    {
                        "change_type": "ADDED",
                        "lesson_id": lesson.lesson_id,
                        "subject_id": assignment.subject_id,
                        **entry,
                        "before": None,
                        "after": _lesson_summary(lesson),
                    }
                )
            continue
        unmatched.remove(source)
        before = _lesson_summary(source)
        after = _lesson_summary(lesson)
        if _lesson_position(source) != _lesson_position(lesson):
            counts["moved"] += 1
            for entry in _class_entries(assignment):
                physical.append(
                    {
                        "change_type": "MOVED",
                        "lesson_id": source.lesson_id,
                        "subject_id": assignment.subject_id,
                        **entry,
                        "before": before,
                        "after": after,
                    }
                )
        elif source.room_id != lesson.room_id:
            counts["room_changed"] += 1
            for entry in _class_entries(assignment):
                physical.append(
                    {
                        "change_type": "ROOM_CHANGED",
                        "lesson_id": source.lesson_id,
                        "subject_id": assignment.subject_id,
                        **entry,
                        "before": before,
                        "after": after,
                    }
                )
        before_slices = _slices_summary(source)
        after_slices = _slices_summary(lesson)
        if before_slices != after_slices:
            counts["modular_updates"] += 1
            for entry in _class_entries(assignment):
                modular.append(
                    {
                        "lesson_id": lesson.lesson_id,
                        "subject_id": assignment.subject_id,
                        **entry,
                        "before": before_slices,
                        "after": after_slices,
                    }
                )
    for lesson in sorted(unmatched, key=lambda row: (row.period.start_utc, row.lesson_id)):
        assignment = assignments.get(lesson.assignment_id)
        if assignment is None:
            continue
        counts["removed"] += 1
        for entry in _class_entries(assignment):
            physical.append(
                {
                    "change_type": "REMOVED",
                    "lesson_id": lesson.lesson_id,
                    "subject_id": assignment.subject_id,
                    **entry,
                    "before": _lesson_summary(lesson),
                    "after": None,
                }
            )
    physical.sort(key=lambda row: (row["class_id"], row["subject_id"], row["lesson_id"]))
    modular.sort(key=lambda row: (row["class_id"], row["subject_id"], row["lesson_id"]))
    return {
        "is_first_generation": not snapshot.baseline_lessons,
        "physical": physical,
        "modular": modular,
        "counts": counts,
    }


def plan_recovery_allocations(
    snapshot: PlanningSnapshot,
    candidate: CandidateSchedule,
    *,
    claim_order: Sequence[int] | None = None,
) -> tuple[RecoveryAllocation, ...]:
    """Reserve open debt on the candidate lessons, oldest claim first.

    The plan links each open claim to the lessons of its own assignment that
    carry the residual minutes. Per-lesson reserved minutes never exceed the
    lesson credit and per-claim reserved minutes never exceed the open debt.
    Reservations are a plan: executing a lesson is what credits progress.
    """
    if snapshot.active_version_id is None or not snapshot.open_debt_minutes:
        return ()
    assignments = {row.assignment_id: row for row in snapshot.assignments}
    lessons_by_assignment: dict[int, list[ScheduledLesson]] = {}
    protected_ids = {row.lesson_id for row in snapshot.protected_lessons}
    for lesson in candidate.lessons:
        if lesson.assignment_id not in assignments:
            continue
        lessons_by_assignment.setdefault(lesson.assignment_id, []).append(lesson)
    for lessons in lessons_by_assignment.values():
        lessons.sort(key=lambda row: (row.period.start_utc, row.lesson_id))
    ordered_claims = (
        list(claim_order) if claim_order is not None else sorted(snapshot.open_debt_minutes)
    )
    if set(ordered_claims) != set(snapshot.open_debt_minutes):
        raise ValueError("Claim order must list exactly the open debt claims.")
    used_by_lesson: dict[tuple[int, int | None], int] = {}
    reservations: list[RecoveryAllocation] = []
    for claim_id in ordered_claims:
        assignment_id = snapshot.claim_assignments[claim_id]
        claim_class = snapshot.claim_classes.get(claim_id)
        if claim_class is None:
            owner = assignments.get(assignment_id)
            claim_class = owner.class_ids[0] if owner is not None else None
        remaining = snapshot.open_debt_minutes[claim_id]
        for lesson in lessons_by_assignment.get(assignment_id, ()):
            if remaining <= 0:
                break
            member_classes = (
                lesson.class_ids
                if lesson.class_ids is not None
                else assignments[assignment_id].class_ids
            )
            if claim_class is not None and claim_class not in member_classes:
                continue
            used = used_by_lesson.get((lesson.lesson_id, claim_class), 0)
            capacity = lesson.credit_minutes - used
            if lesson.lesson_id in protected_ids or is_physically_protected(
                snapshot, lesson.period
            ):
                # Carry a committed recovery without adding new reservations
                # inside the frozen window.
                committed = sum(
                    row.minutes
                    for row in snapshot.reservations
                    if row.version_id == snapshot.active_version_id
                    and row.lesson_id == lesson.lesson_id
                    and row.claim_id == claim_id
                )
                capacity = min(capacity, committed)
            if capacity <= 0:
                continue
            take = min(remaining, capacity)
            used_by_lesson[(lesson.lesson_id, claim_class)] = used + take
            remaining -= take
            reservations.append(
                RecoveryAllocation(snapshot.active_version_id, lesson.lesson_id, claim_id, take)
            )
        if remaining > 0:
            raise ValueError("Open debt exceeds the candidate credit for its assignment.")
    return tuple(reservations)


def evidence_to_dict(evidence: SearchEvidence | None) -> dict[str, Any] | None:
    """Full typed evidence so every quality claim can be replayed later."""
    if evidence is None:
        return None
    return {
        "objective_scope": evidence.objective_scope,
        "certified_stages": evidence.certified_stages,
        "stop_reason": evidence.stop_reason,
        "rounds": evidence.rounds,
        "proposals_excluded": evidence.proposals_excluded,
        "relaxation_bound": evidence.relaxation_bound,
        "relaxation_incumbent": evidence.relaxation_incumbent,
        "relaxation_proven": evidence.relaxation_proven,
        "relaxation_scope": evidence.relaxation_scope,
        "stages": [
            {
                "stage": stage.stage,
                "value": stage.value,
                "proven": stage.proven,
                "reused": stage.reused,
            }
            for stage in evidence.stages
        ],
    }


def _diagnostics_summary(diagnoses: tuple[Diagnosis, ...]) -> list[dict[str, Any]]:
    return [
        {
            "code": diagnosis.code.value,
            "message": diagnosis.message,
            "suggestions": list(diagnosis.suggestions),
            "minimum_missing_minutes": diagnosis.minimum_missing_minutes,
            "affected_class_ids": list(diagnosis.affected_class_ids),
        }
        for diagnosis in diagnoses
    ]


def _base_metrics(
    snapshot: PlanningSnapshot,
    report: ValidationReport,
    evidence: SearchEvidence | None,
    *,
    disruption_cost: int,
    changed_lessons: int,
) -> dict[str, Any]:
    completion_dates = dict(report.completion_dates)
    latest = max(completion_dates.values())
    preferred = snapshot.preferred_end_date
    after = sorted(class_id for class_id, day in completion_dates.items() if day > preferred)
    return {
        "completion_dates": {
            str(class_id): day.isoformat() for class_id, day in sorted(completion_dates.items())
        },
        "latest_completion_date": latest.isoformat(),
        "preferred_end_date": preferred.isoformat(),
        "hard_end_date": snapshot.hard_end_date.isoformat(),
        "margin_days": (preferred - latest).days,
        "excess_days": max(0, (latest - preferred).days),
        "classes_after_preferred": after,
        "disruption_cost": disruption_cost,
        "changed_lessons": changed_lessons,
        "teacher_gap_minutes": 0,
        "class_gap_minutes": 0,
        "preference_cost_minutes": 0,
        "room_change_cost": 0,
        "stop_reason": evidence.stop_reason if evidence is not None else "NOT_MEASURED",
        "certified_stages": evidence.certified_stages if evidence is not None else 0,
        "evidence": evidence_to_dict(evidence),
        "result_code": "COMPLETE",
        "validation": {
            "validator_version": report.validator_version,
            "valid": report.valid,
            "total_credit_minutes": report.total_credit_minutes,
        },
    }


def _apply_quality(metrics: dict[str, Any], quality: InitialQualityMetrics) -> None:
    metrics["teacher_gap_minutes"] = quality.teacher_gap_minutes
    metrics["class_gap_minutes"] = quality.class_gap_minutes
    metrics["preference_cost_minutes"] = quality.preference_cost_minutes
    metrics["room_change_cost"] = quality.room_change_cost


def _warnings(metrics: Mapping[str, Any]) -> list[str]:
    warnings = []
    if metrics.get("excess_days", 0) > 0:
        warnings.append(WARNING_AFTER_PREFERENCE)
    if metrics.get("stop_reason") == "SAFETY_LIMIT":
        warnings.append(WARNING_SEARCH_INTERRUPTED)
    return warnings


def initial_proposal_payload(
    snapshot: PlanningSnapshot,
    candidate: CandidateSchedule,
    *,
    quality: InitialQualityMetrics,
    report: ValidationReport,
    evidence: SearchEvidence | None,
    recovery_status: str = "NOT_ASSESSED",
    recovery_message: str = "",
    diagnoses: tuple[Diagnosis, ...] = (),
) -> ProposalPayload:
    metrics = _base_metrics(snapshot, report, evidence, disruption_cost=0, changed_lessons=0)
    _apply_quality(metrics, quality)
    metrics["excess_days"] = 0
    metrics["recovery_assessment"] = {
        "status": recovery_status,
        "message": recovery_message,
    }
    metrics["diagnostics"] = _diagnostics_summary(diagnoses)
    metrics["warnings"] = _warnings(metrics)
    return ProposalPayload(metrics=metrics, diff=build_diff(snapshot, candidate))


def recovery_proposal_payload(
    snapshot: PlanningSnapshot,
    candidate: CandidateSchedule,
    *,
    quality: RecoveryQualityMetrics,
    report: ValidationReport,
    evidence: SearchEvidence | None,
    diagnoses: tuple[Diagnosis, ...] = (),
) -> ProposalPayload:
    metrics = _base_metrics(
        snapshot,
        report,
        evidence,
        disruption_cost=quality.disruption.total_cost,
        changed_lessons=len(quality.disruption.changes),
    )
    _apply_quality(metrics, quality.initial)
    metrics["diagnostics"] = _diagnostics_summary(diagnoses)
    metrics["warnings"] = _warnings(metrics)
    return ProposalPayload(metrics=metrics, diff=build_diff(snapshot, candidate))
