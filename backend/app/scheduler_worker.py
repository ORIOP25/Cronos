from __future__ import annotations

import asyncio

from app.celery_worker import celery_app
from app.db.database import SessionLocal
from app.db.tenant import set_async_tenant_context
from app.services.scheduler_adaptive_engine import run_adaptive_repair
from app.services.scheduler_complete_engine import run_complete_generation
from app.services.scheduler_job_runtime import (
    GenerationExecutionContext,
    NoValidGenerationOutput,
    SchedulerJobRuntime,
    ValidatedGenerationResult,
)


async def _generation_engine(
    context: GenerationExecutionContext,
) -> ValidatedGenerationResult | NoValidGenerationOutput:
    if context.strategy.value in {"ADAPTIVE_REPAIR", "GRID_CHANGE"}:
        return await run_adaptive_repair(context)
    return await run_complete_generation(context)


async def _run_job(organization_id: int, job_id: int) -> dict[str, object]:
    async with SessionLocal() as db:
        await set_async_tenant_context(db, organization_id)
        job = await SchedulerJobRuntime(db, session_factory=SessionLocal).execute(
            job_id,
            _generation_engine,
            organization_id=organization_id,
        )
        return {
            "job_id": job.id,
            "status": job.job_status.value,
            "failure_code": job.failure_code,
        }


@celery_app.task(name="scheduler.run_generation_job")
def run_schedule_generation_job_task(organization_id: int, job_id: int) -> dict[str, object]:
    return asyncio.run(_run_job(organization_id, job_id))
