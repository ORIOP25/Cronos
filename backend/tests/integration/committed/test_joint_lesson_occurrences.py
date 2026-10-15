"""Joint lesson occurrences and substitutes (WBS 5.2 and 5.3)."""

from __future__ import annotations

from datetime import time, timedelta

import pytest
from joint_lesson_support import (
    MOMENT,
    SCHOOL_DATE,
    add_joint_lesson,
    add_joint_subject,
    seed_joint_pair,
)
from sqlalchemy import select

from app import models, schemas
from app.core.exceptions import AppError
from app.scheduler.infrastructure import occurrences as occurrences_v1
from app.scheduler.infrastructure.models import (
    SchedulerLessonLogV1,
    SchedulerLessonSliceV1,
)
from app.scheduler.infrastructure.operations import (
    record_lesson_log,
    record_operational_lesson_log,
    week_schedule,
)
from app.scheduler.infrastructure.progress import load_executed_minutes
from tests._support.scheduler_v1 import add_lesson, add_version, seed_v1_assignment

pytestmark = pytest.mark.postgresql


async def test_list_groups_joint_siblings_into_one_card(db_session):
    seed, class_b, assignment_b, _group = await seed_joint_pair(db_session)
    version = await add_version(db_session, seed, status="ACTIVE")
    lesson_a, lesson_b = await add_joint_lesson(
        db_session, seed, assignment_b, version, stable_key="occ1"
    )
    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson_a.id,
        status="OCCURRENCE",
        summary="Professora faltou.",
        notes=None,
        now_utc=MOMENT,
    )
    await db_session.commit()

    page = await occurrences_v1.list_occurrences(db_session, seed.organization.id)
    assert page["total"] == 1
    item = page["items"][0]
    classes = {row["class_id"]: row for row in item["joint_lesson"]["classes"]}
    assert set(classes) == {seed.class_.id, class_b.id}
    assert classes[seed.class_.id]["operational_state"] == "OPEN_PENDING"
    assert classes[class_b.id]["operational_state"] == "OPEN_PENDING"
    log_a = await db_session.scalar(
        select(SchedulerLessonLogV1.id).where(SchedulerLessonLogV1.lesson_id == lesson_a.id)
    )
    log_b = await db_session.scalar(
        select(SchedulerLessonLogV1.id).where(SchedulerLessonLogV1.lesson_id == lesson_b.id)
    )
    assert {classes[seed.class_.id]["id"], classes[class_b.id]["id"]} == {log_a, log_b}


async def test_class_ids_gap_decides_every_member_class(db_session):
    seed, class_b, assignment_b, _group = await seed_joint_pair(
        db_session, clerk_user_id="joint_gap", clerk_org_id="joint_gap_org"
    )
    version = await add_version(db_session, seed, status="ACTIVE")
    lesson_a, lesson_b = await add_joint_lesson(
        db_session, seed, assignment_b, version, stable_key="occ2"
    )
    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson_a.id,
        status="OCCURRENCE",
        summary="Professora faltou.",
        notes=None,
        now_utc=MOMENT,
    )
    await db_session.commit()
    item = (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]

    await occurrences_v1.update_occurrence(
        db_session,
        seed.organization.id,
        item["id"],
        schemas.LessonOccurrenceUpdate(
            status=models.LessonOccurrenceStatus.GAP,
            version=item["version"],
            class_ids=[seed.class_.id, class_b.id],
        ),
        decided_by_membership_id=seed.membership.id,
        now_utc=MOMENT,
    )
    await db_session.commit()

    debts = await occurrences_v1.get_debts(db_session, seed.organization.id)
    assert debts["total_gaps"] == 2
    logs = (
        await db_session.scalars(
            select(SchedulerLessonLogV1).where(
                SchedulerLessonLogV1.lesson_id.in_([lesson_a.id, lesson_b.id])
            )
        )
    ).all()
    assert {row.decision for row in logs} == {"GAP"}


