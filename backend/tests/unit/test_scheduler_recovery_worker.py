from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

import app.scheduler_recovery_worker as recovery_worker
from app import models
from app.services.scheduler_job_service import SchedulerJobService


class FakeResult:
    def scalars(self):
        return iter([11, 22])


class FakeSession:
    def __init__(self):
        self.organization_id = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def execute(self, _statement):
        return FakeResult()


class FakeSessionLocal:
    @classmethod
    def begin(cls):
        return FakeSession()

    def __new__(cls):
        return FakeSession()


@pytest.mark.asyncio
async def test_run_once_discovers_organizations_and_recovers_each_tenant(monkeypatch):
    contexts = []

    async def set_context(db, organization_id):
        db.organization_id = organization_id
        contexts.append(organization_id)

    class FakeService:
        def __init__(self, db):
            self.db = db

        async def recover_stale_jobs(self, organization_id):
            return {"dispatch_stalled": 0, "worker_stalled": organization_id == 11, "canceled": 0}

    monkeypatch.setattr(recovery_worker, "SessionLocal", FakeSessionLocal)
    monkeypatch.setattr(recovery_worker, "set_async_tenant_context", set_context)
    monkeypatch.setattr(recovery_worker, "SchedulerJobService", FakeService)

    assert await recovery_worker._run_once() == {
        "organizations_processed": 2,
        "dispatch_stalled": 0,
        "worker_stalled": 1,
        "canceled": 0,
    }
    assert contexts == [11, 22]


def test_task_entrypoint_runs_async_recovery(monkeypatch):
    called = {}

    def fake_run(coroutine):
        called["was_coroutine"] = hasattr(coroutine, "close")
        coroutine.close()
        return {"organizations_processed": 0}

    monkeypatch.setattr(recovery_worker.asyncio, "run", fake_run)
    assert recovery_worker.run_stale_job_recovery_task() == {"organizations_processed": 0}
    assert called["was_coroutine"] is True


@pytest.mark.asyncio
async def test_recovery_only_finalizes_expired_running_and_old_cancellation(monkeypatch):
    now = datetime(2026, 9, 12, tzinfo=UTC)

    def job(job_id, status, **values):
        return SimpleNamespace(
            id=job_id,
            organization_id=7,
            school_year_id=1,
            job_status=status,
            queued_at=values.get("queued_at", now - timedelta(minutes=10)),
            started_at=values.get("started_at"),
            deadline_at=values.get("deadline_at"),
            cancellation_requested_at=values.get("cancellation_requested_at"),
            failure_code=None,
            failure_message=None,
            failure_reference=None,
            finished_at=None,
            duration_ms=None,
        )

    queued = job(1, models.ScheduleGenerationJobStatus.QUEUED)
    running_fresh = job(2, models.ScheduleGenerationJobStatus.RUNNING, deadline_at=now)
    running_stale = job(
        3,
        models.ScheduleGenerationJobStatus.RUNNING,
        started_at=now - timedelta(minutes=4),
        deadline_at=now - timedelta(seconds=31),
    )
    cancel_stale = job(
        4,
        models.ScheduleGenerationJobStatus.CANCEL_REQUESTED,
        started_at=now - timedelta(minutes=4),
        cancellation_requested_at=now - timedelta(minutes=2, seconds=1),
    )

    class FakeDb:
        async def scalars(self, statement):
            self.statement = statement
            return [running_stale, cancel_stale]

        async def flush(self):
            return None

    events = []
    monkeypatch.setattr(
        "app.services.scheduler_job_service.emit_scheduler_job_event",
        lambda event, recovered_job: events.append((event, recovered_job.id)),
    )
    db = FakeDb()
    result = await SchedulerJobService(db).recover_stale_jobs(7, now=now)

    assert result == {"dispatch_stalled": 0, "worker_stalled": 1, "canceled": 1}
    assert "schedule_generation_job.queued_at <=" not in str(db.statement)
    assert queued.job_status == models.ScheduleGenerationJobStatus.QUEUED
    assert running_fresh.job_status == models.ScheduleGenerationJobStatus.RUNNING
    assert running_stale.failure_code == "WORKER_STALLED"
    assert cancel_stale.job_status == models.ScheduleGenerationJobStatus.CANCELED
    assert events == [("generation_worker_stalled", 3), ("generation_canceled", 4)]
