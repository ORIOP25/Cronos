"""W11: real broker messages and owned worker processes prove recovery.

The genuine process-loss proof runs the solving worker as a real Celery
subprocess on a unique broker queue. The test kills only that owned process
while its persistence transaction waits on a test-only PostgreSQL lock. A
separate real supervisor subprocess then consumes the actual
``scheduler.v1.supervise`` message and marks the abandoned attempt
``WORKER_STALLED``. The duplicate-delivery proof stays as a real broker
redelivery that must not create a second proposal.
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url

from app.celery_worker import celery_app
from app.db.tenant import set_async_tenant_context
from app.scheduler.infrastructure.jobs import enqueue_generation
from app.scheduler.infrastructure.models import (
    SchedulerJobV1,
    SchedulerLessonLogV1,
    SchedulerLessonV1,
    SchedulerProposalV1,
    SchedulerVersionV1,
)
from tests._support.db_fixtures import (
    RuntimeTestingSessionLocal,
    TestingSessionLocal,
    runtime_test_engine,
)
from tests._support.scheduler_v1 import seed_generatable_school
from tests.db import validated_test_database_url

pytestmark = pytest.mark.postgresql

BACKEND = Path(__file__).resolve().parents[3]
RUN_TASK = "scheduler.v1.run_next_job"
SUPERVISE_TASK = "scheduler.v1.supervise"
SOLVE_INCLUDE = "app.scheduler_v1_worker"
SUPERVISE_INCLUDE = "app.scheduler_recovery_worker"
MOMENT = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
ABANDONED_SECONDS = 1
HEARTBEAT_SECONDS = 0.5
WAIT_SECONDS = 180.0
OWNED_BROKER_SCHEMES = {"redis", "rediss"}
OWNED_BROKER_HOSTS = {"redis", "127.0.0.1", "localhost"}
PASSWORD_IN_URL = re.compile(
    r"((?:postgres(?:ql)?|redis)(?:\+[^:]+)?://[^:\s/@]+:)[^@\s]+@",
    re.IGNORECASE,
)
STATE_LOCK_SQL = text(
    "SELECT id FROM scheduler_school_year_state "
    "WHERE organization_id = :organization_id AND school_year_id = :school_year_id "
    "FOR UPDATE"
)
PERSISTENCE_WAIT_SQL = text(
    "SELECT EXISTS ("
    "SELECT 1 FROM pg_stat_activity "
    "WHERE datname = current_database() "
    "AND wait_event_type = 'Lock' "
    "AND (CAST(:holder_pid AS integer)) = ANY(pg_blocking_pids(pid)) "
    "AND query ILIKE '%scheduler_school_year_state%'"
    ")"
)


def _unique_queue(label: str) -> str:
    return f"w11-{label}-{uuid.uuid4().hex}"


def _worker_database_url() -> str:
    """The owned subprocess may only reach the xdist runtime test database."""
    return _validate_worker_database_url(
        runtime_test_engine.url.render_as_string(hide_password=False)
    )


def _validate_worker_database_url(value: str) -> str:
    """Accept only the exact test database names the runner owns."""
    return validated_test_database_url(value)


def _validate_owned_broker(broker: str) -> str:
    """Accept only a redis/rediss loopback or owned test-stack broker."""
    url = make_url(broker)
    if url.drivername not in OWNED_BROKER_SCHEMES:
        raise RuntimeError(f"Refusing a non-redis test broker scheme: {url.drivername!r}")
    if url.host not in OWNED_BROKER_HOSTS:
        raise RuntimeError(f"Refusing a foreign test broker host: {url.host!r}")
    return broker


def _owned_broker_url() -> str:
    """The owned subprocess may only reach a redis/rediss loopback or test-stack broker."""
    broker = os.environ.get("CELERY_BROKER_URL") or os.environ.get("REDIS_URL")
    if not broker:
        raise RuntimeError("The owned test broker is not configured.")
    return _validate_owned_broker(broker)


def _owned_process(queue: str, include: str, *, loglevel: str = "warning") -> subprocess.Popen:
    environment = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            filter(None, [str(BACKEND), os.environ.get("PYTHONPATH", "")])
        ),
        # The isolated processes must observe the xdist runtime database and the
        # owned test broker, never the runner base database or a shared broker.
        "DATABASE_URL": _worker_database_url(),
        "CELERY_BROKER_URL": _owned_broker_url(),
        "SCHEDULER_V1_ABANDONED_SECONDS": str(ABANDONED_SECONDS),
        "SCHEDULER_V1_HEARTBEAT_SECONDS": str(HEARTBEAT_SECONDS),
    }
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "app.celery_worker.celery_app",
            "worker",
            f"--include={include}",
            "--pool=solo",
            "--concurrency=1",
            f"--loglevel={loglevel}",
            "--without-gossip",
            "--without-mingle",
            "--without-heartbeat",
            f"--queues={queue}",
            f"--hostname=w11-{uuid.uuid4().hex[:8]}@%h",
        ],
        cwd=BACKEND,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def _sanitize(value: str) -> str:
    return PASSWORD_IN_URL.sub(r"\1[redacted]@", value)


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=30)


def _stop_and_read(process: subprocess.Popen) -> str:
    _stop(process)
    return _output(process)


def _output(process: subprocess.Popen) -> str:
    if process.stdout is None:
        return ""
    if process.poll() is None:
        return "(process still running)"
    return _sanitize(process.stdout.read().decode("utf-8", "replace")[-8000:])


async def _wait_for_status(
    organization_id: int,
    job_id: int,
    terminal: set[str],
    *,
    processes: tuple[subprocess.Popen, ...] = (),
    timeout: float = WAIT_SECONDS,
) -> SchedulerJobV1:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        async with TestingSessionLocal() as observer:
            await set_async_tenant_context(observer, organization_id)
            job = await observer.get(SchedulerJobV1, job_id)
            if job is not None and job.status in terminal:
                return job
        for process in processes:
            if process.poll() is not None:
                raise AssertionError(
                    f"Owned process exited early with {process.returncode}:\n{_output(process)}"
                )
        await asyncio.sleep(0.5)
    details = "\n".join(_output(process) for process in processes)
    raise AssertionError(f"Job {job_id} did not reach {terminal}:\n{details}")


async def _count(organization_id: int, model, *conditions) -> int:
    async with TestingSessionLocal() as observer:
        await set_async_tenant_context(observer, organization_id)
        return int(
            await observer.scalar(select(func.count()).select_from(model).where(*conditions))
        )


async def _proposal_count(organization_id: int, job_id: int) -> int:
    return await _count(organization_id, SchedulerProposalV1, SchedulerProposalV1.job_id == job_id)


async def _version_count(organization_id: int, school_year_id: int) -> int:
    return await _count(
        organization_id, SchedulerVersionV1, SchedulerVersionV1.school_year_id == school_year_id
    )


async def _lesson_count(organization_id: int, school_year_id: int) -> int:
    return await _count(
        organization_id, SchedulerLessonV1, SchedulerLessonV1.school_year_id == school_year_id
    )


async def _lesson_log_count(organization_id: int, school_year_id: int) -> int:
    return await _count(
        organization_id,
        SchedulerLessonLogV1,
        SchedulerLessonLogV1.school_year_id == school_year_id,
    )


async def _lock_state_row(organization_id: int, school_year_id: int) -> tuple[object, int]:
    """Hold the persist-time row lock and return it with the holder backend PID."""
    session = RuntimeTestingSessionLocal()
    try:
        await set_async_tenant_context(session, organization_id)
        holder_pid = int(await session.scalar(text("SELECT pg_backend_pid()")))
        await session.execute(
            STATE_LOCK_SQL,
            {"organization_id": organization_id, "school_year_id": school_year_id},
        )
    except BaseException:
        await session.close()
        raise
    return session, holder_pid


async def _release_lock(session) -> None:
    try:
        await session.rollback()
    finally:
        await session.close()


async def _wait_for_persistence_lock(holder_pid: int, *, timeout: float = WAIT_SECONDS) -> None:
    """Wait until a worker backend is blocked by our own row-lock backend."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        async with RuntimeTestingSessionLocal() as observer:
            waiting = await observer.scalar(PERSISTENCE_WAIT_SQL, {"holder_pid": holder_pid})
        if waiting:
            return
        await asyncio.sleep(0.2)
    raise AssertionError("The owned worker never blocked on the owned persistence lock.")


