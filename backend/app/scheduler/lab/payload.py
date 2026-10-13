"""Serialization of validation, quality, evidence and completion payloads.

The campaign stores the materialized candidate and everything needed to
revalidate it without running the solver again.
"""

from __future__ import annotations

from typing import Any

from app.scheduler.application.contracts import CompletionReport, RepairSummary
from app.scheduler.domain.candidate_validation import ValidationReport
from app.scheduler.domain.diagnostics import Diagnosis
from app.scheduler.domain.quality import InitialQualityMetrics, SearchEvidence
from app.scheduler.domain.recovery import BaselineAssessment, RecoveryQualityMetrics


def validation_to_dict(report: ValidationReport) -> dict[str, Any]:
    return {
        "validator_version": report.validator_version,
        "valid": report.valid,
        "violations": [
            {
                "code": violation.code.value,
                "message": violation.message,
                "assignment_id": violation.assignment_id,
                "lesson_id": violation.lesson_id,
                "resource_type": violation.resource_type,
                "resource_id": violation.resource_id,
            }
            for violation in report.violations
        ],
        "credited_minutes": {
            str(assignment_id): minutes
            for assignment_id, minutes in sorted(report.credited_minutes.items())
        },
        "total_credit_minutes": report.total_credit_minutes,
        "completion_dates": {
            str(class_id): day.isoformat()
            for class_id, day in sorted(report.completion_dates.items())
        },
    }


def quality_to_dict(metrics: InitialQualityMetrics) -> dict[str, Any]:
    return {
        "completion_dates": {
            str(class_id): day.isoformat()
            for class_id, day in sorted(metrics.completion_dates.items())
        },
        "teacher_gap_minutes": metrics.teacher_gap_minutes,
        "class_gap_minutes": metrics.class_gap_minutes,
        "preference_cost_minutes": metrics.preference_cost_minutes,
        "room_change_cost": metrics.room_change_cost,
    }


def evidence_to_dict(evidence: SearchEvidence) -> dict[str, Any]:
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


def completion_to_dict(report: CompletionReport) -> dict[str, Any]:
    return {
        "completion_dates": {
            str(class_id): day.isoformat()
            for class_id, day in sorted(report.completion_dates.items())
        },
        "latest_completion_date": report.latest_completion_date.isoformat(),
        "preferred_end_date": report.preferred_end_date.isoformat(),
        "margin_days": report.margin_days,
        "classes_after_preferred": list(report.classes_after_preferred),
        "recovery": {
            "scenario": report.recovery.scenario,
            "status": report.recovery.status,
            "message": report.recovery.message,
        },
    }


def baseline_to_dict(assessment: BaselineAssessment) -> dict[str, Any]:
    return {
        "valid": assessment.valid,
        "missing_minutes_by_assignment": {
            str(assignment_id): minutes
            for assignment_id, minutes in assessment.missing_minutes_by_assignment.items()
        },
        "excess_minutes_by_assignment": {
            str(assignment_id): minutes
            for assignment_id, minutes in assessment.excess_minutes_by_assignment.items()
        },
        "issues": [
            {
                "kind": issue.kind.value,
                "lesson_id": issue.lesson_id,
                "assignment_id": issue.assignment_id,
                "detail": issue.detail,
            }
            for issue in assessment.issues
        ],
    }


def recovery_quality_to_dict(metrics: RecoveryQualityMetrics) -> dict[str, Any]:
    return {
        "initial": quality_to_dict(metrics.initial),
        "disruption_cost": metrics.disruption.total_cost,
        "changes": [
            {
                "kind": change.kind.value,
                "cost": change.cost,
                "source_lesson_id": change.source_lesson_id,
                "candidate_lesson_id": change.candidate_lesson_id,
            }
            for change in metrics.disruption.changes
        ],
    }


def repair_summary_to_dict(summary: RepairSummary) -> dict[str, Any]:
    return {
        "completion_dates": {
            str(class_id): day.isoformat()
            for class_id, day in sorted(summary.completion_dates.items())
        },
        "latest_completion_date": summary.latest_completion_date.isoformat(),
        "preferred_end_date": summary.preferred_end_date.isoformat(),
        "hard_end_date": summary.hard_end_date.isoformat(),
        "classes_after_preferred": list(summary.classes_after_preferred),
        "excess_days": summary.excess_days,
        "disruption_cost": summary.disruption_cost,
        "changed_lessons": summary.changed_lessons,
    }


def diagnoses_to_dict(diagnoses: tuple[Diagnosis, ...]) -> list[dict[str, Any]]:
    return [
        {
            "code": diagnosis.code.value,
            "evidence_kind": diagnosis.evidence_kind.value,
            "message": diagnosis.message,
            "scope": diagnosis.scope,
            "minimum_missing_minutes": diagnosis.minimum_missing_minutes,
            "affected_class_ids": list(diagnosis.affected_class_ids),
            "suggestions": list(diagnosis.suggestions),
        }
        for diagnosis in diagnoses
    ]
