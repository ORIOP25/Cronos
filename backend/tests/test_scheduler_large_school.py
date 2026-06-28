import asyncio
from datetime import date, datetime, timedelta, timezone
from time import monotonic

import pytest

from app import models
from app.services.scheduler_candidates import CandidateUniverse, CandidateUniverseBuilder
from app.services.scheduler_complete_demand import CompleteDemandLedgerBuilder
from app.services.scheduler_complete_engine import CompleteGenerationEngine
from app.services.scheduler_job_runtime import GenerationExecutionContext, NoValidGenerationOutput
from tests.scheduler_golden_fixtures import large_scheduler_fixture


def test_large_school_candidate_generation_stops_at_bounded_effort():
    fixture = large_scheduler_fixture()
    ledger = CompleteDemandLedgerBuilder().build(fixture.snapshot)
    started = monotonic()

    universe = CandidateUniverseBuilder().build(
        fixture.snapshot,
        ledger,
        window_start=date.fromisoformat(fixture.snapshot["start_date"]),
        window_end=date.fromisoformat(fixture.snapshot["hard_end_date"]),
        deadline_at=datetime.now(timezone.utc) + timedelta(seconds=2),
        max_candidates=5_000,
    )

    assert monotonic() - started < 5
    assert universe.is_usable is False
    assert any(
        marker in blocker
        for blocker in universe.blockers
        for marker in ("safe solve-size limit", "time budget")
    )


@pytest.mark.asyncio
async def test_large_school_complete_engine_never_requests_all_year_optimization(
    monkeypatch,
):
    fixture = large_scheduler_fixture()
    now = datetime.now(timezone.utc)
    captured = {}

    def bounded_build(_builder, _snapshot, _ledger, **kwargs):
        captured.update(kwargs)
        return CandidateUniverse(
            candidates=(),
            blockers=("Controlled bounded large-school failure.",),
            removed_by_reason={},
        )

    monkeypatch.setattr(CandidateUniverseBuilder, "build", bounded_build)
    context = GenerationExecutionContext(
        job_id=1,
        organization_id=1,
        school_year_id=1,
        strategy=models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
        trigger_type=models.ScheduleGenerationTrigger.FIRST_GENERATION,
        immutable_snapshot={"generation_input": fixture.snapshot},
        started_at=now,
        deadline_at=now + timedelta(minutes=5),
    )

    result = await asyncio.wait_for(
        CompleteGenerationEngine().generate(context),
        timeout=5,
    )

    assert isinstance(result, NoValidGenerationOutput)
    requested_days = (captured["window_end"] - captured["window_start"]).days + 1
    school_year_days = (
        date.fromisoformat(fixture.snapshot["hard_end_date"])
        - date.fromisoformat(fixture.snapshot["start_date"])
    ).days + 1
    assert requested_days <= 84
    assert requested_days < school_year_days
    assert captured["deadline_at"] == context.solve_deadline_at
