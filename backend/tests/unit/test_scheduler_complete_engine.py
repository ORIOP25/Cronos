from copy import deepcopy
from datetime import UTC, date, datetime, timedelta

from app import models
from app.services.scheduler_complete_engine import CompleteGenerationEngine
from app.services.scheduler_far_fill import AssembledScheduleBlock, CompleteScheduleAssembly
from app.services.scheduler_job_runtime import (
    GenerationExecutionContext,
    NoValidGenerationOutput,
    ValidatedGenerationResult,
)
from app.services.scheduler_near_optimizer import NearFutureResult
from tests.unit.test_scheduler_candidates import _snapshot


def _context(snapshot: dict) -> GenerationExecutionContext:
    now = datetime.now(UTC)
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


async def test_complete_engine_returns_only_full_valid_annual_draft():
    snapshot = _snapshot()
    snapshot["lunch_rules"] = None
    snapshot["module_accounting"] = [
        {"id": 7, "subject_id": 2, "required_minutes": 60, "sequence": 1},
        {"id": 8, "subject_id": 2, "required_minutes": 60, "sequence": 2},
    ]

    result = await CompleteGenerationEngine().generate(_context(snapshot))

    assert isinstance(result, ValidatedGenerationResult)
    assert result.result_category == models.ScheduleGenerationResultCategory.COMPLETE_SUCCESS
    assert sum(block.duration_minutes for block in result.blocks) == 120
    assert [block.module_sequence_index for block in result.blocks] == [1, 2]
    assert result.summary["required_minutes"] == result.summary["scheduled_minutes"]


async def test_complete_engine_returns_actionable_no_output_for_missing_demand():
    snapshot = _snapshot()
    snapshot["module_accounting"] = []

    result = await CompleteGenerationEngine().generate(_context(snapshot))

    assert isinstance(result, NoValidGenerationOutput)
    assert any("No required module demand" in blocker for blocker in result.blockers)


async def test_complete_engine_never_returns_partial_first_schedule():
    snapshot = deepcopy(_snapshot())
    snapshot["hard_end_date"] = "2025-09-01"
    snapshot["lunch_rules"] = None
    snapshot["module_accounting"] = [
        {"id": 7, "subject_id": 2, "required_minutes": 300, "sequence": 1}
    ]

    result = await CompleteGenerationEngine().generate(_context(snapshot))

    assert isinstance(result, NoValidGenerationOutput)
    assert result.metrics["scheduled_minutes"] < result.metrics["required_minutes"]
    assert any("Residual demand" in blocker for blocker in result.blockers)


async def test_complete_engine_continues_after_empty_near_horizon():
    snapshot = _snapshot()
    snapshot["start_date"] = "2026-06-01"
    snapshot["hard_end_date"] = "2026-12-31"
    snapshot["lunch_rules"] = None
    snapshot["module_accounting"] = [
        {"id": 7, "subject_id": 2, "required_minutes": 60, "sequence": 1}
    ]
    snapshot["calendar_events"] = [
        {"start_date": "2026-06-01", "end_date": "2026-08-24", "event_type": "school_break"}
    ]

    result = await CompleteGenerationEngine().generate(_context(snapshot))

    assert isinstance(result, ValidatedGenerationResult)
    assert result.blocks[0].date > date(2026, 8, 24)


async def test_complete_engine_retains_near_search_exhaustion_scope(monkeypatch):
    snapshot = _snapshot()
    snapshot["lunch_rules"] = None
    snapshot["module_accounting"] = [
        {"id": 7, "subject_id": 2, "required_minutes": 60, "sequence": 1}
    ]

    monkeypatch.setattr(
        "app.services.scheduler_complete_engine.NearFutureOptimizer.optimize",
        lambda *_args, **_kwargs: NearFutureResult((), "search_exhausted", 0, 1, {}),
    )
    monkeypatch.setattr(
        "app.services.scheduler_complete_engine.FarFutureFiller.fill",
        lambda *_args, **_kwargs: CompleteScheduleAssembly(
            blocks=(
                AssembledScheduleBlock(
                    stable_block_key="far",
                    class_id=1,
                    subject_id=2,
                    teacher_id=3,
                    room_id=4,
                    output_date=date(2025, 9, 1),
                    timeslot_id=10,
                    start_minute=540,
                    end_minute=600,
                    duration_minutes=60,
                    module_sequence_index=1,
                    availability_score=1,
                    source="provisional",
                ),
            ),
            blockers=(),
            projected_completion_date=date(2025, 9, 1),
            required_minutes=60,
            scheduled_minutes=60,
        ),
    )

    result = await CompleteGenerationEngine().generate(_context(snapshot))

    assert isinstance(result, ValidatedGenerationResult)
    assert result.metrics["near_optimizer_status"] == "search_exhausted"
    assert result.metrics["quality_optimization_complete"] is False


async def test_complete_engine_fills_from_school_start_when_near_search_exhausts(monkeypatch):
    snapshot = _snapshot()
    snapshot["lunch_rules"] = None
    snapshot["module_accounting"] = [
        {"id": 7, "subject_id": 2, "required_minutes": 60, "sequence": 1}
    ]

    monkeypatch.setattr(
        "app.services.scheduler_complete_engine.NearFutureOptimizer.optimize",
        lambda *_args, **_kwargs: NearFutureResult((), "search_exhausted", 0, 1, {}),
    )

    result = await CompleteGenerationEngine().generate(_context(snapshot))

    assert isinstance(result, ValidatedGenerationResult)
    assert result.blocks[0].date == date.fromisoformat(snapshot["start_date"])


async def test_complete_engine_surfaces_near_model_validation_failure(monkeypatch):
    snapshot = _snapshot()
    snapshot["module_accounting"] = [
        {"id": 7, "subject_id": 2, "required_minutes": 60, "sequence": 1}
    ]
    monkeypatch.setattr(
        "app.services.scheduler_complete_engine.NearFutureOptimizer.optimize",
        lambda *_args, **_kwargs: NearFutureResult(
            (), "system_validation_failure", 0, 1, {"solver_status": "MODEL_INVALID"}
        ),
    )

    result = await CompleteGenerationEngine().generate(_context(snapshot))

    assert isinstance(result, NoValidGenerationOutput)
    assert result.metrics["near_optimizer_status"] == "system_validation_failure"
    assert "system validation" in result.blockers[0]
