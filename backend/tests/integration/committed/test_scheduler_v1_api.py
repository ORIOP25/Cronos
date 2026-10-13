"""W09 API contracts: idempotent generation, dispatch durability and reads."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url

from app import models
from app.api import deps
from app.main import app
from app.scheduler.infrastructure.models import SchedulerJobV1
from tests._support.scheduler_v1 import seed_generatable_school

pytestmark = pytest.mark.postgresql

ADMIN = "v1_api_admin"
ORG = "v1_api_org"
HEADERS = {"Authorization": f"Bearer {ADMIN}"}


@pytest.fixture
def dispatched_tasks():
    calls = []

    class RecordingDispatcher:
        def dispatch(self, *, organization_id, job_id, task_id):
            calls.append((organization_id, job_id, task_id))

    app.dependency_overrides[deps.get_scheduler_task_dispatcher] = RecordingDispatcher
    try:
        yield calls
    finally:
        app.dependency_overrides.pop(deps.get_scheduler_task_dispatcher, None)


async def _configured_school(db_session):
    seed = await seed_generatable_school(db_session, clerk_user_id=ADMIN, clerk_org_id=ORG)
    await db_session.commit()
    return seed


async def test_generate_returns_202_and_dispatches_once(async_client, db_session, dispatched_tasks):
    seed = await _configured_school(db_session)

    response = await async_client.post(
        "/api/v1/scheduler/generate",
        json={"idempotency_key": "click-1", "expected_input_revision": 0},
        headers=HEADERS,
    )

    assert response.status_code == 202
    payload = response.json()["job"]
    assert payload["status"] == "QUEUED"
    assert payload["strategy"] == "COMPLETE_GENERATION"
    assert payload["queue_position"] == 1
    assert dispatched_tasks == [
        (seed.organization.id, payload["id"], f"scheduler-v1-job-{payload['id']}")
    ]


async def test_generate_is_idempotent_for_the_same_click(
    async_client, db_session, dispatched_tasks
):
    await _configured_school(db_session)
    body = {"idempotency_key": "same-click", "expected_input_revision": 0}

    first = await async_client.post("/api/v1/scheduler/generate", json=body, headers=HEADERS)
    retry = await async_client.post("/api/v1/scheduler/generate", json=body, headers=HEADERS)

    assert first.status_code == retry.status_code == 202
    job_id = first.json()["job"]["id"]
    assert retry.json()["job"]["id"] == job_id
    # A duplicate delivery may wake the executor again; only one job exists.
    assert {call[1] for call in dispatched_tasks} == {job_id}
    jobs = (await db_session.scalars(select(SchedulerJobV1))).all()
    assert len(jobs) == 1


async def test_generate_commits_the_job_before_dispatching(async_client, db_session):
    await _configured_school(db_session)
    sync_url = make_url(os.environ["TEST_DATABASE_URL"]).set(drivername="postgresql+psycopg2")
    independent_engine = create_engine(sync_url.render_as_string(hide_password=False))
    observed = {}

    class IndependentSessionDispatcher:
        def dispatch(self, *, organization_id, job_id, task_id):
            with independent_engine.begin() as connection:
                connection.execute(
                    text(
                        "SELECT set_config('app.current_organization_id', :organization_id, true)"
                    ),
                    {"organization_id": str(organization_id)},
                )
                observed["job_id"] = connection.scalar(
                    text("SELECT id FROM scheduler_job_v1 WHERE id = :job_id"),
                    {"job_id": job_id},
                )
                observed["status"] = connection.scalar(
                    text("SELECT status FROM scheduler_job_v1 WHERE id = :job_id"),
                    {"job_id": job_id},
                )
                observed["task_id"] = task_id

    app.dependency_overrides[deps.get_scheduler_task_dispatcher] = IndependentSessionDispatcher
    try:
        response = await async_client.post(
            "/api/v1/scheduler/generate",
            json={"idempotency_key": "commit-first", "expected_input_revision": 0},
            headers=HEADERS,
        )
    finally:
        app.dependency_overrides.pop(deps.get_scheduler_task_dispatcher, None)
        independent_engine.dispose()

    assert response.status_code == 202
    job_id = response.json()["job"]["id"]
    assert observed == {
        "job_id": job_id,
        "status": "QUEUED",
        "task_id": f"scheduler-v1-job-{job_id}",
    }


async def test_a_dispatch_failure_keeps_the_request_recoverable(async_client, db_session):
    await _configured_school(db_session)

    class FailingDispatcher:
        def dispatch(self, **_kwargs):
            raise RuntimeError("broker unavailable")

    app.dependency_overrides[deps.get_scheduler_task_dispatcher] = FailingDispatcher
    try:
        response = await async_client.post(
            "/api/v1/scheduler/generate",
            json={"idempotency_key": "dispatch-fails", "expected_input_revision": 0},
            headers=HEADERS,
        )
    finally:
        app.dependency_overrides.pop(deps.get_scheduler_task_dispatcher, None)

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "generation_dispatch_failed"
    job = await db_session.scalar(select(SchedulerJobV1).order_by(SchedulerJobV1.id.desc()))
    assert job is not None
    assert job.status == "QUEUED"


async def test_generate_conflicts_with_a_stale_revision(async_client, db_session):
    await _configured_school(db_session)
    response = await async_client.post(
        "/api/v1/scheduler/generate",
        json={"idempotency_key": "stale-revision", "expected_input_revision": 99},
        headers=HEADERS,
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "scheduler_state_changed"


async def test_generate_rejects_incompatible_room_without_dispatching(
    async_client, db_session, dispatched_tasks
):
    seed = await _configured_school(db_session)
    seed.room.capacity = 10
    await db_session.commit()

    response = await async_client.post(
        "/api/v1/scheduler/generate",
        json={"idempotency_key": "room-block", "expected_input_revision": 0},
        headers=HEADERS,
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "NO_ELIGIBLE_ROOM"
    assert detail["retryable"] is False
    assert detail["support_required"] is False
    assert detail["context"]["room_issues"] == [
        {
            "class_id": seed.class_.id,
            "class_name": "A",
            "subject_id": seed.subject.id,
            "subject_name": "Subject",
            "required_room_type": "normal",
            "required_capacity": 20,
            "max_available_capacity": 10,
            "reason": "INSUFFICIENT_CAPACITY",
        }
    ]
    assert dispatched_tasks == []
    jobs = (await db_session.scalars(select(SchedulerJobV1))).all()
    assert jobs == []


async def test_generate_without_a_reason_conflicts(async_client, db_session, monkeypatch):
    seed = await _configured_school(db_session)
    state = await db_session.scalar(
        select(models.SchedulerSchoolYearState).where(
            models.SchedulerSchoolYearState.organization_id == seed.organization.id
        )
    )
    state.last_completed_planning_revision = state.planning_revision
    state.last_successful_generation_at = datetime.now(UTC)
    await db_session.commit()

    response = await async_client.post(
        "/api/v1/scheduler/generate",
        json={"idempotency_key": "no-reason", "expected_input_revision": 0},
        headers=HEADERS,
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "no_generation_reason"


async def test_cancel_is_idempotent_and_get_does_not_write(
    async_client, db_session, dispatched_tasks
):
    await _configured_school(db_session)
    created = await async_client.post(
        "/api/v1/scheduler/generate",
        json={"idempotency_key": "cancel-me", "expected_input_revision": 0},
        headers=HEADERS,
    )
    job_id = created.json()["job"]["id"]

    first = await async_client.post(f"/api/v1/scheduler/jobs/{job_id}/cancel", headers=HEADERS)
    second = await async_client.post(f"/api/v1/scheduler/jobs/{job_id}/cancel", headers=HEADERS)
    assert first.status_code == second.status_code == 200
    assert first.json()["job"]["status"] == "CANCELLED"
    assert second.json()["job"]["status"] == "CANCELLED"

    state_before = await db_session.scalar(select(models.SchedulerSchoolYearState.input_revision))
    read = await async_client.get("/api/v1/scheduler/status", headers=HEADERS)
    assert read.status_code == 200
    state_after = await db_session.scalar(select(models.SchedulerSchoolYearState.input_revision))
    assert state_before == state_after


async def test_pending_proposal_diff_and_approval_through_the_api(
    async_client, db_session, monkeypatch
):
    from tests._support.db_fixtures import TestingSessionLocal, test_engine

    seed = await _configured_school(db_session)
    from app.scheduler.infrastructure.jobs import enqueue_generation

    await enqueue_generation(
        db_session,
        seed.organization.id,
        idempotency_key="api-proposal",
        requested_by_membership_id=seed.membership.id,
        now_utc=datetime(2026, 9, 1, 8, 0, tzinfo=UTC),
    )
    from app import scheduler_v1_worker as worker

    monkeypatch.setattr(worker, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(worker, "engine_async", test_engine)
    monkeypatch.setattr(worker, "_now", lambda: datetime(2026, 9, 1, 8, 0, tzinfo=UTC))
    monkeypatch.setattr(worker, "RECOVERY_ASSESSMENT_SECONDS", 0.0)
    monkeypatch.setattr(
        "app.api.v1.endpoints.scheduler._now",
        lambda: datetime(2026, 9, 1, 8, 0, tzinfo=UTC),
    )
    await worker.process_next_jobs()

    current = await async_client.get("/api/v1/scheduler/drafts/current", headers=HEADERS)
    assert current.status_code == 200
    proposal_id = current.json()["proposal_id"]
    assert current.json()["can_approve"] is True

    diff = await async_client.get(f"/api/v1/scheduler/drafts/{proposal_id}/diff", headers=HEADERS)
    assert diff.status_code == 200
    payload = diff.json()
    assert payload["is_first_generation"] is True
    assert payload["counts"]["added"] >= 1
    assert payload["physical"] and payload["modular"] == []

    from app.scheduler.infrastructure.models import SchedulerProposalV1

    proposal = await db_session.get(SchedulerProposalV1, proposal_id)
    assert proposal.status == "PENDING"
    foreign = await seed_generatable_school(
        db_session, clerk_user_id="foreign_proposal_admin", clerk_org_id="foreign_proposal_org"
    )
    await db_session.commit()
    denied_foreign = await async_client.get(
        f"/api/v1/scheduler/drafts/{proposal_id}/diff",
        headers={"Authorization": "Bearer foreign_proposal_admin"},
    )
    assert foreign.organization.id != seed.organization.id
    assert denied_foreign.status_code == 404
    assert denied_foreign.json()["detail"]["code"] == "scheduler_draft_not_found"

    stale_client = await async_client.post(
        f"/api/v1/scheduler/drafts/{proposal_id}/approve",
        json={"expected_input_revision": 999},
        headers=HEADERS,
    )
    assert stale_client.status_code == 409
    assert stale_client.json()["detail"]["code"] == "scheduler_state_changed"
    still_current = await async_client.get("/api/v1/scheduler/drafts/current", headers=HEADERS)
    assert still_current.status_code == 200
    assert still_current.json()["status"] == "PENDING"

    approved = await async_client.post(
        f"/api/v1/scheduler/drafts/{proposal_id}/approve",
        json={"expected_input_revision": 0},
        headers=HEADERS,
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"

    status = await async_client.get("/api/v1/scheduler/status", headers=HEADERS)
    assert status.status_code == 200
    assert status.json()["publication_state"] == "PUBLISHED"
    assert status.json()["active_proposal_id"] == proposal_id
    assert status.json()["default_strategy"] == "ADAPTIVE_RECOVERY"


async def test_job_and_proposal_reads_return_not_found_for_the_wrong_id(async_client, db_session):
    await _configured_school(db_session)
    missing_job = await async_client.get("/api/v1/scheduler/jobs/999999", headers=HEADERS)
    missing_diff = await async_client.get("/api/v1/scheduler/drafts/999999/diff", headers=HEADERS)
    assert missing_job.status_code == 404
    assert missing_diff.status_code == 404