async def _recover_with_supervisor(
    queue: str,
    organization_id: int,
    job_id: int,
    *,
    processes: tuple[subprocess.Popen, ...],
    timeout: float = WAIT_SECONDS,
) -> SchedulerJobV1:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        celery_app.send_task(SUPERVISE_TASK, queue=queue)
        async with TestingSessionLocal() as observer:
            await set_async_tenant_context(observer, organization_id)
            job = await observer.get(SchedulerJobV1, job_id)
            if job is not None and job.status == "FAILED":
                return job
        for process in processes:
            if process.poll() is not None:
                raise AssertionError(
                    f"Owned supervisor exited early with {process.returncode}:\n{_output(process)}"
                )
        await asyncio.sleep(0.5)
    details = "\n".join(_output(process) for process in processes)
    raise AssertionError(f"Job {job_id} was not reconciled by the supervisor:\n{details}")


async def _enqueue(db_session, seed, key: str):
    outcome = await enqueue_generation(
        db_session,
        seed.organization.id,
        idempotency_key=key,
        requested_by_membership_id=seed.membership.id,
        now_utc=MOMENT,
    )
    await db_session.commit()
    return outcome


async def _run_redelivery_with_flush(
    db_session,
    target: tuple[str, str, str],
    flush: tuple[str, str, str],
) -> None:
    """Deliver the target job twice on one owned worker; a flush job orders it.

    Each case is (clerk_user_id, clerk_org_id, idempotency_key). The flush job's
    success proves the duplicate delivery was consumed before it, without a
    sleep. The helper owns one unique queue and one owned process, and always
    stops that process.
    """
    target_user, target_org, target_key = target
    flush_user, flush_org, flush_key = flush
    target_seed = await seed_generatable_school(
        db_session, clerk_user_id=target_user, clerk_org_id=target_org
    )
    target_job = await _enqueue(db_session, target_seed, target_key)
    queue = _unique_queue("redelivery")
    worker = _owned_process(queue, SOLVE_INCLUDE)
    try:
        celery_app.send_task(RUN_TASK, queue=queue)
        celery_app.send_task(RUN_TASK, queue=queue)
        succeeded = await _wait_for_status(
            target_seed.organization.id, target_job.job.id, {"SUCCEEDED"}, processes=(worker,)
        )
        assert succeeded.result_code in (None, "COMPLETE")

        flush_seed = await seed_generatable_school(
            db_session, clerk_user_id=flush_user, clerk_org_id=flush_org
        )
        flush_job = await _enqueue(db_session, flush_seed, flush_key)
        celery_app.send_task(RUN_TASK, queue=queue)
        await _wait_for_status(
            flush_seed.organization.id, flush_job.job.id, {"SUCCEEDED"}, processes=(worker,)
        )

        assert await _proposal_count(target_seed.organization.id, target_job.job.id) == 1
        assert await _proposal_count(flush_seed.organization.id, flush_job.job.id) == 1
    finally:
        _stop(worker)


