from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app import models, schemas
from app.api import deps
from app.config import settings as app_settings
from app.main import app
from app.services import grid_change_service, grid_version_service, settings_service
from app.services.scheduler_job_service import SchedulerJobService
from app.services.scheduler_state_service import SchedulerStateService

PUBLISHED = models.SchoolYearPublicationState.PUBLISHED
API = app_settings.API_V1_STR


async def _create_published_org(db_session) -> tuple[models.Organization, int]:
    organization = models.Organization(name="Proposal School", plan_status="active")
    db_session.add(organization)
    await db_session.flush()
    await settings_service.upsert_settings(
        db_session,
        organization.id,
        schemas.OrganizationSettingsUpsert(
            school_start_date=date(2025, 9, 1),
            school_hard_end_date=date(2026, 7, 31),
            repair_stability_window_days=0,
        ),
    )
    account = models.User(name="Proposal Admin", email="proposal-admin@test.invalid")
    db_session.add(account)
    await db_session.flush()
    membership = models.OrganizationMembership(
        organization_id=organization.id,
        account_id=account.id,
        organization_display_name="Proposal Admin",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.active,
        can_admin=True,
        can_teach=False,
    )
    db_session.add(membership)
    await db_session.flush()
    return organization, membership.id


async def _publish(db_session, organization) -> None:
    state_service = SchedulerStateService(db_session)
    school_year = await state_service.get_active_school_year(organization.id)
    state = await state_service.get_state(organization.id, school_year.id)
    state.school_year_publication_state = PUBLISHED
    state.approved_scheduler_state_version = state.scheduler_state_version
    state.active_schedule_version_id = "draft-0"
    await db_session.flush()


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


async def _seed_published_grid(db_session, organization) -> None:
    await settings_service.save_and_regenerate_grid(
        db_session,
        organization.id,
        schemas.GridConfigurationCommand(
            grid_settings=schemas.OrganizationGridSettingsUpsert(),
            timeslots=_bulk(end_time="10:50"),
        ),
    )


async def _published_grid_org(db_session) -> tuple[models.Organization, int]:
    organization, membership_id = await _create_published_org(db_session)
    await _seed_published_grid(db_session, organization)
    await _publish(db_session, organization)
    return organization, membership_id


async def _propose(db_session, organization, membership_id, *, decisions=None, key=None, bulk=None):
    payload = bulk or _bulk(break_overrides=[{"after_slot": 2, "duration_minutes": 5}])
    preview = await grid_change_service.preview_grid_change(
        db_session,
        organization.id,
        schemas.GridChangePreviewRequest(timeslots=payload),
    )
    response = await grid_change_service.propose_grid_change(
        db_session,
        organization.id,
        schemas.GridChangeProposeRequest(
            timeslots=payload,
            fingerprint=preview.fingerprint,
            decisions=decisions or [],
            idempotency_key=key,
        ),
        membership_id=membership_id,
    )
    return preview, response


