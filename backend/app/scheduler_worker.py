from __future__ import annotations

import asyncio

from app.celery_worker import celery_app
from app.db.database import SessionLocal, engine_async
from app.services.scheduler_job_runtime import (
    GenerationExecutionContext,
    NoValidGenerationOutput,
    SchedulerJobRuntime,
    ValidatedGenerationResult,
)
from app.services.scheduler_complete_engine import run_complete_generation
from app.services.scheduler_adaptive_engine import run_adaptive_repair


async def _generation_engine(
    context: GenerationExecutionContext,
) -> ValidatedGenerationResult | NoValidGenerationOutput:
    if context.strategy.value == "ADAPTIVE_REPAIR":
        return await run_adaptive_repair(context)
    return await run_complete_generation(context)


async def _run_job(job_id: int) -> dict[str, object]:
    try:
        async with SessionLocal() as db:
            job = await SchedulerJobRuntime(db).execute(
                job_id,
                _generation_engine,
            )
            return {
                "job_id": job.id,
                "status": job.job_status.value,
                "failure_code": job.failure_code,
            }
    finally:
        # Celery invokes asyncio.run per task; pooled asyncpg connections cannot
        # be carried into the next task's event loop.
        await engine_async.dispose()


@celery_app.task(name="scheduler.run_generation_job")
def run_schedule_generation_job_task(job_id: int) -> dict[str, object]:
    return asyncio.run(_run_job(job_id))
