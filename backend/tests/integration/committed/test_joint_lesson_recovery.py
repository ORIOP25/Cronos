"""Joint lesson recovery end to end (WBS 3.4/3.8.3/5.4).

One class absent from a joint lesson gets a ``D`` deficit lesson that is then
completed, settling its debt and aligning it with the joint progress. A teacher
absence across every sister is recovered as a joint replacement whose
reservations point at each sister's claim class and whose completion credits
every class exactly once.
"""

from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select

from app import models, schemas
from app.scheduler.domain.candidate import SchedulingStrategy
from app.scheduler.infrastructure.models import (
    CurricularRequirement,
    SchedulerLessonV1,
    SchedulerRecoveryReservationV1,
)
from app.scheduler.infrastructure.operations import record_lesson_log
from app.scheduler.infrastructure.progress import load_executed_minutes, load_open_debt
from app.scheduler.infrastructure.snapshot import load_snapshot
from app.services.scheduler_state_service import SchedulerStateService
from tests._support.scheduler_v1 import run_generation, seed_joint_school

REPAIR_NOW = datetime(2026, 9, 2, 12, tzinfo=UTC)


async def _version_rows(db_session, seed, version_id):
    return (
        await db_session.scalars(
            select(SchedulerLessonV1)
            .where(
                SchedulerLessonV1.organization_id == seed.base.organization.id,
                SchedulerLessonV1.version_id == version_id,
            )
            .order_by(SchedulerLessonV1.id)
        )
    ).all()


def _joint_groups(rows):
    by_key = defaultdict(list)
    for row in rows:
        by_key[row.stable_key].append(row)
    return [group for group in by_key.values() if len(group) > 1]


async def _add_successor_module(db_session, seed) -> models.Module:
    """A separate module selected only by the second class (separate successor)."""
    module = models.Module(
        organization_id=seed.base.organization.id,
        subject_id=seed.base.subject.id,
        name="Sucessor",
        required_minutes=50,
        order=1,
    )
    db_session.add(module)
    await db_session.flush()
    db_session.add(
        CurricularRequirement(
            organization_id=seed.base.organization.id,
            assignment_id=seed.assignment_ids[1],
            module_id=module.id,
            sequence=2,
            required_minutes=50,
        )
    )
    await db_session.execute(
        models.class_subject_module.insert().values(
            organization_id=seed.base.organization.id,
            class_subject_link_id=seed.link_ids[1],
            module_id=module.id,
        )
    )
    await db_session.flush()
    return module


async def _occurrences(db_session, seed):
    from app.scheduler.infrastructure import occurrences as occurrences_v1

    return await occurrences_v1.list_occurrences(db_session, seed.base.organization.id)


async def _decide(db_session, seed, item, *, status, class_ids, now):
    from app.scheduler.infrastructure import occurrences as occurrences_v1

    await occurrences_v1.update_occurrence(
        db_session,
        seed.base.organization.id,
        item["id"],
        schemas.LessonOccurrenceUpdate(status=status, version=item["version"], class_ids=class_ids),
        decided_by_membership_id=seed.base.membership.id,
        now_utc=now,
    )
    await db_session.commit()


async def _bump_revisions(db_session, seed) -> None:
    state = await SchedulerStateService(db_session).get_state(
        seed.base.organization.id, seed.base.year.id
    )
    await db_session.refresh(state)
    state.input_revision += 1
    state.planning_revision += 1
    await db_session.commit()


async def _complete(db_session, seed, lesson_row, summary: str) -> None:
    await record_lesson_log(
        db_session,
        seed.base.organization.id,
        membership_id=seed.base.membership.id,
        lesson_id=lesson_row.id,
        status="COMPLETED",
        summary=summary,
        notes=None,
        now_utc=lesson_row.ends_at,
        planning_relevant=True,
    )
    await db_session.commit()


