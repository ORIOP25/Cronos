from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import select

from app import models, schemas
from app.api import deps
from app.config import settings as app_settings
from app.main import app
from app.scheduler.infrastructure.jobs import (
    claim_next_job,
    finish_job,
    reconcile_abandoned,
)
from app.scheduler.infrastructure.models import (
    CurricularAssignment,
    CurricularRequirement,
    SchedulerJobV1,
    SchedulerVersionV1,
)
from app.scheduler.infrastructure.proposals import approve_proposal
from app.scheduler.infrastructure.queries import current_proposal
from app.services import grid_change_service, grid_version_service, settings_service
from tests._support.db_fixtures import create_teacher_profile, select_all_subject_modules
from tests._support.scheduler_v1 import V1Seed, add_version, seed_generatable_school

API = app_settings.API_V1_STR


def _bulk(**changes) -> schemas.TimeslotBulkCreate:
    payload = {
        "start_time": "09:00",
        "end_time": "11:45",
        "slot_duration_minutes": 50,
        "break_duration_minutes": 10,
        "break_overrides": [],
        "days_of_week": [0],
    }
    payload.update(changes)
    return schemas.TimeslotBulkCreate(**payload)


async def _published_grid_org(db_session) -> V1Seed:
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="grid-change-admin",
        clerk_org_id="grid-change-org",
    )
    await settings_service.upsert_settings(
        db_session,
        seed.organization.id,
        schemas.OrganizationSettingsUpsert(
            school_start_date=date(2026, 9, 1),
            school_hard_end_date=date(2027, 7, 31),
            preferred_end_date=date(2026, 10, 30),
            repair_stability_window_days=0,
        ),
    )
    await settings_service.save_and_regenerate_grid(
        db_session,
        seed.organization.id,
        schemas.GridConfigurationCommand(
            grid_settings=schemas.OrganizationGridSettingsUpsert(),
            timeslots=_bulk(end_time="10:50"),
        ),
    )
    await add_version(db_session, seed, status="ACTIVE")
    await db_session.flush()
    return seed


async def _propose(db_session, seed, *, decisions=None, key=None, bulk=None):
    payload = bulk or _bulk(break_overrides=[{"after_slot": 2, "duration_minutes": 5}])
    preview = await grid_change_service.preview_grid_change(
        db_session,
        seed.organization.id,
        schemas.GridChangePreviewRequest(timeslots=payload),
    )
    response = await grid_change_service.propose_grid_change(
        db_session,
        seed.organization.id,
        schemas.GridChangeProposeRequest(
            timeslots=payload,
            fingerprint=preview.fingerprint,
            decisions=decisions or [],
            idempotency_key=key,
        ),
        membership_id=seed.membership.id,
    )
    return preview, response


async def _copy_all_affected(preview) -> list[schemas.GridChangeDecision]:
    return [
        schemas.GridChangeDecision(current_timeslot_id=entry.current_timeslot_id, action="COPY")
        for entry in preview.affected_availabilities
    ]


async def test_proposal_creates_pending_version_and_pinned_v1_job(db_session):
    seed = await _published_grid_org(db_session)
    published = await grid_version_service.get_active_grid_version(db_session, seed.organization.id)
    published_blocks = await grid_version_service.get_version_blocks(
        db_session, seed.organization.id, published.id
    )
    published_ids = sorted(block.id for block in published_blocks)
    first_block = published_blocks[0]
    teacher = await create_teacher_profile(db_session, organization_id=seed.organization.id)
    db_session.add(
        models.Availability(
            organization_id=seed.organization.id,
            teacher_id=teacher.id,
            timeslot_id=first_block.id,
            score=models.PreferenceLevel.IMPOSSIBLE.value,
        )
    )
    db_session.add(
        models.Constraint(
            organization_id=seed.organization.id,
            rule_type=models.ConstraintType.teacher_preferred,
            teacher_id=teacher.id,
            timeslot_id=first_block.id,
        )
    )
    await db_session.flush()

    payload = _bulk(break_overrides=[{"after_slot": 2, "duration_minutes": 5}])
    preview = await grid_change_service.preview_grid_change(
        db_session, seed.organization.id, schemas.GridChangePreviewRequest(timeslots=payload)
    )
    _, response = await _propose(
        db_session,
        seed,
        bulk=payload,
        decisions=await _copy_all_affected(preview),
    )

    version = await grid_version_service.get_grid_version(
        db_session, seed.organization.id, response.grid_version_id
    )
    assert version is not None
    assert version.state == models.GridVersionState.PENDING
    assert version.effective_date == preview.first_editable_date
    blocks = await grid_version_service.get_version_blocks(
        db_session, seed.organization.id, version.id
    )
    assert len(blocks) == 3

    job = await db_session.get(SchedulerJobV1, response.job_id)
    assert job is not None
    assert job.grid_version_id == version.id
    assert job.base_version_id is not None

    published_after = await grid_version_service.get_grid_version(
        db_session, seed.organization.id, published.id
    )
    await db_session.refresh(published_after)
    assert published_after.state == models.GridVersionState.ACTIVE
    blocks_after = await grid_version_service.get_version_blocks(
        db_session, seed.organization.id, published.id
    )
    assert sorted(block.id for block in blocks_after) == published_ids

    copied_availability = (
        await db_session.scalars(
            select(models.Availability).where(
                models.Availability.teacher_id == teacher.id,
                models.Availability.timeslot_id.in_({block.id for block in blocks}),
            )
        )
    ).all()
    assert [row.score for row in copied_availability] == [models.PreferenceLevel.IMPOSSIBLE.value]
    copied_constraint = await db_session.scalar(
        select(models.Constraint).where(
            models.Constraint.organization_id == seed.organization.id,
            models.Constraint.timeslot_id.in_({block.id for block in blocks}),
        )
    )
    assert copied_constraint is not None
    assert copied_constraint.rule_type == models.ConstraintType.teacher_preferred


