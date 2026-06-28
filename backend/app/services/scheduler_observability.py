from __future__ import annotations

from typing import Any

import structlog

from app import models


logger = structlog.get_logger(__name__)


def emit_scheduler_job_event(
    event_name: str,
    job: models.ScheduleGenerationJob,
    *,
    result: Any | None = None,
    draft_id: int | None = None,
    hard_constraint_failures: int | None = None,
) -> None:
    """Emit one bounded lifecycle event without affecting scheduler behavior."""
    metrics = getattr(result, "metrics", None) or {}
    summary = getattr(result, "summary", None) or {}
    payload = {
        "scheduler_event": event_name,
        "job_id": job.id,
        "organization_id": job.organization_id,
        "school_year_id": job.school_year_id,
        "strategy": _value(job.strategy),
        "trigger_type": _value(job.trigger_type),
        "job_status": _value(job.job_status),
        "result_category": _value(job.result_category),
        "duration_ms": job.duration_ms,
        "draft_id": draft_id,
        "recovery_level": getattr(result, "recovery_escalation_level", None),
        "adaptation_level": getattr(result, "adaptation_level", None),
        "hard_constraint_failures": (
            hard_constraint_failures
            if hard_constraint_failures is not None
            else int(metrics.get("hard_constraint_failures", 0))
        ),
        "recovered_debt_minutes": _metric(
            summary,
            metrics,
            "recovered_minutes",
        ),
        "remaining_debt_minutes": _metric(
            summary,
            metrics,
            "remaining_unscheduled_minutes",
            "residual_debt_minutes",
        ),
        "disruption_score": _metric(summary, metrics, "disruption_score"),
        "failure_category": job.failure_code,
    }
    try:
        logger.info("scheduler_generation_lifecycle", **payload)
    except Exception:
        # Scheduling correctness must not depend on the logging backend.
        return


def _metric(
    summary: dict[str, Any],
    metrics: dict[str, Any],
    *names: str,
) -> Any | None:
    for name in names:
        if name in metrics:
            return metrics[name]
        if name in summary:
            return summary[name]
    return None


def _value(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))