async def test_absent_class_deficit_is_completed_and_settles_the_debt(db_session, monkeypatch):
    seed = await seed_joint_school(db_session)
    module1 = seed.base.module
    await _add_successor_module(db_session, seed)
    await db_session.commit()
    await run_generation(db_session, monkeypatch, seed.base, key="joint-gap")
    await db_session.refresh(seed.base.state)
    first_version = int(seed.base.state.active_schedule_version_id)
    group = _joint_groups(await _version_rows(db_session, seed, first_version))[0]
    joint_lesson = min(group, key=lambda row: row.starts_at)
    absent_class = seed.second_class.id
    absent_assignment, present_assignment = seed.assignment_ids[1], seed.assignment_ids[0]

    # The teacher registers the joint lesson with the second class absent: the
    # present class is credited, the absent class stays a pending occurrence.
    await record_lesson_log(
        db_session,
        seed.base.organization.id,
        membership_id=seed.base.membership.id,
        lesson_id=joint_lesson.id,
        status="COMPLETED",
        summary="Aula conjunta com falta.",
        notes=None,
        now_utc=joint_lesson.ends_at,
        absent_class_ids=[absent_class],
        planning_relevant=True,
    )
    await db_session.commit()

    page = await _occurrences(db_session, seed)
    assert page["total"] == 1
    item = page["items"][0]
    classes = {row["class_id"]: row for row in item["joint_lesson"]["classes"]}
    assert set(classes) == {seed.base.class_.id, absent_class}
    assert classes[absent_class]["operational_state"] == "OPEN_PENDING"

    # Targeted decision for the absent class only, on its own log line/version.
    await _decide(
        db_session,
        seed,
        item,
        status=models.LessonOccurrenceStatus.GAP,
        class_ids=[absent_class],
        now=joint_lesson.ends_at,
    )
    open_debt, _ = await load_open_debt(db_session, seed.base.organization.id, [absent_assignment])
    owed = sum(open_debt.values())
    assert owed == joint_lesson.credit_minutes

    executed_a = (
        await load_executed_minutes(db_session, seed.base.organization.id, [present_assignment])
    )[present_assignment]
    executed_b = (
        await load_executed_minutes(db_session, seed.base.organization.id, [absent_assignment])
    )[absent_assignment]
    assert executed_a.get(module1.id, 0) == joint_lesson.credit_minutes
    assert executed_b.get(module1.id, 0) == 0

    await _bump_revisions(db_session, seed)
    await run_generation(db_session, monkeypatch, seed.base, key="joint-gap-repair", now=REPAIR_NOW)
    await db_session.refresh(seed.base.state)
    second_version = int(seed.base.state.active_schedule_version_id)
    assert second_version != first_version
    rows = await _version_rows(db_session, seed, second_version)

    deficit_key = f"D:{absent_assignment}:{module1.id}"
    deficit = [row for row in rows if row.teaching_unit_key == deficit_key]
    assert deficit, "Reposição do défice."
    d_row = deficit[0]
    assert d_row.assignment_id == absent_assignment
    successors = [
        row for row in rows if row.teaching_unit_key.startswith(f"S:{absent_assignment}:")
    ]
    assert successors
    assert d_row.ends_at <= min(row.starts_at for row in successors)

    # Complete the deficit lesson after its real end: the absent class catches up
    # with the joint progress and its debt settles.
    await _complete(db_session, seed, d_row, "Reposição do défice.")
    executed_a2 = (
        await load_executed_minutes(db_session, seed.base.organization.id, [present_assignment])
    )[present_assignment]
    executed_b2 = (
        await load_executed_minutes(db_session, seed.base.organization.id, [absent_assignment])
    )[absent_assignment]
    assert executed_b2.get(module1.id, 0) == executed_a2.get(module1.id, 0) > 0
    settled, _ = await load_open_debt(db_session, seed.base.organization.id, [absent_assignment])
    assert sum(settled.values()) == 0

    # Reload: the deficit unit is retained with zero residual and the classes are
    # aligned on the joint progress.
    bundle = await load_snapshot(
        db_session,
        seed.base.organization.id,
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        now_utc=d_row.ends_at,
        school_year_id=seed.base.year.id,
    )
    assert deficit_key in bundle.unit_keys
    deficit_unit = next(
        row
        for row in bundle.snapshot.assignments
        if row.assignment_id == bundle.unit_keys[deficit_key]
    )
    deficit_executed = bundle.snapshot.executed_minutes.get(deficit_unit.assignment_id, {})
    deficit_residual = sum(
        module.required_minutes - deficit_executed.get(module.module_id, 0)
        for module in deficit_unit.modules
    )
    assert deficit_residual == 0
    joint_unit = next(row for row in bundle.snapshot.assignments if len(row.class_ids) > 1)
    assert bundle.snapshot.executed_minutes[joint_unit.assignment_id][module1.id] == (
        executed_b2.get(module1.id, 0)
    )


