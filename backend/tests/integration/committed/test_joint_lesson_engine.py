"""Joint lesson engine: snapshot units, room capacity, generation and persistence.

WBS 3.1/3.2/3.3/3.8. The end-to-end path creates a joint group, generates and
approves through the real worker, then registers a summary on one sister and
repairs the schedule, preserving the records.
"""

from collections import defaultdict
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.scheduler.domain.candidate import SchedulingStrategy
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.infrastructure.constructive import construct_schedule
from app.scheduler.infrastructure.models import (
    SchedulerLessonLogV1,
    SchedulerLessonSliceV1,
    SchedulerLessonV1,
)
from app.scheduler.infrastructure.operations import record_lesson_log
from app.scheduler.infrastructure.snapshot import (
    SnapshotConfigurationError,
    load_snapshot,
)
from tests._support.scheduler_v1 import MOMENT, run_generation, seed_joint_school

REPAIR_NOW = datetime(2026, 9, 2, 12, tzinfo=UTC)


async def _bundle(db_session, seed):
    return await load_snapshot(
        db_session,
        seed.base.organization.id,
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        now_utc=MOMENT,
        school_year_id=seed.base.year.id,
    )


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


async def _slices(db_session, lesson_id):
    return sorted(
        (row.module_id, row.offset_minutes, row.minutes)
        for row in (
            await db_session.scalars(
                select(SchedulerLessonSliceV1).where(SchedulerLessonSliceV1.lesson_id == lesson_id)
            )
        ).all()
    )


def _joint_groups(rows):
    by_key = defaultdict(list)
    for row in rows:
        by_key[row.stable_key].append(row)
    return [group for group in by_key.values() if len(group) > 1]


async def test_snapshot_builds_a_joint_unit_with_all_member_classes(db_session):
    seed = await seed_joint_school(db_session)
    bundle = await _bundle(db_session, seed)

    joint = [row for row in bundle.snapshot.assignments if len(row.class_ids) > 1]
    assert len(joint) == 1
    assert set(joint[0].class_ids) == {seed.base.class_.id, seed.second_class.id}
    key = f"J:{seed.group_id}:{seed.base.module.id}"
    assert bundle.unit_keys[key] == joint[0].assignment_id
    assert bundle.unit_accounting[joint[0].assignment_id] == tuple(sorted(seed.assignment_ids))


async def test_joint_room_eligibility_requires_the_sum_of_member_capacities(db_session):
    seed = await seed_joint_school(db_session)
    bundle = await _bundle(db_session, seed)

    joint = next(row for row in bundle.snapshot.assignments if len(row.class_ids) > 1)

    # Each class holds 20 students, so the joint unit needs 40 seats: the
    # 25-seat room is excluded while the 60-seat room qualifies.
    assert seed.base.room.id not in joint.eligible_room_ids
    assert joint.eligible_room_ids


async def test_constructive_plans_the_joint_unit_and_validates(db_session):
    seed = await seed_joint_school(db_session)
    bundle = await _bundle(db_session, seed)

    candidate = construct_schedule(bundle.snapshot, bundle.periods)

    assert candidate is not None
    assert validate_candidate(bundle.snapshot, candidate).valid
    joint_ids = {row.assignment_id for row in bundle.snapshot.assignments if len(row.class_ids) > 1}
    assert any(lesson.assignment_id in joint_ids for lesson in candidate.lessons)


async def test_generate_and_approve_publish_exact_sister_rows(db_session, monkeypatch):
    seed = await seed_joint_school(db_session)
    await run_generation(db_session, monkeypatch, seed.base, key="joint-e2e")
    await db_session.refresh(seed.base.state)
    version_id = int(seed.base.state.active_schedule_version_id)

    rows = await _version_rows(db_session, seed, version_id)
    assert rows
    # No synthetic unit id is ever written as an assignment foreign key.
    assert {row.assignment_id for row in rows} <= set(seed.assignment_ids)

    groups = _joint_groups(rows)
    assert groups, "A aula conjunta publicada deve ter aulas irmãs."
    group = groups[0]
    assert {row.assignment_id for row in group} == set(seed.assignment_ids)
    assert len({row.teaching_unit_key for row in group}) == 1
    assert group[0].teaching_unit_key.startswith("J:")
    reference = group[0]
    slices = await _slices(db_session, reference.id)
    assert slices, "As aulas irmãs partilham os slices dos módulos conjuntos."
    for sister in group[1:]:
        assert (
            sister.school_date,
            sister.starts_at,
            sister.ends_at,
            sister.room_id,
            sister.credit_minutes,
            sister.teaching_unit_key,
        ) == (
            reference.school_date,
            reference.starts_at,
            reference.ends_at,
            reference.room_id,
            reference.credit_minutes,
            reference.teaching_unit_key,
        )
        assert await _slices(db_session, sister.id) == slices


