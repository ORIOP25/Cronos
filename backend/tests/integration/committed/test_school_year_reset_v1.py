"""WBS year reset: a soft reset clears v1 published state, proposals, jobs and progress."""

from datetime import UTC, date, datetime

from sqlalchemy import func, select

from app import models
from app.config import settings
from app.scheduler.domain.debt import DebtOrigin
from app.scheduler.domain.demand import ExecutionEntry, ModuleCredit
from app.scheduler.infrastructure.models import (
    CurricularDebt,
    CurricularDebtSettlement,
    CurricularExecution,
    SchedulerJobV1,
    SchedulerProposalV1,
    SchedulerRecoveryReservationV1,
    SchedulerVersionV1,
)
from app.scheduler.infrastructure.progress import (
    load_executed_minutes,
    load_open_debt,
    record_debt,
    record_execution,
)
from tests._support.scheduler_v1 import (
    V1Seed,
    add_lesson,
    add_version,
    lesson_interval,
    seed_v1_assignment,
)

API = settings.API_V1_STR

MOMENT = datetime(2026, 9, 22, 10, tzinfo=UTC)
LESSON_DATE = date(2026, 9, 22)
WEEK_START = date(2026, 9, 21)


class PublishedSeed:
    def __init__(self, seed: V1Seed, version: SchedulerVersionV1, job: SchedulerJobV1) -> None:
        self.seed = seed
        self.version_id = version.id
        self.job_id = job.id
        self.organization_id = seed.organization.id
        self.assignment_id = seed.assignment.id
        self.module_id = seed.module.id
        self.state_id = seed.state.id
        self.membership_id = seed.membership.id
        self.class_id = seed.class_.id


async def _published_seed(
    db_session,
    *,
    clerk_user_id: str,
    clerk_org_id: str,
) -> PublishedSeed:
    seed = await seed_v1_assignment(
        db_session,
        clerk_user_id=clerk_user_id,
        clerk_org_id=clerk_org_id,
    )
    version = await add_version(db_session, seed)
    start, end = lesson_interval(LESSON_DATE, 10, 60)
    lesson = await add_lesson(
        db_session,
        seed,
        version,
        stable_key="1",
        school_date=LESSON_DATE,
        start=start,
        end=end,
    )
    job = SchedulerJobV1(
        organization_id=seed.organization.id,
        school_year_id=seed.year.id,
        strategy="COMPLETE_GENERATION",
        status="QUEUED",
        origin=f"reset-test:{clerk_org_id}",
        revision=1,
        attempt_token=1,
        requested_by_membership_id=seed.membership.id,
        base_version_id=version.id,
        input_revision_used=seed.state.input_revision,
        planning_revision_used=seed.state.planning_revision,
        snapshot_digest="b" * 64,
        queued_at=MOMENT,
    )
    db_session.add(job)
    await db_session.flush()
    db_session.add(
        SchedulerProposalV1(
            organization_id=seed.organization.id,
            school_year_id=seed.year.id,
            job_id=job.id,
            base_version_id=version.id,
            status="PENDING",
            snapshot_digest="b" * 64,
            policy_version="test",
            input_revision_used=seed.state.input_revision,
            planning_revision_used=seed.state.planning_revision,
            created_at=MOMENT,
        )
    )
    await db_session.flush()

    settled_debt_id = await record_debt(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        DebtOrigin(
            origin="lesson-occurrence:1",
            revision=1,
            origin_date=LESSON_DATE,
            minutes=30,
            author_id=seed.membership.id,
            reason="Falta registada",
            recorded_at=MOMENT,
        ),
    )
    assert settled_debt_id > 0
    await record_execution(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        ExecutionEntry(
            "lesson-log:1",
            1,
            seed.membership.id,
            "Aula registada",
            (ModuleCredit(seed.module.id, 40),),
            recorded_at=MOMENT,
        ),
        planning_relevant=True,
    )
    open_debt_id = await record_debt(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        DebtOrigin(
            origin="lesson-occurrence:2",
            revision=1,
            origin_date=LESSON_DATE,
            minutes=20,
            author_id=seed.membership.id,
            reason="Falta registada",
            recorded_at=MOMENT,
        ),
    )
    db_session.add(
        SchedulerRecoveryReservationV1(
            organization_id=seed.organization.id,
            school_year_id=seed.year.id,
            version_id=version.id,
            assignment_id=seed.assignment.id,
            lesson_id=lesson.id,
            debt_id=open_debt_id,
            minutes=10,
        )
    )
    seed.state.school_year_publication_state = models.SchoolYearPublicationState.PUBLISHED
    seed.state.active_schedule_version_id = str(version.id)
    seed.state.last_completed_planning_revision = seed.state.planning_revision
    seed.state.last_successful_generation_at = MOMENT
    await db_session.commit()
    return PublishedSeed(seed, version, job)