async def test_proposal_creates_pending_version_and_grid_change_job(db_session):
    organization, membership_id = await _published_grid_org(db_session)
    published = await grid_version_service.get_active_grid_version(db_session, organization.id)
    published_blocks = await grid_version_service.get_version_blocks(
        db_session, organization.id, published.id
    )
    published_ids = sorted(block.id for block in published_blocks)

    first_block = published_blocks[0]
    teacher = models.Teacher(
        organization_id=organization.id,
        organization_membership_id=None,
    )
    account = models.User(name="Teacher", email="proposal-teacher@test.invalid")
    db_session.add(account)
    await db_session.flush()
    membership = models.OrganizationMembership(
        organization_id=organization.id,
        account_id=account.id,
        organization_display_name="Teacher",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.none,
        can_admin=False,
        can_teach=True,
        teacher_access_mode=models.TeacherAccessMode.scheduler_only,
    )
    db_session.add(membership)
    await db_session.flush()
    teacher.organization_membership_id = membership.id
    db_session.add(teacher)
    await db_session.flush()
    db_session.add(
        models.Availability(
            organization_id=organization.id,
            teacher_id=teacher.id,
            timeslot_id=first_block.id,
            score=models.PreferenceLevel.IMPOSSIBLE.value,
        )
    )
    db_session.add(
        models.Constraint(
            organization_id=organization.id,
            rule_type=models.ConstraintType.teacher_preferred,
            teacher_id=teacher.id,
            timeslot_id=first_block.id,
        )
    )
    await db_session.flush()

    preview, response = await _propose(
        db_session,
        organization,
        membership_id,
        decisions=[
            schemas.GridChangeDecision(
                current_timeslot_id=first_block.id,
                action="COPY",
            )
        ],
    )

    version = await grid_version_service.get_grid_version(
        db_session, organization.id, response.grid_version_id
    )
    assert version is not None
    assert version.state == models.GridVersionState.PENDING
    assert version.effective_date == preview.first_editable_date
    blocks = await grid_version_service.get_version_blocks(db_session, organization.id, version.id)
    assert len(blocks) == 3

    job = await db_session.get(models.ScheduleGenerationJob, response.job_id)
    assert job is not None
    assert job.strategy == models.ScheduleGenerationStrategy.GRID_CHANGE
    assert job.trigger_type == models.ScheduleGenerationTrigger.GRID_CHANGE
    assert job.grid_version_id == version.id

    published_after = await grid_version_service.get_grid_version(
        db_session, organization.id, published.id
    )
    await db_session.refresh(published_after)
    assert published_after.state == models.GridVersionState.ACTIVE
    blocks_after = await grid_version_service.get_version_blocks(
        db_session, organization.id, published.id
    )
    assert sorted(block.id for block in blocks_after) == published_ids

    copied_availability = await db_session.scalars(
        select(models.Availability).where(
            models.Availability.teacher_id == teacher.id,
            models.Availability.timeslot_id.in_({block.id for block in blocks}),
        )
    )
    assert [row.score for row in copied_availability] == [models.PreferenceLevel.IMPOSSIBLE.value]
    copied_constraint = await db_session.scalar(
        select(models.Constraint).where(
            models.Constraint.organization_id == organization.id,
            models.Constraint.timeslot_id.in_({block.id for block in blocks}),
        )
    )
    assert copied_constraint is not None
    assert copied_constraint.rule_type == models.ConstraintType.teacher_preferred


async def test_proposal_requires_decisions_for_moved_associations(db_session):
    organization, membership_id = await _published_grid_org(db_session)
    published = await grid_version_service.get_active_grid_version(db_session, organization.id)
    block = (
        await grid_version_service.get_version_blocks(db_session, organization.id, published.id)
    )[0]
    teacher = await _add_teacher(db_session, organization)
    db_session.add(
        models.Availability(
            organization_id=organization.id,
            teacher_id=teacher.id,
            timeslot_id=block.id,
            score=models.PreferenceLevel.IMPOSSIBLE.value,
        )
    )
    await db_session.flush()

    payload = _bulk(slot_duration_minutes=55, break_duration_minutes=5)
    preview = await grid_change_service.preview_grid_change(
        db_session, organization.id, schemas.GridChangePreviewRequest(timeslots=payload)
    )
    assert preview.can_propose is True
    moved = next(
        entry for entry in preview.affected_availabilities if entry.current_timeslot_id == block.id
    )
    assert moved.requires_decision is True

    with pytest.raises(grid_change_service.GridChangeError) as excinfo:
        await grid_change_service.propose_grid_change(
            db_session,
            organization.id,
            schemas.GridChangeProposeRequest(
                timeslots=payload, fingerprint=preview.fingerprint, decisions=[]
            ),
            membership_id=membership_id,
        )
    assert excinfo.value.code == "GRID_CHANGE_DECISION_REQUIRED"
    assert await grid_change_service.pending_grid_change(db_session, organization.id) is None


async def test_proposal_rejects_stale_fingerprint(db_session):
    organization, membership_id = await _published_grid_org(db_session)

    with pytest.raises(grid_change_service.GridChangeError) as excinfo:
        await grid_change_service.propose_grid_change(
            db_session,
            organization.id,
            schemas.GridChangeProposeRequest(timeslots=_bulk(), fingerprint="0" * 64),
            membership_id=membership_id,
        )
    assert excinfo.value.code == "GRID_CHANGE_STALE"
    assert await grid_change_service.pending_grid_change(db_session, organization.id) is None


async def test_proposal_is_idempotent_with_an_idempotency_key(db_session):
    organization, membership_id = await _published_grid_org(db_session)

    _, first = await _propose(db_session, organization, membership_id, key="proposal-key")
    _, second = await _propose(db_session, organization, membership_id, key="proposal-key")

    assert first.created is True
    assert second.created is False
    assert second.grid_version_id == first.grid_version_id
    assert second.job_id == first.job_id


