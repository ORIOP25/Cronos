from datetime import UTC, datetime, timedelta

from app import models
from app.scheduler.domain.contracts import ValidatedGenerationResult
from app.services.scheduler_adaptive_engine import AdaptiveRepairEngine
from app.services.scheduler_job_runtime import GenerationExecutionContext, SchedulerJobRuntime
from tests.scheduler_job_13_fixture import scheduler_job_13_snapshot


async def test_failed_job_13_snapshot_places_all_new_curriculum_within_job_cap():
    snapshot = scheduler_job_13_snapshot()
    now = datetime.now(UTC)
    context = GenerationExecutionContext(
        job_id=13,
        organization_id=1,
        school_year_id=1,
        strategy=models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR,
        trigger_type=models.ScheduleGenerationTrigger.SCHEDULER_CHANGE,
        immutable_snapshot=snapshot,
        started_at=now,
        deadline_at=now + timedelta(minutes=5),
    )

    result = await AdaptiveRepairEngine().generate(context)

    assert isinstance(result, ValidatedGenerationResult)
    SchedulerJobRuntime._validate_adaptive_repair(context, result)
    additions = [block for block in result.blocks if block.reason_code == "NEW_CURRICULUM_DEMAND"]
    assert result.result_category == models.ScheduleGenerationResultCategory.COMPLETE_SUCCESS
    assert len(additions) == 30
    assert sum(block.duration_minutes for block in additions) == 1_500
    assert len({block.stable_block_key for block in additions}) == 30
    assert result.metrics["candidate_count"] == 3_868
    assert result.metrics["construction_duration_ms"] >= 0
    assert result.metrics["feasibility_solve_duration_ms"] >= 0
    assert result.metrics["result_extraction_duration_ms"] >= 0