async def test_presence_split_is_visible_and_given_credits_the_absent_class(db_session):
    seed, class_b, assignment_b, _group = await seed_joint_pair(
        db_session, clerk_user_id="joint_presence", clerk_org_id="joint_presence_org"
    )
    version = await add_version(db_session, seed, status="ACTIVE")
    lesson_a, _lesson_b = await add_joint_lesson(
        db_session, seed, assignment_b, version, stable_key="occ3"
    )
    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson_a.id,
        status="COMPLETED",
        summary="Aula conjunta.",
        notes=None,
        now_utc=lesson_a.ends_at,
        absent_class_ids=[class_b.id],
    )
    await db_session.commit()

    page = await occurrences_v1.list_occurrences(db_session, seed.organization.id)
    assert page["total"] == 1
    item = page["items"][0]
    classes = {row["class_id"]: row for row in item["joint_lesson"]["classes"]}
    assert classes[seed.class_.id]["operational_state"] == "DECIDED_GIVEN"
    assert classes[class_b.id]["operational_state"] == "OPEN_PENDING"

    await occurrences_v1.update_occurrence(
        db_session,
        seed.organization.id,
        classes[class_b.id]["id"],
        schemas.LessonOccurrenceUpdate(
            status=models.LessonOccurrenceStatus.GIVEN,
            version=classes[class_b.id]["version"],
        ),
        decided_by_membership_id=seed.membership.id,
        now_utc=lesson_a.ends_at,
    )
    await db_session.commit()
    executed_b = await load_executed_minutes(db_session, seed.organization.id, [assignment_b.id])
    assert sum(executed_b[assignment_b.id].values()) == lesson_a.credit_minutes


async def test_a_joint_subject_candidate_must_match_the_member_classes(db_session):
    seed, class_b, assignment_b, _group = await seed_joint_pair(
        db_session, clerk_user_id="joint_cand", clerk_org_id="joint_cand_org"
    )
    version = await add_version(db_session, seed, status="ACTIVE")
    lesson_a, _lesson_b = await add_joint_lesson(
        db_session, seed, assignment_b, version, stable_key="occ4"
    )
    ingles, ingles_teacher, _module, _assignments = await add_joint_subject(
        db_session, seed, class_b, name="Inglês"
    )
    await add_joint_subject(db_session, seed, class_b, name="Matemática", joint=False)
    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson_a.id,
        status="OCCURRENCE",
        summary="Falta.",
        notes=None,
        now_utc=MOMENT,
    )
    await db_session.commit()
    item = (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]

    recommendations = await occurrences_v1.get_substitute_recommendations(
        db_session, seed.organization.id, item["id"]
    )
    assert {row["subject_id"] for row in recommendations} == {ingles.id}
    assert {row["teacher_id"] for row in recommendations} == {ingles_teacher.id}

    diagnostics = await occurrences_v1.get_substitute_diagnostics(
        db_session, seed.organization.id, item["id"]
    )
    codes = {
        exclusion["code"]
        for candidate in diagnostics["candidates"]
        for exclusion in candidate["exclusions"]
    }
    assert "joint_classes_mismatch" in codes


async def test_a_single_class_substitute_cannot_give_a_joint_subject(db_session):
    seed = await seed_v1_assignment(
        db_session, clerk_user_id="joint_single_sub", clerk_org_id="joint_single_sub_org"
    )
    class_b = models.Class(
        name="B",
        size=18,
        start_year=2026,
        end_year=2029,
        grade_level=10,
        course_id=seed.course.id,
        organization_id=seed.organization.id,
    )
    db_session.add(class_b)
    await db_session.flush()
    version = await add_version(db_session, seed, status="ACTIVE")
    lesson = await add_lesson(
        db_session,
        seed,
        version,
        stable_key="single1",
        school_date=SCHOOL_DATE,
        start=MOMENT,
        end=MOMENT + timedelta(minutes=50),
    )
    db_session.add(
        SchedulerLessonSliceV1(
            organization_id=seed.organization.id,
            school_year_id=seed.year.id,
            lesson_id=lesson.id,
            module_id=seed.module.id,
            offset_minutes=0,
            minutes=50,
        )
    )
    portugues, _teacher, _module, _assignments = await add_joint_subject(
        db_session, seed, class_b, name="Português"
    )
    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson.id,
        status="OCCURRENCE",
        summary="Falta.",
        notes=None,
        now_utc=MOMENT,
    )
    await db_session.commit()
    item = (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]

    recommendations = await occurrences_v1.get_substitute_recommendations(
        db_session, seed.organization.id, item["id"]
    )
    assert all(row["subject_id"] != portugues.id for row in recommendations)
    diagnostics = await occurrences_v1.get_substitute_diagnostics(
        db_session, seed.organization.id, item["id"]
    )
    candidate = next(row for row in diagnostics["candidates"] if row["subject_id"] == portugues.id)
    assert {exclusion["code"] for exclusion in candidate["exclusions"]} == {"joint_in_progress"}


