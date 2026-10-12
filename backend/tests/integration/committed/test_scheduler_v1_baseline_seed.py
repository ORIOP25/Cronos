"""Parity: the native published-baseline helper matches the solver-published contract."""

import pytest
from sqlalchemy import select

from app import models
from app.scheduler.domain.candidate import SchedulingStrategy
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.infrastructure.models import SchedulerLessonV1, SchedulerVersionV1
from app.scheduler.infrastructure.snapshot import load_snapshot
from tests._support.scheduler_v1 import (
    MOMENT,
    publish_schedule,
    seed_generatable_school,
    seed_published_baseline,
)

pytestmark = pytest.mark.postgresql


async def _observable(db_session, seed) -> dict:
    version_id = int(seed.state.active_schedule_version_id)
    version = await db_session.get(SchedulerVersionV1, version_id)
    rows = (
        await db_session.scalars(
            select(SchedulerLessonV1)
            .where(
                SchedulerLessonV1.organization_id == seed.organization.id,
                SchedulerLessonV1.version_id == version_id,
            )
            .order_by(SchedulerLessonV1.id)
        )
    ).all()
    keys = sorted(int(row.stable_key) for row in rows)
    bundle = await load_snapshot(
        db_session,
        seed.organization.id,
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        now_utc=MOMENT,
        school_year_id=seed.year.id,
    )
    baseline = bundle.baseline
    return {
        "status": version.status,
        "approved": version.approved_at is not None,
        "publication": seed.state.school_year_publication_state,
        "first_approved": seed.organization.first_real_schedule_approved_at is not None,
        "digest_is_fingerprint": version.snapshot_digest != "a" * 64,
        "credit": sum(row.credit_minutes for row in rows),
        "baseline_total": 0
        if baseline is None
        else sum(row.credit_minutes for row in baseline.lessons),
        "baseline_valid": baseline is not None
        and validate_candidate(bundle.snapshot, baseline).valid,
        "stable_keys_unique": len(set(keys)) == len(keys) and all(key > 0 for key in keys),
    }


async def test_native_baseline_matches_the_solver_published_contract(db_session, monkeypatch):
    solver_seed = await seed_generatable_school(
        db_session, clerk_user_id="parity_solver", clerk_org_id="parity_solver"
    )
    await db_session.commit()
    await publish_schedule(db_session, monkeypatch, solver_seed)

    native_seed = await seed_generatable_school(
        db_session, clerk_user_id="parity_native", clerk_org_id="parity_native"
    )
    await db_session.commit()
    await seed_published_baseline(db_session, native_seed)

    solver = await _observable(db_session, solver_seed)
    native = await _observable(db_session, native_seed)

    assert native == solver
    assert native["status"] == "ACTIVE"
    assert native["publication"] is models.SchoolYearPublicationState.PUBLISHED
    assert native["digest_is_fingerprint"] is True
    assert native["credit"] == 100
    assert native["baseline_total"] == 100
    assert native["baseline_valid"] is True
    assert native["stable_keys_unique"] is True
