"""WBS 2.6.3-2.6.6: engine readers ignore retired modules.

A module deselected on a class/subject link keeps a ``planned = false``
requirement row when it has executed history. No planning reader may credit it
again or count its catalogue minutes. These tests are red before the readers
use the planning view and green after.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import delete, select, update

from app import models, schemas
from app.scheduler.domain.debt import DebtOrigin
from app.scheduler.infrastructure import occurrences as occurrences_v1
from app.scheduler.infrastructure import operations
from app.scheduler.infrastructure.models import (
    CurricularAssignment,
    CurricularExecution,
    CurricularExecutionCredit,
    CurricularRequirement,
    SchedulerLessonV1,
)
from app.scheduler.infrastructure.operations import OperationsError, record_lesson_log
from app.scheduler.infrastructure.progress import (
    load_executed_minutes,
    record_debt,
    settle_open_debt,
)
from app.services import dashboard_service, grid_change_service
from tests._support.db_fixtures import create_teacher_profile
from tests._support.scheduler_v1 import (
    MOMENT,
    V1Seed,
    seed_generatable_school,
    seed_published_baseline,
    seed_v1_assignment,
)

pytestmark = pytest.mark.postgresql


async def _retire(db_session, assignment_id: int, module_id: int) -> None:
    # Deselect on the live class/subject link (the authoritative selection) and
    # close the persisted requirement at its executed minutes.
    assignment = await db_session.get(CurricularAssignment, assignment_id)
    if assignment is not None:
        link_id = await db_session.scalar(
            select(models.ClassSubjectLink.id).where(
                models.ClassSubjectLink.organization_id == assignment.organization_id,
                models.ClassSubjectLink.class_id == assignment.class_id,
                models.ClassSubjectLink.subject_id == assignment.subject_id,
            )
        )
        if link_id is not None:
            await db_session.execute(
                delete(models.class_subject_module).where(
                    models.class_subject_module.c.organization_id == assignment.organization_id,
                    models.class_subject_module.c.class_subject_link_id == link_id,
                    models.class_subject_module.c.module_id == module_id,
                )
            )
    await db_session.execute(
        update(CurricularRequirement)
        .where(
            CurricularRequirement.assignment_id == assignment_id,
            CurricularRequirement.module_id == module_id,
        )
        .values(planned=False)
    )
    await db_session.commit()


async def test_dashboard_progress_ignores_a_retired_requirement(db_session):
    seed = await seed_v1_assignment(db_session, module_minutes=120)
    await _retire(db_session, seed.assignment.id, seed.module.id)

    progress = await db_session.run_sync(
        lambda db: dashboard_service._get_class_progress(db, seed.organization.id)
    )

    assert len(progress) == 1
    assert progress[0].class_id == seed.class_.id
    assert progress[0].total_hours == 0.0
    assert progress[0].completed_hours == 0.0


async def test_grid_canonical_minutes_ignore_a_retired_requirement(db_session):
    seed = await seed_v1_assignment(db_session, module_minutes=120)
    await _retire(db_session, seed.assignment.id, seed.module.id)

    completed, protected, after_boundary, required = await grid_change_service._canonical_minutes(
        db_session,
        seed.organization.id,
        first_editable=date(2026, 9, 1),
        school_today=date(2026, 9, 1),
    )

    assert required == 0
    assert completed == 0
    assert protected == 0
    assert after_boundary == 0


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


async def _substitute_assignment(
    db_session,
    seed: V1Seed,
    *,
    planned_minutes: int,
    retired_minutes: int,
) -> tuple[
    models.Subject,
    models.Teacher,
    CurricularAssignment,
    models.Module | None,
    models.Module | None,
]:
    subject = models.Subject(
        name=f"Substituto {planned_minutes}/{retired_minutes}",
        organization_id=seed.organization.id,
    )
    db_session.add(subject)
    await db_session.flush()
    teacher = await create_teacher_profile(
        db_session,
        organization_id=seed.organization.id,
        name=f"Substituto {planned_minutes}/{retired_minutes}",
    )
    assignment = CurricularAssignment(
        organization_id=seed.organization.id,
        school_year_id=seed.year.id,
        class_id=seed.class_.id,
        subject_id=subject.id,
        teacher_id=teacher.id,
    )
    db_session.add(assignment)
    await db_session.flush()
    sequence = 1
    planned_module = None
    if planned_minutes:
        planned_module = models.Module(
            organization_id=seed.organization.id,
            subject_id=subject.id,
            name="Planeado",
            required_minutes=planned_minutes,
            order=0,
        )
        db_session.add(planned_module)
        await db_session.flush()
        db_session.add(
            CurricularRequirement(
                organization_id=seed.organization.id,
                assignment_id=assignment.id,
                module_id=planned_module.id,
                sequence=sequence,
                required_minutes=planned_minutes,
            )
        )
        sequence += 1
    retired_module = None
    if retired_minutes:
        retired_module = models.Module(
            organization_id=seed.organization.id,
            subject_id=subject.id,
            name="Retirado",
            required_minutes=retired_minutes,
            order=1,
        )
        db_session.add(retired_module)
        await db_session.flush()
        db_session.add(
            CurricularRequirement(
                organization_id=seed.organization.id,
                assignment_id=assignment.id,
                module_id=retired_module.id,
                sequence=sequence,
                required_minutes=retired_minutes,
                planned=False,
            )
        )
    await db_session.commit()
    return subject, teacher, assignment, planned_module, retired_module


async def _substituted_lesson(db_session, suffix: str):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id=f"selection_readers{suffix}",
        clerk_org_id=f"selection_readers_org{suffix}",
        module_minutes=50,
    )
    await db_session.commit()
    await seed_published_baseline(db_session, seed)
    lesson = (await _lessons(db_session, seed))[0]
    await _occurrence(db_session, seed, lesson)
    item = (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]
    return seed, lesson, item


async def test_substitution_capacity_ignores_a_retired_module(db_session, monkeypatch):
    seed, _lesson, item = await _substituted_lesson(db_session, "_capacity")
    _subject, teacher, _assignment, _planned, retired = await _substitute_assignment(
        db_session, seed, planned_minutes=30, retired_minutes=100
    )
    assert retired is not None

    diagnostics = await occurrences_v1.get_substitute_diagnostics(
        db_session, seed.organization.id, item["id"]
    )
    candidate = next(row for row in diagnostics["candidates"] if row["teacher_id"] == teacher.id)

    assert candidate["eligible"] is False
    assert "no_capacity" in {exclusion["code"] for exclusion in candidate["exclusions"]}


async def test_substitution_log_does_not_credit_a_retired_subject(db_session, monkeypatch):
    seed, lesson, item = await _substituted_lesson(db_session, "_credit")
    subject, teacher, assignment, planned, retired = await _substitute_assignment(
        db_session, seed, planned_minutes=100, retired_minutes=100
    )
    assert planned is not None and retired is not None

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

    # Deselect the planned module after planning but before the log completes.
    await _retire(db_session, assignment.id, planned.id)

    with pytest.raises(OperationsError) as raised:
        await operations.record_operational_lesson_log(
            db_session,
            seed.organization.id,
            membership_id=seed.membership.id,
            operational_block_id=decided["substitute_block_id"],
            payload=schemas.LessonLogCreate(
                status=models.LessonLogStatus.COMPLETED, summary="Substituta dada.", notes=None
            ),
            now_utc=lesson.ends_at,
        )

    assert raised.value.code == "substitute_without_requirements"
    executed = await load_executed_minutes(db_session, seed.organization.id, [assignment.id])
    assert sum(executed.get(assignment.id, {}).values()) == 0


async def test_year_reset_settlement_does_not_credit_a_retired_module(db_session):
    seed = await seed_v1_assignment(db_session, module_minutes=50)
    retired = models.Module(
        organization_id=seed.organization.id,
        subject_id=seed.subject.id,
        name="Retirado",
        required_minutes=100,
        order=2,
    )
    db_session.add(retired)
    await db_session.flush()
    db_session.add(
        CurricularRequirement(
            organization_id=seed.organization.id,
            assignment_id=seed.assignment.id,
            module_id=retired.id,
            sequence=2,
            required_minutes=100,
            planned=False,
        )
    )
    # A retired module keeps its history: one executed credit keeps the closed
    # row when the live selection is reconciled.
    execution = CurricularExecution(
        organization_id=seed.organization.id,
        assignment_id=seed.assignment.id,
        origin="retired-history",
        revision=1,
        author_membership_id=seed.membership.id,
        reason="Histórico do módulo retirado",
        recorded_at=MOMENT,
        planning_relevant=True,
    )
    db_session.add(execution)
    await db_session.flush()
    db_session.add(
        CurricularExecutionCredit(
            organization_id=seed.organization.id,
            execution_id=execution.id,
            module_id=retired.id,
            offset_minutes=0,
            delta_minutes=20,
        )
    )
    await db_session.commit()

    await record_debt(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        DebtOrigin(
            "occurrence:retired",
            1,
            date(2026, 9, 22),
            80,
            seed.membership.id,
            "Missed lesson",
            recorded_at=MOMENT,
        ),
    )
    await db_session.commit()

    with pytest.raises(ValueError, match="Open debt exceeds"):
        await settle_open_debt(
            db_session,
            seed.organization.id,
            seed.year.id,
            seed.assignment.id,
            membership_id=seed.membership.id,
            reason="school_year_reset",
            now_utc=MOMENT,
        )
