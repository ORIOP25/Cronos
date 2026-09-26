from datetime import UTC, datetime

from app.scheduler.infrastructure.models import SchedulerJobV1, SchedulerProposalV1
from tests._support.scheduler_v1 import seed_generatable_school


def _v1_headers(suffix: str) -> dict[str, str]:
    return {"Authorization": f"Bearer scheduler_v1_tenant_{suffix}"}


async def _v1_tenant_bundle(db_session, suffix: str) -> dict[str, object]:
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id=f"scheduler_v1_tenant_{suffix}",
        clerk_org_id=f"org_scheduler_v1_{suffix}",
    )
    now = datetime.now(UTC)
    job = SchedulerJobV1(
        organization_id=seed.organization.id,
        school_year_id=seed.year.id,
        strategy="COMPLETE_GENERATION",
        status="QUEUED",
        origin=f"v1-{suffix}",
        revision=1,
        attempt_token=1,
        requested_by_membership_id=seed.membership.id,
        queued_at=now,
    )
    db_session.add(job)
    await db_session.flush()
    proposal = SchedulerProposalV1(
        organization_id=seed.organization.id,
        school_year_id=seed.year.id,
        job_id=job.id,
        status="PENDING",
        snapshot_digest="a" * 64,
        policy_version="baseline-v1",
        input_revision_used=0,
        planning_revision_used=0,
        created_at=now,
    )
    db_session.add(proposal)
    await db_session.commit()
    return {"organization": seed.organization, "job": job, "proposal": proposal}


async def test_scheduler_api_rejects_cross_tenant_jobs_and_drafts(
    async_client,
    db_session,
):
    await _v1_tenant_bundle(db_session, "a")
    tenant_b = await _v1_tenant_bundle(db_session, "b")
    job_id = tenant_b["job"].id
    proposal_id = tenant_b["proposal"].id
    responses = [
        await async_client.get(f"/api/v1/scheduler/jobs/{job_id}", headers=_v1_headers("a")),
        await async_client.post(
            f"/api/v1/scheduler/jobs/{job_id}/cancel", headers=_v1_headers("a")
        ),
        await async_client.get(
            f"/api/v1/scheduler/drafts/{proposal_id}/diff", headers=_v1_headers("a")
        ),
        await async_client.post(
            f"/api/v1/scheduler/drafts/{proposal_id}/approve", headers=_v1_headers("a")
        ),
        await async_client.post(
            f"/api/v1/scheduler/drafts/{proposal_id}/reject", headers=_v1_headers("a")
        ),
    ]

    assert [response.status_code for response in responses] == [404] * len(responses)
    await db_session.refresh(tenant_b["job"])
    await db_session.refresh(tenant_b["proposal"])
    assert tenant_b["job"].status == "QUEUED"
    assert tenant_b["proposal"].status == "PENDING"
