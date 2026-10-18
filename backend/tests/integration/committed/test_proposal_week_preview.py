"""Read-only weekly preview of a pending scheduler proposal (WBS proposal preview).

The published weekly grid shows the ACTIVE version. A proposal preview reads the
lessons of the proposal's CANDIDATE version in the same weekly format.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.scheduler.infrastructure.models import SchedulerJobV1, SchedulerProposalV1
from app.scheduler.infrastructure.operations import ProposalPreviewNotFound, week_schedule
from tests._support.scheduler_v1 import (
    V1Seed,
    add_lesson,
    add_version,
    lesson_interval,
    seed_v1_assignment,
)

pytestmark = pytest.mark.postgresql

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
    seed = await seed_v1_assignment(db_session)
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