async def _week_slots(client, headers, class_id: int) -> list[dict]:
    response = await client.get(
        f"{API}/schedule/week",
        params={"week_start": WEEK_START.isoformat(), "class_id": class_id},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_soft_reset_clears_v1_schedule_state_and_progress(
    async_client,
    db_session,
):
    headers = {"Authorization": "Bearer test_reset_admin"}
    published = await _published_seed(
        db_session,
        clerk_user_id="reset_admin",
        clerk_org_id="reset_org",
    )

    assert len(await _week_slots(async_client, headers, published.class_id)) == 1

    executed_before = await load_executed_minutes(
        db_session, published.organization_id, [published.assignment_id]
    )
    open_debt_before, _ = await load_open_debt(
        db_session, published.organization_id, [published.assignment_id]
    )
    assert executed_before[published.assignment_id][published.module_id] == 40
    assert sum(open_debt_before.values()) == 20

    response = await async_client.post(
        f"{API}/school/settings/soft-reset",
        json={"confirm_phrase": "Confirmo"},
        headers=headers,
    )
    assert response.status_code == 200, response.text

    assert await _week_slots(async_client, headers, published.class_id) == []

    status = await async_client.get(f"{API}/scheduler/status", headers=headers)
    assert status.status_code == 200, status.text
    payload = status.json()
    assert payload["publication_state"] == "UNPUBLISHED"
    assert payload["active_version_id"] is None
    assert payload["default_strategy"] == "COMPLETE_GENERATION"
    assert payload["pending_proposal"] is None
    assert payload["active_job"] is None
    assert payload["revisions"]["input"] == 0
    assert payload["revisions"]["planning"] == 0
    assert payload["revisions"]["last_completed_planning"] is None
    assert payload["revisions"]["last_successful_generation_at"] is None

    db_session.expire_all()
    stored_version = await db_session.get(SchedulerVersionV1, published.version_id)
    stored_job = await db_session.get(SchedulerJobV1, published.job_id)
    stored_state = await db_session.get(models.SchedulerSchoolYearState, published.state_id)
    stored_proposal = await db_session.scalar(
        select(SchedulerProposalV1).where(SchedulerProposalV1.job_id == published.job_id)
    )
    assert stored_version.status == "SUPERSEDED"
    assert stored_job.status == "CANCELLED"
    assert stored_job.finished_at is not None
    assert stored_proposal.status == "SUPERSEDED"
    assert stored_proposal.decided_at is not None
    assert stored_proposal.decided_by_membership_id == published.membership_id
    assert stored_state.active_schedule_version_id is None
    assert stored_state.input_revision == 0
    assert stored_state.planning_revision == 0
    assert stored_state.last_completed_planning_revision is None
    assert stored_state.last_successful_generation_at is None

    executed_after = await load_executed_minutes(
        db_session, published.organization_id, [published.assignment_id]
    )
    open_debt_after, _ = await load_open_debt(
        db_session, published.organization_id, [published.assignment_id]
    )
    assert executed_after[published.assignment_id] == {published.module_id: 0}
    assert open_debt_after == {}
    reservations = await db_session.scalar(
        select(func.count())
        .select_from(SchedulerRecoveryReservationV1)
        .where(SchedulerRecoveryReservationV1.organization_id == published.organization_id)
    )
    assert reservations == 1
    active_reservations = await db_session.scalar(
        select(func.count())
        .select_from(SchedulerRecoveryReservationV1)
        .join(
            SchedulerVersionV1,
            (SchedulerVersionV1.organization_id == SchedulerRecoveryReservationV1.organization_id)
            & (SchedulerVersionV1.school_year_id == SchedulerRecoveryReservationV1.school_year_id)
            & (SchedulerVersionV1.id == SchedulerRecoveryReservationV1.version_id),
        )
        .where(
            SchedulerRecoveryReservationV1.organization_id == published.organization_id,
            SchedulerVersionV1.status == "ACTIVE",
        )
    )
    assert active_reservations == 0
    claims = await db_session.scalar(
        select(func.count())
        .select_from(CurricularDebt)
        .where(CurricularDebt.organization_id == published.organization_id)
    )
    assert claims == 2
    settlements = await db_session.scalar(
        select(func.count())
        .select_from(CurricularDebtSettlement)
        .where(CurricularDebtSettlement.organization_id == published.organization_id)
    )
    assert settlements == 2
    executions = await db_session.scalar(
        select(func.count())
        .select_from(CurricularExecution)
        .where(CurricularExecution.organization_id == published.organization_id)
    )
    assert executions == 4
    lesson_entries = await db_session.scalar(
        select(func.count())
        .select_from(CurricularExecution)
        .where(
            CurricularExecution.organization_id == published.organization_id,
            CurricularExecution.origin == "lesson-log:1",
        )
    )
    assert lesson_entries == 2


async def test_soft_reset_is_org_scoped_and_idempotent(async_client, db_session):
    headers_a = {"Authorization": "Bearer test_reset_admin_a"}
    headers_b = {"Authorization": "Bearer test_reset_admin_b"}
    published_a = await _published_seed(
        db_session,
        clerk_user_id="reset_admin_a",
        clerk_org_id="reset_org_a",
    )
    published_b = await _published_seed(
        db_session,
        clerk_user_id="reset_admin_b",
        clerk_org_id="reset_org_b",
    )

    for _ in range(2):
        response = await async_client.post(
            f"{API}/school/settings/soft-reset",
            json={"confirm_phrase": "Confirmo"},
            headers=headers_a,
        )
        assert response.status_code == 200, response.text
        assert await _week_slots(async_client, headers_a, published_a.class_id) == []

    db_session.expire_all()
    version_a = await db_session.get(SchedulerVersionV1, published_a.version_id)
    version_b = await db_session.get(SchedulerVersionV1, published_b.version_id)
    assert version_a.status == "SUPERSEDED"
    assert version_b.status == "ACTIVE"

    other_week = await _week_slots(async_client, headers_b, published_b.class_id)
    assert len(other_week) == 1
    state_b = await db_session.get(models.SchedulerSchoolYearState, published_b.state_id)
    assert state_b.school_year_publication_state == models.SchoolYearPublicationState.PUBLISHED
    assert state_b.active_schedule_version_id == str(published_b.version_id)
    assert state_b.planning_revision > 0
    assert state_b.last_successful_generation_at is not None

    executed_b = await load_executed_minutes(
        db_session, published_b.organization_id, [published_b.assignment_id]
    )
    open_debt_b, _ = await load_open_debt(
        db_session, published_b.organization_id, [published_b.assignment_id]
    )
    assert executed_b[published_b.assignment_id][published_b.module_id] == 40
    assert sum(open_debt_b.values()) == 20


async def test_soft_reset_requires_exact_confirmation(async_client, db_session):
    headers = {"Authorization": "Bearer test_reset_admin"}
    await _published_seed(
        db_session,
        clerk_user_id="reset_admin",
        clerk_org_id="reset_org",
    )

    response = await async_client.post(
        f"{API}/school/settings/soft-reset",
        json={"confirm_phrase": "confirmo"},
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "soft_reset_confirmation_required"


async def test_soft_reset_unpublishes_the_school_year(async_client, db_session):
    headers = {"Authorization": "Bearer test_reset_school-settings"}
    published = await _published_seed(
        db_session,
        clerk_user_id="reset_school-settings",
        clerk_org_id="reset_school-settings_org",
    )

    response = await async_client.post(
        f"{API}/school/settings/soft-reset",
        json={"confirm_phrase": "Confirmo"},
        headers=headers,
    )
    assert response.status_code == 200, response.text

    assert await _week_slots(async_client, headers, published.class_id) == []
    status = await async_client.get(f"{API}/scheduler/status", headers=headers)
    assert status.json()["publication_state"] == "UNPUBLISHED"
    assert status.json()["default_strategy"] == "COMPLETE_GENERATION"
    db_session.expire_all()
    stored_version = await db_session.get(SchedulerVersionV1, published.version_id)
    assert stored_version.status == "SUPERSEDED"
    executed = await load_executed_minutes(
        db_session, published.organization_id, [published.assignment_id]
    )
    assert executed[published.assignment_id] == {published.module_id: 0}