async def test_second_proposal_is_blocked_while_pending(db_session):
    organization, membership_id = await _published_grid_org(db_session)
    _, first = await _propose(db_session, organization, membership_id)

    payload = _bulk(break_overrides=[{"after_slot": 1, "duration_minutes": 5}])
    preview = await grid_change_service.preview_grid_change(
        db_session, organization.id, schemas.GridChangePreviewRequest(timeslots=payload)
    )
    assert preview.can_propose is False
    assert preview.pending_grid_version_id == first.grid_version_id

    with pytest.raises(grid_change_service.GridChangeError) as excinfo:
        await grid_change_service.propose_grid_change(
            db_session,
            organization.id,
            schemas.GridChangeProposeRequest(timeslots=payload, fingerprint=preview.fingerprint),
            membership_id=membership_id,
        )
    assert excinfo.value.code == "GRID_CHANGE_BLOCKED"


async def test_terminal_job_failure_rejects_the_proposal(db_session):
    organization, membership_id = await _published_grid_org(db_session)
    _, response = await _propose(db_session, organization, membership_id)

    job = await SchedulerJobService(db_session).mark_dispatch_failed(
        organization.id, response.job_id, "dispatcher unavailable"
    )
    assert job.job_status == models.ScheduleGenerationJobStatus.FAILED

    version = await grid_version_service.get_grid_version(
        db_session, organization.id, response.grid_version_id
    )
    assert version.state == models.GridVersionState.REJECTED
    assert await grid_change_service.pending_grid_change(db_session, organization.id) is None


async def test_stale_job_recovery_rejects_the_proposal(db_session):
    organization, membership_id = await _published_grid_org(db_session)
    _, response = await _propose(db_session, organization, membership_id)

    job = await db_session.get(models.ScheduleGenerationJob, response.job_id)
    now = datetime.now(UTC)
    job.queued_at = now - timedelta(minutes=20)
    job.job_status = models.ScheduleGenerationJobStatus.RUNNING
    job.started_at = now - timedelta(minutes=10)
    job.deadline_at = now - timedelta(minutes=5)
    await db_session.flush()

    totals = await SchedulerJobService(db_session).recover_stale_jobs(organization.id, now=now)
    assert totals["worker_stalled"] == 1
    await db_session.refresh(job)
    assert job.job_status == models.ScheduleGenerationJobStatus.FAILED

    version = await grid_version_service.get_grid_version(
        db_session, organization.id, response.grid_version_id
    )
    assert version.state == models.GridVersionState.REJECTED


async def _add_teacher(db_session, organization) -> models.Teacher:
    account = models.User(name="Teacher", email="proposal-teacher@test.invalid")
    db_session.add(account)
    await db_session.flush()
    membership = models.OrganizationMembership(
        organization_id=organization.id,
        account_id=account.id,
        organization_display_name="Teacher",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.none,
        can_admin=False,
        can_teach=True,
        teacher_access_mode=models.TeacherAccessMode.scheduler_only,
    )
    db_session.add(membership)
    await db_session.flush()
    teacher = models.Teacher(
        organization_id=organization.id,
        organization_membership_id=membership.id,
    )
    db_session.add(teacher)
    await db_session.flush()
    return teacher


async def _published_admin_org(db_session) -> models.Organization:
    organization = await db_session.scalar(
        select(models.Organization).where(models.Organization.clerk_org_id == "org_test_001")
    )
    await settings_service.upsert_settings(
        db_session,
        organization.id,
        schemas.OrganizationSettingsUpsert(
            school_start_date=date(2025, 9, 1),
            school_hard_end_date=date(2026, 7, 31),
            repair_stability_window_days=0,
        ),
    )
    await _seed_published_grid(db_session, organization)
    await _publish(db_session, organization)
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
    organization = await _published_admin_org(db_session)
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
    assert observed["task_id"] == f"scheduler-job-{data['job_id']}"
    assert observed["organization_id"] == organization.id

    pending = await grid_change_service.pending_grid_change(db_session, organization.id)
    assert pending is not None
    assert pending.grid_version_id == data["grid_version_id"]
    assert pending.job_id == data["job_id"]


async def test_grid_change_endpoint_rejects_the_proposal_on_dispatch_failure(
    async_client, db_session, clerk_admin_headers
):
    organization = await _published_admin_org(db_session)
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
        select(models.ScheduleGenerationJob).where(
            models.ScheduleGenerationJob.organization_id == organization.id,
            models.ScheduleGenerationJob.strategy == models.ScheduleGenerationStrategy.GRID_CHANGE,
        )
    )
    await db_session.refresh(job)
    assert job.job_status == models.ScheduleGenerationJobStatus.FAILED
    assert await grid_change_service.pending_grid_change(db_session, organization.id) is None
