"""Read-only weekly preview of a pending scheduler proposal (WBS proposal preview).

The published weekly grid shows the ACTIVE version. A proposal preview reads the
lessons of the proposal's CANDIDATE version in the same weekly format.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select

from app import models
from app.config import settings
from app.scheduler.infrastructure.models import SchedulerJobV1, SchedulerProposalV1
from app.scheduler.infrastructure.operations import ProposalPreviewNotFound, week_schedule
from tests._support.db_fixtures import (
    accept_current_legal_documents,
    create_teacher_profile,
    create_teacher_user,
)
from tests._support.scheduler_v1 import (
    V1Seed,
    add_lesson,
    add_version,
    lesson_interval,
    seed_v1_assignment,
)

pytestmark = pytest.mark.postgresql

API = settings.API_V1_STR
WEEK_START = date(2026, 9, 21)
SCHOOL_DATE = date(2026, 9, 22)
CREATED_AT = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)


async def _add_proposal(
    db_session,
    seed: V1Seed,
    version_id: int,
    *,
    status: str = "PENDING",
) -> SchedulerProposalV1:
    job = SchedulerJobV1(
        organization_id=seed.organization.id,
        school_year_id=seed.year.id,
        strategy="COMPLETE_GENERATION",
        status="QUEUED",
        origin=f"proposal-preview-{status.lower()}",
        revision=1,
        attempt_token=1,
        requested_by_membership_id=seed.membership.id,
        queued_at=CREATED_AT,
    )
    db_session.add(job)
    await db_session.flush()
    proposal = SchedulerProposalV1(
        organization_id=seed.organization.id,
        school_year_id=seed.year.id,
        job_id=job.id,
        version_id=version_id,
        status=status,
        snapshot_digest="c" * 64,
        policy_version="baseline-v1",
        input_revision_used=0,
        planning_revision_used=0,
        created_at=CREATED_AT,
        decided_at=None if status == "PENDING" else CREATED_AT,
    )
    db_session.add(proposal)
    await db_session.flush()
    return proposal


def _lesson_ids(slots: list[dict]) -> list[int]:
    return [slot["scheduler_lesson_id"] for slot in slots]


async def test_proposal_preview_shows_the_candidate_lessons_not_the_active_ones(db_session):
    seed = await seed_v1_assignment(db_session)
    active = await add_version(db_session, seed, status="ACTIVE")
    candidate = await add_version(db_session, seed, status="CANDIDATE", digest="b" * 64)
    start, end = lesson_interval(SCHOOL_DATE, 9)
    active_lesson = await add_lesson(
        db_session, seed, active, stable_key="active", school_date=SCHOOL_DATE, start=start, end=end
    )
    candidate_lesson = await add_lesson(
        db_session,
        seed,
        candidate,
        stable_key="candidate",
        school_date=SCHOOL_DATE,
        start=start,
        end=end,
    )
    proposal = await _add_proposal(db_session, seed, candidate.id)
    await db_session.commit()

    preview = await week_schedule(
        db_session,
        seed.organization.id,
        week_start=WEEK_START,
        class_id=seed.class_.id,
        teacher_id=None,
        proposal_id=proposal.id,
    )
    published = await week_schedule(
        db_session,
        seed.organization.id,
        week_start=WEEK_START,
        class_id=seed.class_.id,
        teacher_id=None,
    )

    assert _lesson_ids(preview) == [candidate_lesson.id]
    assert preview[0]["can_complete"] is False
    assert preview[0]["blocked_reason"] == "proposal_preview"
    assert preview[0]["can_create_occurrence"] is False
    assert _lesson_ids(published) == [active_lesson.id]


async def test_proposal_preview_works_before_any_version_is_active(db_session):
    seed, lesson, proposal = await _seed_pending_preview(db_session)

    preview = await week_schedule(
        db_session,
        seed.organization.id,
        week_start=WEEK_START,
        class_id=seed.class_.id,
        teacher_id=None,
        proposal_id=proposal.id,
    )
    published = await week_schedule(
        db_session,
        seed.organization.id,
        week_start=WEEK_START,
        class_id=seed.class_.id,
        teacher_id=None,
    )

    assert _lesson_ids(preview) == [lesson.id]
    assert published is None


async def test_proposal_preview_rejects_a_proposal_that_is_not_pending(db_session):
    seed = await seed_v1_assignment(db_session)
    candidate = await add_version(db_session, seed, status="CANDIDATE", digest="b" * 64)
    proposal = await _add_proposal(db_session, seed, candidate.id, status="REJECTED")
    await db_session.commit()

    with pytest.raises(ProposalPreviewNotFound):
        await week_schedule(
            db_session,
            seed.organization.id,
            week_start=WEEK_START,
            class_id=seed.class_.id,
            teacher_id=None,
            proposal_id=proposal.id,
        )


async def test_proposal_preview_rejects_another_organizations_proposal(db_session):
    seed = await seed_v1_assignment(db_session)
    other = await seed_v1_assignment(
        db_session,
        clerk_user_id="proposal_preview_other",
        clerk_org_id="proposal_preview_other_org",
    )
    other_candidate = await add_version(db_session, other, status="CANDIDATE", digest="e" * 64)
    other_proposal = await _add_proposal(db_session, other, other_candidate.id)
    await db_session.commit()

    with pytest.raises(ProposalPreviewNotFound):
        await week_schedule(
            db_session,
            seed.organization.id,
            week_start=WEEK_START,
            class_id=seed.class_.id,
            teacher_id=None,
            proposal_id=other_proposal.id,
        )


async def _seed_pending_preview(
    db_session,
    *,
    clerk_user_id: str = "proposal_preview_admin",
    clerk_org_id: str = "proposal_preview_org",
):
    """A pending proposal whose candidate version holds one lesson, and no ACTIVE version."""
    seed = await seed_v1_assignment(
        db_session, clerk_user_id=clerk_user_id, clerk_org_id=clerk_org_id
    )
    candidate = await add_version(db_session, seed, status="CANDIDATE", digest="b" * 64)
    start, end = lesson_interval(SCHOOL_DATE, 9)
    lesson = await add_lesson(
        db_session,
        seed,
        candidate,
        stable_key="first",
        school_date=SCHOOL_DATE,
        start=start,
        end=end,
    )
    proposal = await _add_proposal(db_session, seed, candidate.id)
    await db_session.commit()
    return seed, lesson, proposal


async def _teacher_headers(db_session, seed: V1Seed) -> tuple[dict[str, str], int]:
    """Headers of a teacher-only actor (no admin capability) in the seed organization."""
    teacher = await create_teacher_profile(
        db_session, organization_id=seed.organization.id, name="Proposal Preview Teacher"
    )
    user = await create_teacher_user(
        db_session,
        clerk_user_id="proposal_preview_teacher",
        email="proposal.preview.teacher@escola.pt",
        name="Proposal Preview Teacher",
        org_id=seed.organization.id,
        teacher_id=teacher.id,
    )
    membership = await db_session.scalar(
        select(models.OrganizationMembership).where(
            models.OrganizationMembership.organization_id == seed.organization.id,
            models.OrganizationMembership.account_id == user.id,
        )
    )
    await accept_current_legal_documents(
        db_session, organization_id=seed.organization.id, membership_id=membership.id
    )
    await db_session.commit()
    return {"Authorization": "Bearer test_proposal_preview_teacher"}, teacher.id


async def test_proposal_preview_over_http_is_admin_only(async_client, db_session):
    seed, _lesson, proposal = await _seed_pending_preview(db_session)
    headers, teacher_id = await _teacher_headers(db_session, seed)

    response = await async_client.get(
        f"{API}/schedule/week",
        headers=headers,
        params={"week_start": "2026-09-21", "teacher_id": teacher_id, "proposal_id": proposal.id},
    )

    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["code"] == "proposal_preview_forbidden"
    assert detail["message"] == "Só a direção pode ver a proposta pendente."


async def test_admin_previews_the_pending_proposal_over_http(async_client, db_session):
    seed, lesson, proposal = await _seed_pending_preview(db_session)

    response = await async_client.get(
        f"{API}/schedule/week",
        headers={"Authorization": "Bearer test_proposal_preview_admin"},
        params={"week_start": "2026-09-21", "class_id": seed.class_.id, "proposal_id": proposal.id},
    )

    assert response.status_code == 200
    slots = response.json()
    assert [slot["scheduler_lesson_id"] for slot in slots] == [lesson.id]
    assert slots[0]["can_complete"] is False
    assert slots[0]["blocked_reason"] == "proposal_preview"
    assert slots[0]["can_create_occurrence"] is False


async def test_unknown_proposal_is_not_found_over_http(async_client, db_session):
    seed, _lesson, _proposal = await _seed_pending_preview(db_session)

    response = await async_client.get(
        f"{API}/schedule/week",
        headers={"Authorization": "Bearer test_proposal_preview_admin"},
        params={"week_start": "2026-09-21", "class_id": seed.class_.id, "proposal_id": 999_999},
    )

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["code"] == "proposal_not_found"
    assert detail["message"] == "Proposta não encontrada."