async def test_a_joint_substitution_plans_and_concludes_every_member(db_session):
    seed, class_b, assignment_b, _group = await seed_joint_pair(
        db_session, clerk_user_id="joint_sub", clerk_org_id="joint_sub_org"
    )
    seed.year.timezone = "UTC"
    version = await add_version(db_session, seed, status="ACTIVE")
    lesson_a, _lesson_b = await add_joint_lesson(
        db_session, seed, assignment_b, version, stable_key="occ5"
    )
    db_session.add(
        models.Timeslot(
            organization_id=seed.organization.id,
            day_of_week=SCHOOL_DATE.weekday(),
            start_time=time(10, 0),
            end_time=time(10, 50),
        )
    )
    ingles, ingles_teacher, _module, ingles_assignments = await add_joint_subject(
        db_session, seed, class_b, name="Inglês"
    )
    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson_a.id,
        status="OCCURRENCE",
        summary="Falta.",
        notes=None,
        now_utc=MOMENT,
    )
    await db_session.commit()
    item = (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]

    decided = await occurrences_v1.update_occurrence(
        db_session,
        seed.organization.id,
        item["id"],
        schemas.LessonOccurrenceUpdate(
            status=models.LessonOccurrenceStatus.SUBSTITUTED,
            version=item["version"],
            substitute_teacher_id=ingles_teacher.id,
            substitute_subject_id=ingles.id,
            class_ids=[seed.class_.id, class_b.id],
        ),
        decided_by_membership_id=seed.membership.id,
        now_utc=MOMENT,
    )
    await db_session.commit()
    assert decided["operational_state"] == "DECIDED_SUBSTITUTED"
    blocks = (
        await db_session.scalars(
            select(models.OperationalScheduleBlock).where(
                models.OperationalScheduleBlock.organization_id == seed.organization.id,
                models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
            )
        )
    ).all()
    assert len(blocks) == 2

    await record_operational_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        operational_block_id=blocks[0].id,
        payload=schemas.LessonLogCreate(
            status=models.LessonLogStatus.COMPLETED,
            summary="Inglês dado.",
            notes=None,
            absent_class_ids=[class_b.id],
        ),
        now_utc=lesson_a.ends_at,
    )
    await db_session.commit()

    class_a_assignment = ingles_assignments[seed.class_.id].id
    class_b_assignment = ingles_assignments[class_b.id].id
    executed_a = await load_executed_minutes(db_session, seed.organization.id, [class_a_assignment])
    executed_b = await load_executed_minutes(db_session, seed.organization.id, [class_b_assignment])
    assert sum(executed_a[class_a_assignment].values()) == lesson_a.credit_minutes
    assert sum(executed_b.get(class_b_assignment, {}).values()) == 0
    blocks = (
        await db_session.scalars(
            select(models.OperationalScheduleBlock).where(
                models.OperationalScheduleBlock.organization_id == seed.organization.id,
            )
        )
    ).all()
    statuses = {row.class_id: row.status for row in blocks}
    assert statuses[class_b.id] == models.OperationalBlockStatus.CANCELLED

    # Teacher week view: one collapsed block with every member's block state.
    week_start = SCHOOL_DATE - timedelta(days=SCHOOL_DATE.weekday())
    slots = await week_schedule(
        db_session,
        seed.organization.id,
        week_start=week_start,
        class_id=None,
        teacher_id=ingles_teacher.id,
        now_utc=lesson_a.ends_at,
    )
    joint = [
        slot for slot in slots if slot["block_source"] == "operational" and slot["class_infos"]
    ]
    assert len(joint) == 1
    infos = {info["id"]: info for info in joint[0]["class_infos"]}
    assert set(infos) == {seed.class_.id, class_b.id}
    assert infos[seed.class_.id]["substitute_execution_status"] == "COMPLETED"
    assert infos[class_b.id]["substitute_execution_status"] == "CANCELLED"
    assert infos[class_b.id]["operational_block_id"] is not None


