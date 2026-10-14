"""CI509.4: relevant rule mutations move the v1 planning revision."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from pydantic import TypeAdapter
from sqlalchemy import select

from app import models, schemas
from app.scheduler.infrastructure.proposals import ProposalConflict, approve_proposal
from app.scheduler.infrastructure.queries import current_proposal, scheduler_status
from app.services import room_service, schedule_service
from tests._support.scheduler_v1 import (
    MOMENT,
    run_generation,
    seed_generatable_school,
)

pytestmark = pytest.mark.postgresql

CONSTRAINT_ADAPTER = TypeAdapter(schemas.ConstraintCreate)


def _future_rule(teacher_id: int, timeslot_id: int) -> schemas.ConstraintCreate:
    return CONSTRAINT_ADAPTER.validate_python(
        {
            "rule_type": "teacher_unavailable",
            "rule_payload": {
                "teacher_id": teacher_id,
                "date": (date.today() + timedelta(days=30)).isoformat(),
                "timeslot_id": timeslot_id,
            },
        }
    )


def _past_rule(teacher_id: int) -> schemas.ConstraintCreate:
    return CONSTRAINT_ADAPTER.validate_python(
        {
            "rule_type": "teacher_unavailable",
            "rule_payload": {
                "teacher_id": teacher_id,
                "date": (date.today() - timedelta(days=1)).isoformat(),
            },
        }
    )


async def _timeslot_id(db_session, organization_id: int) -> int:
    return await db_session.scalar(
        select(models.Timeslot.id).where(models.Timeslot.organization_id == organization_id)
    )


async def _queue_generation(db_session, monkeypatch, seed, *, key: str) -> None:
    from app import scheduler_v1_worker as worker
    from app.scheduler.infrastructure.jobs import enqueue_generation
    from tests._support.db_fixtures import TestingSessionLocal, test_engine

    await enqueue_generation(
        db_session,
        seed.organization.id,
        idempotency_key=key,
        requested_by_membership_id=seed.membership.id,
        now_utc=MOMENT,
    )
    await db_session.commit()
    monkeypatch.setattr(worker, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(worker, "engine_async", test_engine)
    monkeypatch.setattr(worker, "_now", lambda: MOMENT)
    monkeypatch.setattr(worker, "RECOVERY_ASSESSMENT_SECONDS", 0.0)
    await worker.process_next_jobs()
    await db_session.refresh(seed.state)


async def _published_school(db_session, monkeypatch, *, suffix: str):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id=f"rule_{suffix}",
        clerk_org_id=f"rule_org_{suffix}",
    )
    await db_session.commit()
    await run_generation(db_session, monkeypatch, seed, key=f"rule-{suffix}")
    return seed


async def test_a_future_unavailable_rule_consumes_a_planning_revision(db_session, monkeypatch):
    seed = await _published_school(db_session, monkeypatch, suffix="future")
    await db_session.refresh(seed.state)
    before = (seed.state.input_revision, seed.state.planning_revision)
    timeslot_id = await _timeslot_id(db_session, seed.organization.id)

    await schedule_service.create_constraint(
        db_session,
        _future_rule(seed.assignment.teacher_id, timeslot_id),
        seed.organization.id,
    )
    await db_session.commit()
    await db_session.refresh(seed.state)

    assert seed.state.input_revision == before[0] + 1
    assert seed.state.planning_revision == before[1] + 1
    status = await scheduler_status(db_session, seed.organization.id, now_utc=MOMENT)
    assert "PLANNING_CHANGE" in status["eligibility"]["reasons"]
    assert status["default_strategy"] == "ADAPTIVE_RECOVERY"


async def test_a_rule_change_invalidates_a_pending_proposal(db_session, monkeypatch):
    seed = await seed_generatable_school(
        db_session, clerk_user_id="rule_pending", clerk_org_id="rule_org_pending"
    )
    await db_session.commit()
    await _queue_generation(db_session, monkeypatch, seed, key="rule-pending")
    proposal = await current_proposal(db_session, seed.organization.id)
    assert proposal is not None
    assert proposal["can_approve"] is True
    timeslot_id = await _timeslot_id(db_session, seed.organization.id)

    await schedule_service.create_constraint(
        db_session,
        _future_rule(seed.assignment.teacher_id, timeslot_id),
        seed.organization.id,
    )
    await db_session.commit()

    summary = await current_proposal(db_session, seed.organization.id)
    assert summary["can_approve"] is False
    assert summary["stale_reason"] == "REVISIONS_CHANGED"
    with pytest.raises(ProposalConflict) as conflict:
        await approve_proposal(
            db_session,
            organization_id=seed.organization.id,
            proposal_id=proposal["proposal_id"],
            decided_by_membership_id=seed.membership.id,
            now_utc=MOMENT,
        )
    assert conflict.value.code == "proposal_stale"


async def test_a_past_rule_does_not_consume_a_planning_revision(db_session, monkeypatch):
    seed = await _published_school(db_session, monkeypatch, suffix="past")
    await db_session.refresh(seed.state)
    before = (seed.state.input_revision, seed.state.planning_revision)

    await schedule_service.create_constraint(
        db_session,
        _past_rule(seed.assignment.teacher_id),
        seed.organization.id,
    )
    await db_session.commit()
    await db_session.refresh(seed.state)

    assert seed.state.input_revision == before[0] + 1
    assert seed.state.planning_revision == before[1]
    status = await scheduler_status(db_session, seed.organization.id, now_utc=MOMENT)
    assert "PLANNING_CHANGE" not in status["eligibility"]["reasons"]


async def test_a_rename_that_the_planner_ignores_does_not_consume_revisions(
    db_session, monkeypatch
):
    seed = await _published_school(db_session, monkeypatch, suffix="noop")
    await db_session.refresh(seed.state)
    before = (seed.state.input_revision, seed.state.planning_revision)

    await room_service.update_room(
        db_session,
        seed.room.id,
        schemas.RoomUpdate(name="Renamed Room"),
        seed.organization.id,
    )
    await db_session.commit()
    await db_session.refresh(seed.state)

    assert (seed.state.input_revision, seed.state.planning_revision) == before
    status = await scheduler_status(db_session, seed.organization.id, now_utc=MOMENT)
    assert "PLANNING_CHANGE" not in status["eligibility"]["reasons"]
