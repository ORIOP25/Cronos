"""Read models for the scheduler v1 API. Reads never write.

Freshness is reported without changing the database: approval is the only
command that marks a proposal stale. GET responses expose product language
data only; the translation of stable codes belongs to the frontend.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.scheduler.domain.eligibility import (
    EligibilityFacts,
    generation_eligibility,
)
from app.scheduler.infrastructure.jobs import queue_position
from app.scheduler.infrastructure.models import (
    JOB_ACTIVE_STATUSES,
    JOB_TERMINAL_STATUSES,
    SchedulerJobV1,
    SchedulerProposalV1,
)
from app.scheduler.infrastructure.progress import load_active_version_id


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


async def _year_and_state(db: AsyncSession, organization_id: int):
    year = await db.scalar(
        select(models.SchedulerSchoolYear).where(
            models.SchedulerSchoolYear.organization_id == organization_id,
            models.SchedulerSchoolYear.is_active.is_(True),
        )
    )
    if year is None:
        return None, None
    state = await db.scalar(
        select(models.SchedulerSchoolYearState).where(
            models.SchedulerSchoolYearState.organization_id == organization_id,
            models.SchedulerSchoolYearState.school_year_id == year.id,
        )
    )
    return year, state


async def _eligibility(
    db: AsyncSession,
    organization_id: int,
    year: models.SchedulerSchoolYear,
    state: models.SchedulerSchoolYearState,
    *,
    now_utc: datetime,
) -> dict:
    latest_terminal = await db.scalar(
        select(SchedulerJobV1)
        .where(
            SchedulerJobV1.organization_id == organization_id,
            SchedulerJobV1.school_year_id == year.id,
            SchedulerJobV1.status.in_(JOB_TERMINAL_STATUSES),
        )
        .order_by(SchedulerJobV1.id.desc())
    )
    active_job = await db.scalar(
        select(SchedulerJobV1)
        .where(
            SchedulerJobV1.organization_id == organization_id,
            SchedulerJobV1.school_year_id == year.id,
            SchedulerJobV1.status.in_(JOB_ACTIVE_STATUSES),
        )
        .order_by(SchedulerJobV1.id)
    )
    zone = ZoneInfo(year.timezone)
    last_success = state.last_successful_generation_at
    decision = generation_eligibility(
        EligibilityFacts(
            school_today=now_utc.astimezone(zone).date(),
            planning_revision=state.planning_revision,
            last_completed_planning_revision=state.last_completed_planning_revision,
            last_successful_generation_date=(
                None if last_success is None else last_success.astimezone(zone).date()
            ),
            last_attempt_incomplete=(
                latest_terminal is not None and latest_terminal.status != "SUCCEEDED"
            ),
            active_job=active_job is not None,
        )
    )
    return {
        "can_generate": decision.can_generate,
        "reasons": [reason.value for reason in decision.reasons],
        "blocker": decision.blocker.value if decision.blocker is not None else None,
        "active_job": active_job,
    }


async def _job_summary(db: AsyncSession, job: SchedulerJobV1) -> dict:
    position = await queue_position(db, job.id) if job.status == "QUEUED" else None
    return {
        "id": job.id,
        "strategy": job.strategy,
        "status": job.status,
        "result_code": job.result_code,
        "stop_reason": job.stop_reason,
        "queue_position": position,
        "queued_at": job.queued_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "heartbeat_at": job.heartbeat_at,
        "cancellation_requested": job.cancellation_requested_at is not None,
    }


def _proposal_summary(
    proposal: SchedulerProposalV1,
    *,
    state: models.SchedulerSchoolYearState | None,
    active_version_id: int | None,
) -> dict:
    stale_reason: str | None = None
    if proposal.status == "PENDING" and state is not None:
        if (
            state.input_revision != proposal.input_revision_used
            or state.planning_revision != proposal.planning_revision_used
        ):
            stale_reason = "REVISIONS_CHANGED"
        elif active_version_id != proposal.base_version_id:
            stale_reason = "BASE_VERSION_CHANGED"
    metrics = dict(proposal.metrics_json or {})
    evidence = metrics.get("evidence") or {}
    stages = list(evidence.get("stages") or ())
    certified = int(evidence.get("certified_stages") or 0)
    return {
        "proposal_id": proposal.id,
        "status": proposal.status,
        "created_at": proposal.created_at,
        "decided_at": proposal.decided_at,
        "base_version_id": proposal.base_version_id,
        "policy_version": proposal.policy_version,
        "is_stale": stale_reason is not None,
        "stale_reason": stale_reason,
        "can_approve": proposal.status == "PENDING" and stale_reason is None,
        "metrics": metrics,
        "warnings": list(metrics.get("warnings", ())),
        "diagnostics": list(metrics.get("diagnostics", ())),
        "quality_summary": {
            "stop_reason": metrics.get("stop_reason"),
            "objective_scope": evidence.get("objective_scope"),
            "certified_stages": certified,
            "total_stages": len(stages),
            "claims_optimum": bool(stages) and certified == len(stages),
            "policy_version": metrics.get("policy_version") or proposal.policy_version,
        },
    }


async def scheduler_status(db: AsyncSession, organization_id: int, *, now_utc: datetime) -> dict:
    year, state = await _year_and_state(db, organization_id)
    if year is None or state is None:
        return {
            "configured": False,
            "school_year": None,
            "publication_state": "UNPUBLISHED",
            "active_version_id": None,
            "revisions": {
                "input": 0,
                "planning": 0,
                "last_completed_planning": None,
                "last_successful_generation_at": None,
            },
            "eligibility": {
                "can_generate": False,
                "reasons": [],
                "blocker": None,
            },
            "default_strategy": "COMPLETE_GENERATION",
            "active_job": None,
            "pending_proposal": None,
        }
    active_version_id = await load_active_version_id(db, organization_id, year.id)
    active_proposal_id = (
        await db.scalar(
            select(SchedulerProposalV1.id)
            .where(
                SchedulerProposalV1.organization_id == organization_id,
                SchedulerProposalV1.school_year_id == year.id,
                SchedulerProposalV1.version_id == active_version_id,
                SchedulerProposalV1.status == "APPROVED",
            )
            .order_by(SchedulerProposalV1.id.desc())
            .limit(1)
        )
        if active_version_id is not None
        else None
    )
    eligibility = await _eligibility(db, organization_id, year, state, now_utc=now_utc)
    active_job = eligibility.pop("active_job")
    proposal = await db.scalar(
        select(SchedulerProposalV1)
        .where(
            SchedulerProposalV1.organization_id == organization_id,
            SchedulerProposalV1.school_year_id == year.id,
            SchedulerProposalV1.status == "PENDING",
        )
        .order_by(SchedulerProposalV1.id.desc())
    )
    return {
        "configured": True,
        "school_year": {
            "id": year.id,
            "label": year.label,
            "start_date": year.start_date,
            "preferred_end_date": year.preferred_end_date,
            "hard_end_date": year.hard_end_date,
            "timezone": year.timezone,
        },
        "publication_state": state.school_year_publication_state.value,
        "active_version_id": active_version_id,
        "active_proposal_id": active_proposal_id,
        "revisions": {
            "input": state.input_revision,
            "planning": state.planning_revision,
            "last_completed_planning": state.last_completed_planning_revision,
            "last_successful_generation_at": _iso(state.last_successful_generation_at),
        },
        "eligibility": eligibility,
        "default_strategy": (
            "ADAPTIVE_RECOVERY" if active_version_id is not None else "COMPLETE_GENERATION"
        ),
        "active_job": None if active_job is None else await _job_summary(db, active_job),
        "pending_proposal": (
            None
            if proposal is None
            else _proposal_summary(proposal, state=state, active_version_id=active_version_id)
        ),
    }


async def get_job(db: AsyncSession, organization_id: int, job_id: int) -> dict | None:
    job = await db.scalar(
        select(SchedulerJobV1).where(
            SchedulerJobV1.id == job_id,
            SchedulerJobV1.organization_id == organization_id,
        )
    )
    if job is None:
        return None
    summary = await _job_summary(db, job)
    proposal = await db.scalar(
        select(SchedulerProposalV1).where(SchedulerProposalV1.job_id == job.id)
    )
    summary["proposal_id"] = proposal.id if proposal is not None else None
    summary["summary"] = dict(proposal.metrics_json) if proposal is not None else None
    return summary


async def current_proposal(db: AsyncSession, organization_id: int) -> dict | None:
    year, state = await _year_and_state(db, organization_id)
    if year is None:
        return None
    proposal = await db.scalar(
        select(SchedulerProposalV1)
        .where(
            SchedulerProposalV1.organization_id == organization_id,
            SchedulerProposalV1.school_year_id == year.id,
            SchedulerProposalV1.status == "PENDING",
        )
        .order_by(SchedulerProposalV1.id.desc())
    )
    if proposal is None:
        return None
    active_version_id = await load_active_version_id(db, organization_id, year.id)
    summary = _proposal_summary(proposal, state=state, active_version_id=active_version_id)
    job = await db.scalar(select(SchedulerJobV1).where(SchedulerJobV1.id == proposal.job_id))
    summary["strategy"] = job.strategy if job is not None else None
    return summary


async def proposal_diff(db: AsyncSession, organization_id: int, proposal_id: int) -> dict | None:
    proposal = await db.scalar(
        select(SchedulerProposalV1).where(
            SchedulerProposalV1.id == proposal_id,
            SchedulerProposalV1.organization_id == organization_id,
        )
    )
    if proposal is None:
        return None
    return dict(proposal.diff_json or {})