async def test_proposal_requires_decisions_for_moved_associations(db_session):
    seed = await _published_grid_org(db_session)
    published = await grid_version_service.get_active_grid_version(db_session, seed.organization.id)
    block = (
        await grid_version_service.get_version_blocks(
            db_session, seed.organization.id, published.id
        )
    )[0]
    teacher = await create_teacher_profile(db_session, organization_id=seed.organization.id)
    db_session.add(
        models.Availability(
            organization_id=seed.organization.id,
            teacher_id=teacher.id,
            timeslot_id=block.id,
            score=models.PreferenceLevel.IMPOSSIBLE.value,
        )
    )
    await db_session.flush()

    payload = _bulk(slot_duration_minutes=55, break_duration_minutes=5)
    preview = await grid_change_service.preview_grid_change(
        db_session, seed.organization.id, schemas.GridChangePreviewRequest(timeslots=payload)
    )
    assert preview.can_propose is True
    moved = next(
        entry for entry in preview.affected_availabilities if entry.current_timeslot_id == block.id
    )
    assert moved.requires_decision is True

    with pytest.raises(grid_change_service.GridChangeError) as excinfo:
        await grid_change_service.propose_grid_change(
            db_session,
            seed.organization.id,
            schemas.GridChangeProposeRequest(
                timeslots=payload, fingerprint=preview.fingerprint, decisions=[]
            ),
            membership_id=seed.membership.id,
        )
    assert excinfo.value.code == "GRID_CHANGE_DECISION_REQUIRED"
    assert await grid_change_service.pending_grid_change(db_session, seed.organization.id) is None


async def test_proposal_rejects_stale_fingerprint(db_session):
    seed = await _published_grid_org(db_session)

    with pytest.raises(grid_change_service.GridChangeError) as excinfo:
        await grid_change_service.propose_grid_change(
            db_session,
            seed.organization.id,
            schemas.GridChangeProposeRequest(timeslots=_bulk(), fingerprint="0" * 64),
            membership_id=seed.membership.id,
        )
    assert excinfo.value.code == "GRID_CHANGE_STALE"
    assert await grid_change_service.pending_grid_change(db_session, seed.organization.id) is None


async def test_proposal_is_idempotent_with_an_idempotency_key(db_session):
    seed = await _published_grid_org(db_session)

    _, first = await _propose(db_session, seed, key="proposal-key")
    _, second = await _propose(db_session, seed, key="proposal-key")

    assert first.created is True
    assert second.created is False
    assert second.grid_version_id == first.grid_version_id
    assert second.job_id == first.job_id


async def test_second_proposal_is_blocked_while_pending(db_session):
    seed = await _published_grid_org(db_session)
    _, first = await _propose(db_session, seed)

    payload = _bulk(break_overrides=[{"after_slot": 1, "duration_minutes": 5}])
    preview = await grid_change_service.preview_grid_change(
        db_session, seed.organization.id, schemas.GridChangePreviewRequest(timeslots=payload)
    )
    assert preview.can_propose is False
    assert preview.pending_grid_version_id == first.grid_version_id

    with pytest.raises(grid_change_service.GridChangeError) as excinfo:
        await grid_change_service.propose_grid_change(
            db_session,
            seed.organization.id,
            schemas.GridChangeProposeRequest(timeslots=payload, fingerprint=preview.fingerprint),
            membership_id=seed.membership.id,
        )
    assert excinfo.value.code == "GRID_CHANGE_BLOCKED"