async def test_substituted_without_class_ids_covers_every_member(db_session):
    seed, class_b, assignment_b, _group = await seed_joint_pair(
        db_session, clerk_user_id="joint_auto", clerk_org_id="joint_auto_org"
    )
    seed.year.timezone = "UTC"
    version = await add_version(db_session, seed, status="ACTIVE")
    lesson_a, _lesson_b = await add_joint_lesson(
        db_session, seed, assignment_b, version, stable_key="occ6"
    )
    db_session.add(
        models.Timeslot(
            organization_id=seed.organization.id,
            day_of_week=SCHOOL_DATE.weekday(),
            start_time=time(10, 0),
            end_time=time(10, 50),
        )
    )
    ingles, ingles_teacher, _module, _assignments = await add_joint_subject(
        db_session, seed, class_b, name="Inglês"
    )
    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson_a.id,
        status="OCCURRENCE",
        summary="Falta.",
        notes=None,
        now_utc=MOMENT,
    )
    await db_session.commit()
    item = (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]

    decided = await occurrences_v1.update_occurrence(
        db_session,
        seed.organization.id,
        item["id"],
        schemas.LessonOccurrenceUpdate(
            status=models.LessonOccurrenceStatus.SUBSTITUTED,
            version=item["version"],
            substitute_teacher_id=ingles_teacher.id,
            substitute_subject_id=ingles.id,
        ),
        decided_by_membership_id=seed.membership.id,
        now_utc=MOMENT,
    )
    await db_session.commit()
    assert decided["operational_state"] == "DECIDED_SUBSTITUTED"
    blocks = (
        await db_session.scalars(
            select(models.OperationalScheduleBlock).where(
                models.OperationalScheduleBlock.organization_id == seed.organization.id,
                models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
            )
        )
    ).all()
    assert len(blocks) == 2, "Sem class_ids, a substituição conjunta cobre todas as turmas."


async def test_a_foreign_member_class_is_rejected_without_effects(db_session):
    seed, class_b, assignment_b, _group = await seed_joint_pair(
        db_session, clerk_user_id="joint_foreign", clerk_org_id="joint_foreign_org"
    )
    version = await add_version(db_session, seed, status="ACTIVE")
    lesson_a, lesson_b = await add_joint_lesson(
        db_session, seed, assignment_b, version, stable_key="occ7"
    )
    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson_a.id,
        status="OCCURRENCE",
        summary="Falta.",
        notes=None,
        now_utc=MOMENT,
    )
    await db_session.commit()
    item = (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]

    with pytest.raises(AppError) as rejected:
        await occurrences_v1.update_occurrence(
            db_session,
            seed.organization.id,
            item["id"],
            schemas.LessonOccurrenceUpdate(
                status=models.LessonOccurrenceStatus.GAP,
                version=item["version"],
                class_ids=[seed.class_.id, 999_999],
            ),
            decided_by_membership_id=seed.membership.id,
            now_utc=MOMENT,
        )
    assert rejected.value.kind == "validation"
    logs = (
        await db_session.scalars(
            select(SchedulerLessonLogV1).where(
                SchedulerLessonLogV1.lesson_id.in_([lesson_a.id, lesson_b.id])
            )
        )
    ).all()
    assert {row.decision for row in logs} == {None}
    debts = await occurrences_v1.get_debts(db_session, seed.organization.id)
    assert debts["total_gaps"] == 0


async def test_cancelling_one_joint_occurrence_reverts_only_that_class(db_session):
    seed, class_b, assignment_b, _group = await seed_joint_pair(
        db_session, clerk_user_id="joint_reverse", clerk_org_id="joint_reverse_org"
    )
    version = await add_version(db_session, seed, status="ACTIVE")
    lesson_a, lesson_b = await add_joint_lesson(
        db_session, seed, assignment_b, version, stable_key="occ8"
    )
    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson_a.id,
        status="OCCURRENCE",
        summary="Falta.",
        notes=None,
        now_utc=MOMENT,
    )
    await db_session.commit()
    item = (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]
    decided = await occurrences_v1.update_occurrence(
        db_session,
        seed.organization.id,
        item["id"],
        schemas.LessonOccurrenceUpdate(
            status=models.LessonOccurrenceStatus.GAP, version=item["version"]
        ),
        decided_by_membership_id=seed.membership.id,
        now_utc=MOMENT,
    )
    await db_session.commit()

    await occurrences_v1.cancel_occurrence(
        db_session,
        seed.organization.id,
        item["id"],
        version=decided["version"],
        reason="Reversão só desta turma",
        cancelled_by_membership_id=seed.membership.id,
        now_utc=MOMENT,
    )
    await db_session.commit()

    logs = {
        row.lesson_id: row
        for row in (
            await db_session.scalars(
                select(SchedulerLessonLogV1).where(
                    SchedulerLessonLogV1.lesson_id.in_([lesson_a.id, lesson_b.id])
                )
            )
        ).all()
    }
    assert logs[lesson_a.id].status == "REVOKED"
    assert logs[lesson_b.id].status == "OCCURRENCE"
    assert logs[lesson_b.id].decision is None
    assert (await occurrences_v1.get_debts(db_session, seed.organization.id))["total_gaps"] == 0


