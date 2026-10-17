"""S9 (R09, R13, D02, D13): a sala da turma entra no snapshot só quando é válida."""

from app import models
from app.scheduler.domain.candidate import HomeRoom, SchedulingStrategy
from app.scheduler.infrastructure.snapshot import load_snapshot
from tests._support.db_fixtures import get_school_room_type_id
from tests._support.scheduler_v1 import MOMENT, seed_generatable_school


async def _snapshot(db, seed):
    bundle = await load_snapshot(
        db,
        seed.organization.id,
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        now_utc=MOMENT,
        school_year_id=seed.year.id,
    )
    return bundle.snapshot


async def _lab_room(db, seed, name: str, capacity: int = 30) -> models.Room:
    room = models.Room(
        organization_id=seed.organization.id,
        name=name,
        capacity=capacity,
        room_type_id=await get_school_room_type_id(db, seed.organization.id, "Laboratório"),
    )
    db.add(room)
    await db.flush()
    return room


async def test_a_normal_subject_may_use_the_class_laboratory_home_room(db_session):
    seed = await seed_generatable_school(db_session, clerk_org_id="home_room_snapshot_pairs")
    lab = await _lab_room(db_session, seed, "L-03")
    seed.class_.home_room_id = lab.id
    await db_session.commit()

    snapshot = await _snapshot(db_session, seed)

    assert snapshot.home_rooms == (HomeRoom(class_id=seed.class_.id, room_id=lab.id),)
    (assignment,) = snapshot.assignments
    assert assignment.eligible_room_ids == frozenset({seed.room.id, lab.id})
    assert assignment.needs_special_room is False


async def test_a_class_grown_above_its_home_room_ignores_it(db_session):
    """R09: a turma que cresce acima da lotação da sala da turma deixa de a usar."""
    seed = await seed_generatable_school(db_session, clerk_org_id="home_room_snapshot_grown")
    seed.room.capacity = 40
    lab = await _lab_room(db_session, seed, "L-03", capacity=30)
    seed.class_.home_room_id = lab.id
    await db_session.commit()
    seed.class_.size = 35
    await db_session.commit()

    snapshot = await _snapshot(db_session, seed)

    assert snapshot.home_rooms == ()
    (assignment,) = snapshot.assignments
    assert assignment.eligible_room_ids == frozenset({seed.room.id})


async def test_an_archived_home_room_is_ignored(db_session):
    seed = await seed_generatable_school(db_session, clerk_org_id="home_room_snapshot_archived")
    lab = await _lab_room(db_session, seed, "L-03")
    seed.class_.home_room_id = lab.id
    lab.is_archived = True
    await db_session.commit()

    snapshot = await _snapshot(db_session, seed)

    assert snapshot.home_rooms == ()
    (assignment,) = snapshot.assignments
    assert assignment.eligible_room_ids == frozenset({seed.room.id})


async def test_a_special_room_subject_uses_only_its_own_type_and_is_flagged(db_session):
    """D07/D12: uma disciplina de sala própria não usa a sala da turma de outro tipo."""
    seed = await seed_generatable_school(db_session, clerk_org_id="home_room_snapshot_special")
    lab = await _lab_room(db_session, seed, "L-05")
    seed.class_.home_room_id = seed.room.id
    seed.subject.room_type_id = await get_school_room_type_id(
        db_session, seed.organization.id, "Laboratório"
    )
    await db_session.commit()

    snapshot = await _snapshot(db_session, seed)

    assert snapshot.home_rooms == (HomeRoom(class_id=seed.class_.id, room_id=seed.room.id),)
    (assignment,) = snapshot.assignments
    assert assignment.needs_special_room is True
    assert assignment.eligible_room_ids == frozenset({lab.id})