async def test_terminal_job_failure_rejects_the_pending_version(db_session):
    seed = await _published_grid_org(db_session)
    _, response = await _propose(db_session, seed)

    now = datetime.now(UTC)
    claim = await claim_next_job(db_session, now_utc=now)
    assert claim is not None and claim.job_id == response.job_id
    await db_session.commit()
    written = await finish_job(
        db_session,
        organization_id=seed.organization.id,
        job_id=response.job_id,
        attempt_token=claim.attempt_token,
        status="FAILED",
        result_code="FAILED",
        stop_reason="FAILED",
        now_utc=now,
    )
    await db_session.commit()
    assert written == "FAILED"

    version = await grid_version_service.get_grid_version(
        db_session, seed.organization.id, response.grid_version_id
    )
    assert version.state == models.GridVersionState.REJECTED
    assert await grid_change_service.pending_grid_change(db_session, seed.organization.id) is None


async def test_abandoned_job_recovery_rejects_the_pending_version(db_session):
    seed = await _published_grid_org(db_session)
    _, response = await _propose(db_session, seed)

    job = await db_session.get(SchedulerJobV1, response.job_id)
    now = datetime.now(UTC)
    job.status = "RUNNING"
    job.started_at = now - timedelta(minutes=10)
    job.heartbeat_at = now - timedelta(minutes=10)
    await db_session.flush()
    await db_session.commit()

    reconciled = await reconcile_abandoned(db_session, stale_after_seconds=60, now_utc=now)
    await db_session.commit()
    assert reconciled == 1
    await db_session.refresh(job)
    assert job.status == "FAILED"

    version = await grid_version_service.get_grid_version(
        db_session, seed.organization.id, response.grid_version_id
    )
    assert version.state == models.GridVersionState.REJECTED