async def test_a_per_class_version_reference_survives_a_sibling_revision_drift(db_session):
    seed, class_b, assignment_b, _group = await seed_joint_pair(
        db_session, clerk_user_id="joint_drift", clerk_org_id="joint_drift_org"
    )
    version = await add_version(db_session, seed, status="ACTIVE")
    lesson_a, lesson_b = await add_joint_lesson(
        db_session, seed, assignment_b, version, stable_key="occ9"
    )
    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson_a.id,
        status="OCCURRENCE",
        summary="Falta.",
        notes=None,
        now_utc=MOMENT,
    )
    await db_session.commit()

    item = (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]
    classes = {row["class_id"]: row for row in item["joint_lesson"]["classes"]}
    assert classes[seed.class_.id]["version"] == 1
    assert classes[class_b.id]["version"] == 1

    # Decide A with A's own occurrence id/version: A moves to revision 2.
    await occurrences_v1.update_occurrence(
        db_session,
        seed.organization.id,
        classes[seed.class_.id]["id"],
        schemas.LessonOccurrenceUpdate(
            status=models.LessonOccurrenceStatus.GAP,
            version=classes[seed.class_.id]["version"],
        ),
        decided_by_membership_id=seed.membership.id,
        now_utc=MOMENT,
    )
    await db_session.commit()

    item = (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]
    classes = {row["class_id"]: row for row in item["joint_lesson"]["classes"]}
    assert classes[seed.class_.id]["version"] == 2
    assert classes[class_b.id]["version"] == 1, "A linha não decidida mantém a revisão."

    # The frontend decides B with B's own id/version: it must succeed.
    decided = await occurrences_v1.update_occurrence(
        db_session,
        seed.organization.id,
        classes[class_b.id]["id"],
        schemas.LessonOccurrenceUpdate(
            status=models.LessonOccurrenceStatus.GAP,
            version=classes[class_b.id]["version"],
            class_ids=[class_b.id],
        ),
        decided_by_membership_id=seed.membership.id,
        now_utc=MOMENT,
    )
    await db_session.commit()
    assert decided["operational_state"] == "DECIDED_GAP"

    # A stale reference to A (old version 1) is rejected with no partial effect.
    with pytest.raises(AppError) as stale:
        await occurrences_v1.update_occurrence(
            db_session,
            seed.organization.id,
            classes[seed.class_.id]["id"],
            schemas.LessonOccurrenceUpdate(
                status=models.LessonOccurrenceStatus.GIVEN,
                version=1,
                class_ids=[seed.class_.id],
            ),
            decided_by_membership_id=seed.membership.id,
            now_utc=MOMENT,
        )
    assert stale.value.detail == "OCCURRENCE_STALE_VERSION"
    logs = {
        row.lesson_id: row
        for row in (
            await db_session.scalars(
                select(SchedulerLessonLogV1).where(
                    SchedulerLessonLogV1.lesson_id.in_([lesson_a.id, lesson_b.id])
                )
            )
        ).all()
    }
    assert logs[lesson_a.id].decision == "GAP"
    assert logs[lesson_b.id].decision == "GAP"


async def test_status_filter_keeps_a_joint_card_that_any_sibling_matches(db_session):
    seed, class_b, assignment_b, _group = await seed_joint_pair(
        db_session, clerk_user_id="joint_filter", clerk_org_id="joint_filter_org"
    )
    version = await add_version(db_session, seed, status="ACTIVE")
    lesson_a, _lesson_b = await add_joint_lesson(
        db_session, seed, assignment_b, version, stable_key="occ10"
    )
    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson_a.id,
        status="OCCURRENCE",
        summary="Falta.",
        notes=None,
        now_utc=MOMENT,
    )
    await db_session.commit()
    item = (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]
    classes = {row["class_id"]: row for row in item["joint_lesson"]["classes"]}

    # Only class A is decided: class B is still pending.
    await occurrences_v1.update_occurrence(
        db_session,
        seed.organization.id,
        classes[seed.class_.id]["id"],
        schemas.LessonOccurrenceUpdate(
            status=models.LessonOccurrenceStatus.GAP,
            version=classes[seed.class_.id]["version"],
        ),
        decided_by_membership_id=seed.membership.id,
        now_utc=MOMENT,
    )
    await db_session.commit()

    page = await occurrences_v1.list_occurrences(
        db_session, seed.organization.id, status_filter="OPEN_PENDING"
    )
    assert page["total"] == 1, "O cartão aparece pelo irmão ainda pendente."
    filtered_classes = {row["class_id"]: row for row in page["items"][0]["joint_lesson"]["classes"]}
    assert filtered_classes[class_b.id]["operational_state"] == "OPEN_PENDING"
    assert filtered_classes[seed.class_.id]["operational_state"] == "DECIDED_GAP"