async def test_an_owned_worker_never_duplicates_delivery_of_a_queued_job(db_session):
    await _run_redelivery_with_flush(
        db_session,
        ("w11_redelivery", "w11_org_redelivery", "w11-redelivery"),
        ("w11_later", "w11_org_later", "w11-later"),
    )


async def test_an_owned_worker_process_loss_is_recovered_by_a_real_supervisor(db_session):
    seed = await seed_generatable_school(
        db_session, clerk_user_id="w11_loss", clerk_org_id="w11_org_loss"
    )
    job = await _enqueue(db_session, seed, "w11-loss")

    solve_queue = _unique_queue("solve")
    supervise_queue = _unique_queue("supervise")
    lock, holder_pid = await _lock_state_row(seed.organization.id, seed.year.id)
    worker = None
    supervisor = None
    try:
        worker = _owned_process(solve_queue, SOLVE_INCLUDE)
        celery_app.send_task(RUN_TASK, queue=solve_queue)

        running = await _wait_for_status(
            seed.organization.id, job.job.id, {"RUNNING"}, processes=(worker,)
        )
        assert running.started_at is not None
        assert running.attempt_token == 2
        await _wait_for_persistence_lock(holder_pid)

        # The owned solving worker is alive and blocked before any commit.
        assert worker.poll() is None
        worker.kill()
        worker.wait(timeout=30)
        assert worker.poll() is not None
        await _release_lock(lock)
        lock = None

        supervisor = _owned_process(supervise_queue, SUPERVISE_INCLUDE, loglevel="info")
        failed = await _recover_with_supervisor(
            supervise_queue,
            seed.organization.id,
            job.job.id,
            processes=(supervisor,),
        )
        assert failed.status == "FAILED"
        assert failed.result_code == "WORKER_STALLED"
        assert failed.finished_at is not None
        assert await _proposal_count(seed.organization.id, job.job.id) == 0
        assert await _version_count(seed.organization.id, seed.year.id) == 0
        assert await _lesson_count(seed.organization.id, seed.year.id) == 0
        assert await _lesson_log_count(seed.organization.id, seed.year.id) == 0

        receipt = _stop_and_read(supervisor)
        supervisor = None
        assert SUPERVISE_TASK in receipt
        assert "received" in receipt

        # A later isolated job succeeds once; its duplicate delivery is flushed
        # by a second job on the same single-threaded queue.
        await _run_redelivery_with_flush(
            db_session,
            ("w11_recovered", "w11_org_recovered", "w11-recovered"),
            ("w11_flush", "w11_org_flush", "w11-flush"),
        )
    finally:
        if worker is not None:
            _stop(worker)
        if supervisor is not None:
            _stop(supervisor)
        if lock is not None:
            await _release_lock(lock)


