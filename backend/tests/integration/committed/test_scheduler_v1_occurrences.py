"""R89.08: the administrative occurrence page uses the v1 ledger as truth."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app import models, schemas
from app.scheduler.infrastructure import occurrences as occurrences_v1
from app.scheduler.infrastructure.models import (
    CurricularAssignment,
    CurricularRequirement,
    SchedulerLessonV1,
)
from app.scheduler.infrastructure.operations import record_lesson_log
from app.scheduler.infrastructure.progress import load_executed_minutes, load_open_debt
from tests._support.db_fixtures import create_teacher_profile
from tests._support.scheduler_v1 import (
    MOMENT,
    V1Seed,
    publish_schedule,
    seed_generatable_school,
)

pytestmark = pytest.mark.postgresql


async def _school(db_session, *, suffix: str = "") -> V1Seed:
    return await seed_generatable_school(
        db_session,
        clerk_user_id=f"w09_occ_a{suffix}",
        clerk_org_id=f"w09_occ_org{suffix}",
        module_minutes=100,
    )


async def _lessons(db_session, seed: V1Seed) -> list[SchedulerLessonV1]:
    return list(
        (
            await db_session.scalars(
                select(SchedulerLessonV1)
                .where(SchedulerLessonV1.organization_id == seed.organization.id)
                .order_by(SchedulerLessonV1.school_date, SchedulerLessonV1.id)
            )
        ).all()
    )


async def _second_assignment(db_session, seed: V1Seed):
    subject = models.Subject(name="Matemática", organization_id=seed.organization.id)
    db_session.add(subject)
    await db_session.flush()
    module = models.Module(
        organization_id=seed.organization.id,
        subject_id=subject.id,
        name="Módulo M",
        required_minutes=100,
        order=1,
    )
    teacher = await create_teacher_profile(
        db_session, organization_id=seed.organization.id, name="Prof. Matemática"
    )
    db_session.add(module)
    await db_session.flush()
    assignment = CurricularAssignment(
        organization_id=seed.organization.id,
        school_year_id=seed.year.id,
        class_id=seed.class_.id,
        subject_id=subject.id,
        teacher_id=teacher.id,
    )
    db_session.add(assignment)
    await db_session.flush()
    db_session.add(
        CurricularRequirement(
            organization_id=seed.organization.id,
            assignment_id=assignment.id,
            module_id=module.id,
            sequence=1,
            required_minutes=100,
        )
    )
    await db_session.commit()
    return subject, module, teacher, assignment


async def _occurrence(db_session, seed: V1Seed, lesson: SchedulerLessonV1) -> None:
    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson.id,
        status="OCCURRENCE",
        summary="Falta registada.",
        notes=None,
        now_utc=MOMENT,
        planning_relevant=True,
    )
    await db_session.commit()


async def test_a_v1_occurrence_is_listed_and_decided_as_given(db_session, monkeypatch):
    seed = await _school(db_session)
    await db_session.commit()
    await publish_schedule(db_session, monkeypatch, seed)
    lessons = await _lessons(db_session, seed)
    await _occurrence(db_session, seed, lessons[0])

    page = await occurrences_v1.list_occurrences(db_session, seed.organization.id)
    assert page["total"] == 1
    item = page["items"][0]
    assert item["operational_state"] == "OPEN_PENDING"
    assert item["class_id"] == seed.class_.id
    assert item["subject_id"] == seed.subject.id

    decided = await occurrences_v1.update_occurrence(
        db_session,
        seed.organization.id,
        item["id"],
        schemas.LessonOccurrenceUpdate(
            status=models.LessonOccurrenceStatus.GIVEN,
            version=item["version"],
        ),
        decided_by_membership_id=seed.membership.id,
        now_utc=MOMENT,
    )
    await db_session.commit()
    assert decided["status"] == "GIVEN"
    assert decided["operational_state"] == "DECIDED_GIVEN"

    pending = await occurrences_v1.list_occurrences(
        db_session, seed.organization.id, status_filter="OPEN_PENDING"
    )
    assert pending["total"] == 0
    debts = await occurrences_v1.get_debts(db_session, seed.organization.id)
    assert debts["total_gaps"] == 0
    open_debt, _ = await load_open_debt(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(open_debt.values()) == 0
    executed = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(executed[seed.assignment.id].values()) == lessons[0].credit_minutes


async def test_a_substitution_credits_the_substitute_subject_and_keeps_the_debt(
    db_session, monkeypatch
):
    seed = await _school(db_session, suffix="_sub")
    await db_session.commit()
    await publish_schedule(db_session, monkeypatch, seed)
    lessons = await _lessons(db_session, seed)
    subject, _module, teacher, assignment = await _second_assignment(db_session, seed)
    await _occurrence(db_session, seed, lessons[0])

    recommendations = await occurrences_v1.get_substitute_recommendations(
        db_session,
        seed.organization.id,
        (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]["id"],
    )
    assert recommendations, "O substituto elegível deve ser recomendado."
    assert {row["teacher_id"] for row in recommendations} == {teacher.id}
    assert {row["subject_id"] for row in recommendations} == {subject.id}

    page = await occurrences_v1.list_occurrences(db_session, seed.organization.id)
    item = page["items"][0]
    decided = await occurrences_v1.update_occurrence(
        db_session,
        seed.organization.id,
        item["id"],
        schemas.LessonOccurrenceUpdate(
            status=models.LessonOccurrenceStatus.SUBSTITUTED,
            version=item["version"],
            substitute_teacher_id=teacher.id,
            substitute_subject_id=subject.id,
        ),
        decided_by_membership_id=seed.membership.id,
        now_utc=MOMENT,
    )
    await db_session.commit()
    assert decided["status"] == "SUBSTITUTED"
    assert decided["operational_state"] == "DECIDED_SUBSTITUTED"
    assert decided["substitute_teacher_id"] == teacher.id
    assert decided["hours_given"] == lessons[0].credit_minutes / 60

    executed = await load_executed_minutes(db_session, seed.organization.id, [assignment.id])
    assert sum(executed[assignment.id].values()) == lessons[0].credit_minutes
    open_debt, _ = await load_open_debt(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(open_debt.values()) == lessons[0].credit_minutes

    debts = await occurrences_v1.get_debts(db_session, seed.organization.id)
    assert debts["total_gaps"] == 1
    assert debts["items"][0]["subject_id"] == seed.subject.id
    assert debts["items"][0]["hours_owed"] == lessons[0].credit_minutes / 60

    cancelled = await occurrences_v1.cancel_occurrence(
        db_session,
        seed.organization.id,
        item["id"],
        version=decided["version"],
        reason="Reversão administrativa",
        cancelled_by_membership_id=seed.membership.id,
        now_utc=MOMENT,
    )
    await db_session.commit()
    assert cancelled["cancelled"] is True
    executed = await load_executed_minutes(db_session, seed.organization.id, [assignment.id])
    assert sum(executed[assignment.id].values()) == 0
    open_debt, _ = await load_open_debt(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(open_debt.values()) == 0
    final_page = await occurrences_v1.list_occurrences(db_session, seed.organization.id)
    assert final_page["items"][0]["status"] == "REVOKED"
    assert final_page["items"][0]["is_active"] is False
    debts = await occurrences_v1.get_debts(db_session, seed.organization.id)
    assert debts["total_gaps"] == 0


async def test_open_debts_aggregate_occurrence_claims(db_session, monkeypatch):
    seed = await _school(db_session, suffix="_debts")
    await db_session.commit()
    await publish_schedule(db_session, monkeypatch, seed)
    lessons = await _lessons(db_session, seed)
    await _occurrence(db_session, seed, lessons[0])
    await _occurrence(db_session, seed, lessons[1])

    debts = await occurrences_v1.get_debts(db_session, seed.organization.id)
    assert debts["total_gaps"] == 2
    assert len(debts["items"]) == 1
    assert debts["items"][0]["gap_occurrences"] == 2
    assert debts["items"][0]["hours_owed"] == 2 * lessons[0].credit_minutes / 60
    overdue = await occurrences_v1.get_debts(db_session, seed.organization.id)
    assert overdue["total_gaps_overdue"] == 2


async def test_recommendations_exclude_the_planned_teacher_and_subject(db_session, monkeypatch):
    seed = await _school(db_session, suffix="_recs")
    await db_session.commit()
    await publish_schedule(db_session, monkeypatch, seed)
    lessons = await _lessons(db_session, seed)
    await _second_assignment(db_session, seed)
    await _occurrence(db_session, seed, lessons[0])

    page = await occurrences_v1.list_occurrences(db_session, seed.organization.id)
    recommendations = await occurrences_v1.get_substitute_recommendations(
        db_session, seed.organization.id, page["items"][0]["id"]
    )
    assert recommendations
    for row in recommendations:
        assert row["teacher_id"] != seed.assignment.teacher_id
        assert row["subject_id"] != seed.subject.id
