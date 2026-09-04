from types import SimpleNamespace

from app import models
from app.services import scheduler_observability


class _CapturingLogger:
    def __init__(self):
        self.calls = []

    def info(self, event, **fields):
        self.calls.append((event, fields))


def test_scheduler_event_contains_required_diagnostic_metrics(monkeypatch):
    logger = _CapturingLogger()
    monkeypatch.setattr(scheduler_observability, "logger", logger)
    job = models.ScheduleGenerationJob(
        id=19,
        organization_id=7,
        school_year_id=8,
        strategy=models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR,
        trigger_type=models.ScheduleGenerationTrigger.MIXED,
        job_status=models.ScheduleGenerationJobStatus.SUCCEEDED,
        result_category=models.ScheduleGenerationResultCategory.PARTIAL_RECOVERY,
        duration_ms=42_000,
    )
    result = SimpleNamespace(
        recovery_escalation_level="DEADLINE_RESCUE",
        adaptation_level="AFFECTED_CLASSES",
        summary={
            "recovered_minutes": 480,
            "remaining_unscheduled_minutes": 120,
        },
        metrics={
            "disruption_score": 17.5,
            "hard_constraint_failures": 0,
            "quality_completed_stage": "GAPS_AVAILABILITY",
            "workload_override_used": True,
        },
    )

    scheduler_observability.emit_scheduler_job_event(
        "generation_succeeded",
        job,
        result=result,
        draft_id=23,
    )

    event, fields = logger.calls[0]
    assert event == "scheduler_generation_lifecycle"
    assert fields == {
        "scheduler_event": "generation_succeeded",
        "job_id": 19,
        "organization_id": 7,
        "school_year_id": 8,
        "strategy": "ADAPTIVE_REPAIR",
        "trigger_type": "MIXED",
        "job_status": "SUCCEEDED",
        "result_category": "PARTIAL_RECOVERY",
        "duration_ms": 42_000,
        "draft_id": 23,
        "recovery_level": "DEADLINE_RESCUE",
        "adaptation_level": "AFFECTED_CLASSES",
        "hard_constraint_failures": 0,
        "recovered_debt_minutes": 480,
        "remaining_debt_minutes": 120,
        "disruption_score": 17.5,
        "quality_completed_stage": "GAPS_AVAILABILITY",
        "workload_override_used": True,
        "failure_category": None,
    }


def test_scheduler_logging_failure_never_breaks_generation(monkeypatch):
    logger = SimpleNamespace(info=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError()))
    monkeypatch.setattr(scheduler_observability, "logger", logger)
    job = models.ScheduleGenerationJob(
        id=1,
        organization_id=1,
        school_year_id=1,
        strategy=models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
        job_status=models.ScheduleGenerationJobStatus.QUEUED,
    )

    scheduler_observability.emit_scheduler_job_event("generation_queued", job)