@pytest.mark.parametrize(
    "broker",
    [
        "amqp://guest:super-secret@localhost:5672//",
        "redis://guest:super-secret@example.com:6379/0",
    ],
)
def test_an_owned_worker_broker_error_never_echoes_credentials(broker):
    with pytest.raises(RuntimeError) as failure:
        _validate_owned_broker(broker)
    assert "super-secret" not in str(failure.value)


def test_an_owned_worker_accepts_the_owned_broker():
    assert _validate_owned_broker("redis://127.0.0.1:6379/0") == "redis://127.0.0.1:6379/0"
    assert _validate_owned_broker("rediss://redis:6379/0") == "rediss://redis:6379/0"


def test_an_owned_worker_rejects_a_foreign_broker():
    with pytest.raises(RuntimeError):
        _validate_owned_broker("amqp://guest:guest@localhost:5672//")
    with pytest.raises(RuntimeError):
        _validate_owned_broker("redis://10.0.0.5:6379/0")


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://cronos_app:super-secret@db:5432/postgres",
        "postgresql+asyncpg://cronos_app:super-secret@db:5432/cronos_db",
        "postgresql+asyncpg://cronos_app:super-secret@db:5432/cronos_test_gw",
    ],
)
def test_an_owned_worker_rejects_an_unowned_database(url):
    with pytest.raises(RuntimeError) as failure:
        _validate_worker_database_url(url)
    assert "super-secret" not in str(failure.value)
