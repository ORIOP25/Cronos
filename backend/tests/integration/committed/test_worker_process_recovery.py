"""W11: a real broker message and an owned worker process recover abandoned attempts.

The worker runs as a separate process with a unique queue so the real Celery
message path is exercised without touching any shared runtime resources.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.celery_worker import celery_app
from app.db.tenant import set_async_tenant_context
from app.scheduler.infrastructure.jobs import (
    claim_next_job,
    enqueue_generation,
    release_executor_lock,
    try_acquire_executor_lock,
)
from app.scheduler.infrastructure.models import SchedulerJobV1, SchedulerProposalV1
from tests._support.db_fixtures import (
    TestingSessionLocal,
    runtime_test_engine,
    test_engine,
)
from tests._support.scheduler_v1 import seed_generatable_school

pytestmark = pytest.mark.postgresql

BACKEND = Path(__file__).resolve().parents[3]
QUEUE = f"w11-recovery-{uuid.uuid4().hex}"
TASK = "scheduler.v1.run_next_job"
MOMENT = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)


def _owned_worker() -> subprocess.Popen:
    environment = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            filter(None, [str(BACKEND), os.environ.get("PYTHONPATH", "")])
        ),
        # The isolated worker must observe the same per-worker database.
        "DATABASE_URL": runtime_test_engine.url.render_as_string(hide_password=False),
        "SCHEDULER_V1_ABANDONED_SECONDS": "1",
        "SCHEDULER_V1_HEARTBEAT_SECONDS": "0.5",
    }
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "app.celery_worker.celery_app",
            "worker",
            "--include=app.scheduler_v1_worker",
            "--pool=solo",
            "--concurrency=1",
            "--loglevel=warning",
            "--without-gossip",
            "--without-mingle",
            "--without-heartbeat",
            f"--queues={QUEUE}",
            f"--hostname=w11-{os.getpid()}@%h",
        ],
        cwd=BACKEND,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def _stop_worker(worker: subprocess.Popen) -> None:
    if worker.poll() is None:
        worker.terminate()
        try:
            worker.wait(timeout=30)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait(timeout=30)


def _worker_output(worker: subprocess.Popen) -> str:
    if worker.stdout is None:
        return ""
    if worker.poll() is None:
        return "(worker still running)"
    return worker.stdout.read().decode("utf-8", "replace")[-4000:]


async def _wait_for_status(
    organization_id: int, job_id: int, terminal: set[str], worker: subprocess.Popen
) -> SchedulerJobV1:
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        async with TestingSessionLocal() as observer:
            await set_async_tenant_context(observer, organization_id)
            job = await observer.get(SchedulerJobV1, job_id)
            if job is not None and job.status in terminal:
                return job
        if worker.poll() is not None:
            raise AssertionError(
                f"Owned worker exited early with {worker.returncode}:\n{_worker_output(worker)}"
            )
        await asyncio.sleep(0.5)
    raise AssertionError(f"Job {job_id} did not reach {terminal}:\n{_worker_output(worker)}")


async def _proposal_count(organization_id: int, job_id: int) -> int:
    async with TestingSessionLocal() as observer:
        await set_async_tenant_context(observer, organization_id)
        return int(
            await observer.scalar(
                select(func.count())
                .select_from(SchedulerProposalV1)
                .where(SchedulerProposalV1.job_id == job_id)
            )
        )


async def test_an_owned_worker_recovers_a_stalled_attempt_and_never_duplicates_delivery(
    db_session,
):
    abandoned = await seed_generatable_school(
        db_session, clerk_user_id="w11_abandoned", clerk_org_id="w11_org_abandoned"
    )
    abandoned_job = await enqueue_generation(
        db_session,
        abandoned.organization.id,
        idempotency_key="w11-abandoned",
        requested_by_membership_id=abandoned.membership.id,
        now_utc=MOMENT,
    )
    await db_session.commit()

    lock = await try_acquire_executor_lock(test_engine)
    assert lock is not None
    try:
        claim = await claim_next_job(db_session, now_utc=MOMENT)
        assert claim is not None and claim.job_id == abandoned_job.job.id
    finally:
        await release_executor_lock(lock)
    stalled = await db_session.get(SchedulerJobV1, abandoned_job.job.id)
    stalled.heartbeat_at = datetime.now(UTC) - timedelta(minutes=10)
    await db_session.commit()

    worker = _owned_worker()
    try:
        celery_app.send_task(TASK, queue=QUEUE)
        recovered = await _wait_for_status(
            abandoned.organization.id, abandoned_job.job.id, {"FAILED"}, worker
        )
        assert recovered.result_code == "WORKER_STALLED"
        assert await _proposal_count(abandoned.organization.id, abandoned_job.job.id) == 0

        completed = await seed_generatable_school(
            db_session, clerk_user_id="w11_completed", clerk_org_id="w11_org_completed"
        )
        completed_job = await enqueue_generation(
            db_session,
            completed.organization.id,
            idempotency_key="w11-completed",
            requested_by_membership_id=completed.membership.id,
            now_utc=MOMENT,
        )
        await db_session.commit()

        celery_app.send_task(TASK, queue=QUEUE)
        celery_app.send_task(TASK, queue=QUEUE)
        succeeded = await _wait_for_status(
            completed.organization.id, completed_job.job.id, {"SUCCEEDED"}, worker
        )
        assert succeeded.result_code in (None, "COMPLETE")
        assert await _proposal_count(completed.organization.id, completed_job.job.id) == 1

        celery_app.send_task(TASK, queue=QUEUE)
        await asyncio.sleep(3)
        assert await _proposal_count(completed.organization.id, completed_job.job.id) == 1
    finally:
        _stop_worker(worker)