async def test_approval_activates_the_pending_grid_version(db_session, monkeypatch):
    seed = await _published_grid_org(db_session)
    payload = _bulk(break_overrides=[{"after_slot": 2, "duration_minutes": 5}])
    preview = await grid_change_service.preview_grid_change(
        db_session, seed.organization.id, schemas.GridChangePreviewRequest(timeslots=payload)
    )
    _, response = await _propose(
        db_session,
        seed,
        bulk=payload,
        decisions=await _copy_all_affected(preview),
    )

    from app import scheduler_v1_worker as worker
    from tests._support.db_fixtures import TestingSessionLocal, test_engine

    monkeypatch.setattr(worker, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(worker, "engine_async", test_engine)
    monkeypatch.setattr(worker, "RECOVERY_ASSESSMENT_SECONDS", 0.0)
    await worker.process_next_jobs()
    await db_session.refresh(seed.state)

    now = datetime.now(UTC)
    proposal = await current_proposal(db_session, seed.organization.id)
    assert proposal is not None
    result = await approve_proposal(
        db_session,
        organization_id=seed.organization.id,
        proposal_id=proposal["proposal_id"],
        decided_by_membership_id=seed.membership.id,
        now_utc=now,
    )
    assert result.active_version_id is not None

    version = await grid_version_service.get_grid_version(
        db_session, seed.organization.id, response.grid_version_id
    )
    assert version.state == models.GridVersionState.ACTIVE
    active_grid = await grid_version_service.get_active_grid_version(
        db_session, seed.organization.id
    )
    assert active_grid is not None and active_grid.id == version.id


async def _seed_v1_configuration_for_admin_org(db_session) -> models.Organization:
    organization = await db_session.scalar(
        select(models.Organization).where(models.Organization.clerk_org_id == "org_test_001")
    )
    await settings_service.upsert_settings(
        db_session,
        organization.id,
        schemas.OrganizationSettingsUpsert(
            school_start_date=date(2026, 9, 1),
            school_hard_end_date=date(2027, 7, 31),
            preferred_end_date=date(2026, 10, 30),
            repair_stability_window_days=0,
        ),
    )
    await db_session.flush()
    year = await db_session.scalar(
        select(models.SchedulerSchoolYear).where(
            models.SchedulerSchoolYear.organization_id == organization.id,
            models.SchedulerSchoolYear.is_active.is_(True),
        )
    )
    course = models.Course(name="Course", abbreviation="C", organization_id=organization.id)
    subject = models.Subject(name="Subject", organization_id=organization.id)
    room = models.Room(name="Sala", capacity=25, organization_id=organization.id)
    db_session.add_all((course, subject, room))
    await db_session.flush()
    class_ = models.Class(
        name="A",
        size=20,
        start_year=2026,
        end_year=2029,
        grade_level=10,
        course_id=course.id,
        organization_id=organization.id,
    )
    module = models.Module(
        organization_id=organization.id,
        subject_id=subject.id,
        name="Module",
        required_minutes=100,
        order=1,
    )
    db_session.add_all((class_, module))
    await db_session.flush()
    teacher = await create_teacher_profile(db_session, organization_id=organization.id)
    assignment = CurricularAssignment(
        organization_id=organization.id,
        school_year_id=year.id,
        class_id=class_.id,
        subject_id=subject.id,
        teacher_id=teacher.id,
    )
    db_session.add(assignment)
    await db_session.flush()
    link = models.ClassSubjectLink(
        organization_id=organization.id,
        class_id=class_.id,
        subject_id=subject.id,
        grade_level=class_.grade_level,
        teacher_id=teacher.id,
    )
    db_session.add_all(
        (
            CurricularRequirement(
                organization_id=organization.id,
                assignment_id=assignment.id,
                module_id=module.id,
                sequence=1,
                required_minutes=100,
            ),
            link,
            models.Timeslot(
                organization_id=organization.id,
                day_of_week=0,
                start_time=time(9, 0),
                end_time=time(9, 50),
            ),
            SchedulerVersionV1(
                organization_id=organization.id,
                school_year_id=year.id,
                origin="e2e",
                status="ACTIVE",
                snapshot_digest="a" * 64,
                created_at=datetime(2026, 9, 22, 10, tzinfo=UTC),
                approved_at=datetime(2026, 9, 22, 10, tzinfo=UTC),
            ),
        )
    )
    await db_session.flush()
    await select_all_subject_modules(
        db_session,
        organization_id=organization.id,
        class_subject_link_id=link.id,
        subject_id=subject.id,
    )
    await db_session.commit()
    return organization


def _proposal_body(fingerprint: str, **changes) -> dict:
    payload = {
        "start_time": "09:00",
        "end_time": "11:45",
        "slot_duration_minutes": 50,
        "break_duration_minutes": 10,
        "break_overrides": [],
        "days_of_week": [0],
    }
    payload.update(changes)
    return {
        "timeslots": payload,
        "fingerprint": fingerprint,
        "decisions": [],
        "idempotency_key": None,
    }


async def test_grid_change_endpoint_dispatches_the_job(
    async_client, db_session, clerk_admin_headers
):
    organization = await _seed_v1_configuration_for_admin_org(db_session)
    preview = await async_client.post(
        f"{API}/school/grid-changes/preview",
        json={"timeslots": _proposal_body("0" * 64)["timeslots"]},
        headers=clerk_admin_headers,
    )
    assert preview.status_code == 200
    fingerprint = preview.json()["fingerprint"]

    observed = {}

    class RecordingDispatcher:
        def dispatch(self, *, organization_id, job_id, task_id):
            observed["organization_id"] = organization_id
            observed["job_id"] = job_id
            observed["task_id"] = task_id

    app.dependency_overrides[deps.get_scheduler_task_dispatcher] = RecordingDispatcher
    try:
        response = await async_client.post(
            f"{API}/school/grid-changes",
            json=_proposal_body(fingerprint),
            headers=clerk_admin_headers,
        )
    finally:
        app.dependency_overrides.pop(deps.get_scheduler_task_dispatcher, None)

    assert response.status_code == 200
    data = response.json()
    assert data["strategy"] == "GRID_CHANGE"
    assert data["created"] is True
    assert observed["job_id"] == data["job_id"]
    assert observed["task_id"] == f"scheduler-v1-job-{data['job_id']}"
    assert observed["organization_id"] == organization.id

    pending = await grid_change_service.pending_grid_change(db_session, organization.id)
    assert pending is not None
    assert pending.grid_version_id == data["grid_version_id"]
    assert pending.job_id == data["job_id"]


async def test_grid_change_endpoint_keeps_the_job_queued_on_dispatch_failure(
    async_client, db_session, clerk_admin_headers
):
    organization = await _seed_v1_configuration_for_admin_org(db_session)
    preview = await async_client.post(
        f"{API}/school/grid-changes/preview",
        json={"timeslots": _proposal_body("0" * 64)["timeslots"]},
        headers=clerk_admin_headers,
    )
    fingerprint = preview.json()["fingerprint"]

    class FailingDispatcher:
        def dispatch(self, **_kwargs):
            raise RuntimeError("broker unavailable")

    app.dependency_overrides[deps.get_scheduler_task_dispatcher] = FailingDispatcher
    try:
        response = await async_client.post(
            f"{API}/school/grid-changes",
            json=_proposal_body(fingerprint),
            headers=clerk_admin_headers,
        )
    finally:
        app.dependency_overrides.pop(deps.get_scheduler_task_dispatcher, None)

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "generation_dispatch_failed"

    job = await db_session.scalar(
        select(SchedulerJobV1).where(
            SchedulerJobV1.organization_id == organization.id,
            SchedulerJobV1.grid_version_id.is_not(None),
        )
    )
    await db_session.refresh(job)
    assert job.status == "QUEUED"
    assert await grid_change_service.pending_grid_change(db_session, organization.id) is not None