async def test_summary_on_one_sister_then_repair_preserves_records(db_session, monkeypatch):
    seed = await seed_joint_school(db_session)
    await run_generation(db_session, monkeypatch, seed.base, key="joint-summary")
    await db_session.refresh(seed.base.state)
    first_version = int(seed.base.state.active_schedule_version_id)
    first_rows = await _version_rows(db_session, seed, first_version)
    group = _joint_groups(first_rows)[0]

    # The teacher registers one summary on any sister; the real operations API
    # credits every present class in one transaction (J12).
    await record_lesson_log(
        db_session,
        seed.base.organization.id,
        membership_id=seed.base.membership.id,
        lesson_id=group[0].id,
        status="COMPLETED",
        summary="Sumário da aula conjunta.",
        notes=None,
        now_utc=group[0].ends_at,
        planning_relevant=True,
    )
    await db_session.commit()
    logged = (
        await db_session.scalars(
            select(SchedulerLessonLogV1).where(
                SchedulerLessonLogV1.organization_id == seed.base.organization.id,
                SchedulerLessonLogV1.lesson_id.in_([row.id for row in group]),
            )
        )
    ).all()
    assert len(logged) == len(group)

    await run_generation(
        db_session, monkeypatch, seed.base, key="joint-summary-repair", now=REPAIR_NOW
    )
    await db_session.refresh(seed.base.state)
    second_version = int(seed.base.state.active_schedule_version_id)
    assert second_version != first_version
    second_rows = await _version_rows(db_session, seed, second_version)
    assert _joint_groups(second_rows), "A reparação mantém a aula conjunta."

    # Records follow their own sister into the new version.
    second_logged = (
        await db_session.scalars(
            select(SchedulerLessonLogV1).where(
                SchedulerLessonLogV1.organization_id == seed.base.organization.id,
                SchedulerLessonLogV1.lesson_id.in_([row.id for row in second_rows]),
            )
        )
    ).all()
    assert second_logged, "O sumário registado segue a aula irmã da mesma turma."


async def _approved_group(db_session, monkeypatch, key):
    seed = await seed_joint_school(db_session)
    await run_generation(db_session, monkeypatch, seed.base, key=key)
    await db_session.refresh(seed.base.state)
    version_id = int(seed.base.state.active_schedule_version_id)
    group = _joint_groups(await _version_rows(db_session, seed, version_id))[0]
    return seed, group


async def _reload_adaptive(db_session, seed):
    return await load_snapshot(
        db_session,
        seed.base.organization.id,
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        now_utc=REPAIR_NOW,
        school_year_id=seed.base.year.id,
    )


async def test_sister_metadata_mismatch_is_inconsistent(db_session, monkeypatch):
    seed, group = await _approved_group(db_session, monkeypatch, "joint-inconsistent")
    group[1].credit_minutes = max(1, group[1].physical_minutes - 10)
    await db_session.commit()

    with pytest.raises(SnapshotConfigurationError) as exc:
        await _reload_adaptive(db_session, seed)

    assert exc.value.code == "JOINT_LESSON_INCONSISTENT"


async def test_partial_sister_withdrawal_is_inconsistent(db_session, monkeypatch):
    seed, group = await _approved_group(db_session, monkeypatch, "joint-partial")
    # Withdraw only one sister: the logical lesson loses a member class.
    db_session.add(
        SchedulerLessonLogV1(
            organization_id=seed.base.organization.id,
            school_year_id=seed.base.year.id,
            lesson_id=group[1].id,
            status="OCCURRENCE",
            revision=1,
            logged_by_membership_id=seed.base.membership.id,
            logged_at=REPAIR_NOW,
            created_at=REPAIR_NOW,
            updated_at=REPAIR_NOW,
            withdrawn_at=REPAIR_NOW,
        )
    )
    await db_session.commit()

    with pytest.raises(SnapshotConfigurationError) as exc:
        await _reload_adaptive(db_session, seed)

    assert exc.value.code == "JOINT_LESSON_INCONSISTENT"


async def test_a_stale_protected_joint_key_conflicts(db_session, monkeypatch):
    seed, group = await _approved_group(db_session, monkeypatch, "joint-stale-key")
    for row in group:
        row.teaching_unit_key = "J:999999999:1"
    await db_session.commit()

    with pytest.raises(SnapshotConfigurationError) as exc:
        await _reload_adaptive(db_session, seed)

    assert exc.value.code == "JOINT_PUBLISHED_LESSONS_CONFLICT"
