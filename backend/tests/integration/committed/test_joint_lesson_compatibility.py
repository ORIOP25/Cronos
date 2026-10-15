"""Joint lesson compatibility: a school without joints keeps its encoded shape.

WBS 2.3.5/3.2.1. The snapshot digest of a school without joint groups must stay
byte-identical to the item-1 encoding: one ``class_id`` per assignment, no
``precedences`` and no ``claim_classes``. This is the guard that lets a pending
proposal survive the joint-lessons deploy.
"""

from app.scheduler.domain.candidate import SchedulingStrategy
from app.scheduler.domain.serialization import snapshot_to_dict
from app.scheduler.infrastructure.snapshot import load_snapshot
from tests._support.scheduler_v1 import MOMENT, seed_generatable_school, seed_joint_school


async def _bundle(db_session, *, organization_id, year_id):
    return await load_snapshot(
        db_session,
        organization_id,
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        now_utc=MOMENT,
        school_year_id=year_id,
    )


async def test_jointless_snapshot_keeps_the_legacy_encoding(db_session):
    seed = await seed_generatable_school(db_session)
    bundle = await _bundle(db_session, organization_id=seed.organization.id, year_id=seed.year.id)

    payload = snapshot_to_dict(bundle.snapshot)

    assert all("class_ids" not in row for row in payload["assignments"])
    assert all(row["class_id"] == seed.assignment.class_id for row in payload["assignments"])
    assert "precedences" not in payload
    assert "claim_classes" not in payload
    assert bundle.snapshot.precedences == ()
    assert bundle.unit_accounting == {seed.assignment.id: (seed.assignment.id,)}
    assert bundle.unit_keys == {f"A:{seed.assignment.id}": seed.assignment.id}


async def test_jointless_snapshot_digest_is_deterministic(db_session):
    seed = await seed_generatable_school(db_session)

    first = await _bundle(db_session, organization_id=seed.organization.id, year_id=seed.year.id)
    second = await _bundle(db_session, organization_id=seed.organization.id, year_id=seed.year.id)

    assert first.digest == second.digest


async def test_joint_snapshot_encodes_classes_and_exposes_units(db_session):
    seed = await seed_joint_school(db_session)
    bundle = await _bundle(
        db_session, organization_id=seed.base.organization.id, year_id=seed.base.year.id
    )

    payload = snapshot_to_dict(bundle.snapshot)

    joint_rows = [row for row in payload["assignments"] if "class_ids" in row]
    assert len(joint_rows) == 1
    assert sorted(joint_rows[0]["class_ids"]) == [seed.base.class_.id, seed.second_class.id]
    assert any(len(row.class_ids) > 1 for row in bundle.snapshot.assignments)