async def test_teacher_absence_all_gap_recovers_a_joint_replacement(db_session, monkeypatch):
    seed = await seed_joint_school(db_session)
    module1 = seed.base.module
    await db_session.commit()
    await run_generation(db_session, monkeypatch, seed.base, key="joint-absence")
    await db_session.refresh(seed.base.state)
    first_version = int(seed.base.state.active_schedule_version_id)
    group = _joint_groups(await _version_rows(db_session, seed, first_version))[0]
    lesson = min(group, key=lambda row: row.starts_at)
    class_a, class_b = seed.base.class_.id, seed.second_class.id

    # The teacher is absent: the occurrence covers every sister class.
    await record_lesson_log(
        db_session,
        seed.base.organization.id,
        membership_id=seed.base.membership.id,
        lesson_id=lesson.id,
        status="OCCURRENCE",
        summary="Professor faltou.",
        notes=None,
        now_utc=lesson.ends_at,
        planning_relevant=True,
    )
    await db_session.commit()
    page = await _occurrences(db_session, seed)
    assert page["total"] == 1
    item = page["items"][0]
    states = {row["class_id"]: row["operational_state"] for row in item["joint_lesson"]["classes"]}
    assert states == {class_a: "OPEN_PENDING", class_b: "OPEN_PENDING"}

    await _decide(
        db_session,
        seed,
        item,
        status=models.LessonOccurrenceStatus.GAP,
        class_ids=[class_a, class_b],
        now=lesson.ends_at,
    )
    open_debt, _ = await load_open_debt(db_session, seed.base.organization.id, seed.assignment_ids)
    owed = sum(open_debt.values())
    assert owed == 2 * lesson.credit_minutes

    await _bump_revisions(db_session, seed)
    await run_generation(
        db_session, monkeypatch, seed.base, key="joint-absence-repair", now=REPAIR_NOW
    )
    await db_session.refresh(seed.base.state)
    second_version = int(seed.base.state.active_schedule_version_id)
    rows = await _version_rows(db_session, seed, second_version)

    reservations = (
        await db_session.scalars(
            select(SchedulerRecoveryReservationV1).where(
                SchedulerRecoveryReservationV1.organization_id == seed.base.organization.id,
                SchedulerRecoveryReservationV1.version_id == second_version,
            )
        )
    ).all()
    assert reservations, "A falta do professor repõe-se numa aula conjunta."
    # Each claim class reserves on its own sister of one joint replacement.
    assert {row.assignment_id for row in reservations} == set(seed.assignment_ids)
    assert sum(row.minutes for row in reservations) == owed
    reserved_lesson_ids = {row.lesson_id for row in reservations}
    reserved = [row for row in rows if row.id in reserved_lesson_ids]
    assert len({row.stable_key for row in reserved}) == 1
    assert all(row.teaching_unit_key.startswith("J:") for row in reserved)
    # One logical lesson, one interval and one room: the teacher's hours count once.
    assert len({(row.starts_at, row.ends_at, row.room_id) for row in reserved}) == 1

    replacement = reserved[0]
    await _complete(db_session, seed, replacement, "Aula conjunta reposta.")
    settled, _ = await load_open_debt(db_session, seed.base.organization.id, seed.assignment_ids)
    assert sum(settled.values()) == 0
    executed_a = (
        await load_executed_minutes(db_session, seed.base.organization.id, [seed.assignment_ids[0]])
    )[seed.assignment_ids[0]]
    executed_b = (
        await load_executed_minutes(db_session, seed.base.organization.id, [seed.assignment_ids[1]])
    )[seed.assignment_ids[1]]
    assert executed_a.get(module1.id, 0) == replacement.credit_minutes
    assert executed_b.get(module1.id, 0) == replacement.credit_minutes
