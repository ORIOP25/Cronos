from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.services.scheduler_complete_engine import CompleteGenerationEngine
from app.services.scheduler_job_runtime import (
    GenerationExecutionContext,
    NoValidGenerationOutput,
    ValidatedGenerationResult,
)
from tests.test_scheduler_candidates import _snapshot


pytestmark = pytest.mark.unit


def _context(snapshot: dict) -> GenerationExecutionContext:
    now = datetime.now(timezone.utc)
    return GenerationExecutionContext(
        job_id=1,
        organization_id=1,
        school_year_id=1,
        strategy=models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
        trigger_type=models.ScheduleGenerationTrigger.FIRST_GENERATION,
        immutable_snapshot={"generation_input": snapshot},
        started_at=now,
        deadline_at=now + timedelta(seconds=30),
    )


@pytest.mark.asyncio
async def test_complete_engine_returns_only_full_valid_annual_draft():
    snapshot = _snapshot()
    snapshot["lunch_rules"] = None
    snapshot["module_accounting"] = [
        {"id": 7, "subject_id": 2, "hours_total": 1, "sequence": 1},
        {"id": 8, "subject_id": 2, "hours_total": 1, "sequence": 2},
    ]

    result = await CompleteGenerationEngine().generate(_context(snapshot))

    assert isinstance(result, ValidatedGenerationResult)
    assert result.result_category == models.ScheduleGenerationResultCategory.COMPLETE_SUCCESS
    assert sum(block.duration_minutes for block in result.blocks) == 120
    assert [block.module_sequence_index for block in result.blocks] == [1, 2]
    assert result.summary["required_minutes"] == result.summary["scheduled_minutes"]


@pytest.mark.asyncio
async def test_complete_engine_returns_actionable_no_output_for_missing_demand():
    snapshot = _snapshot()
    snapshot["module_accounting"] = []

    result = await CompleteGenerationEngine().generate(_context(snapshot))

    assert isinstance(result, NoValidGenerationOutput)
    assert any("No required module demand" in blocker for blocker in result.blockers)


@pytest.mark.asyncio
async def test_complete_engine_never_returns_partial_first_schedule():
    snapshot = deepcopy(_snapshot())
    snapshot["hard_end_date"] = "2025-09-01"
    snapshot["lunch_rules"] = None
    snapshot["module_accounting"] = [
        {"id": 7, "subject_id": 2, "hours_total": 5, "sequence": 1}
    ]

    result = await CompleteGenerationEngine().generate(_context(snapshot))

    assert isinstance(result, NoValidGenerationOutput)
    assert result.metrics["scheduled_minutes"] < result.metrics["required_minutes"]
    assert any("Residual demand" in blocker for blocker in result.blockers)
