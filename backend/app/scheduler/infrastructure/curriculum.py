"""Materialize product curriculum data into the v1 planning tables.

The product configures classes, subjects, modules and teacher links. The v1
engine plans from ``CurricularAssignment`` and ``CurricularRequirement``, so
every generation request rebuilds that projection from the live links before
the snapshot is captured. The rebuild is idempotent and stays in the caller's
transaction.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.scheduler.infrastructure.models import (
    CurricularAssignment,
    CurricularDebt,
    CurricularExecution,
    CurricularRequirement,
    SchedulerLessonV1,
    SchedulerRecoveryReservationV1,
)


async def sync_curricular_projection(
    db: AsyncSession,
    organization_id: int,
    school_year: models.SchedulerSchoolYear,
) -> int:
    """Upsert live class/subject links and drop projections that no longer apply.

    A link without modules is skipped: it cannot produce a valid requirement.
    A removed link loses its assignment only when no scheduler row references
    it; referenced history is preserved and stays visible to the records.
    """
    rows = (
        (
            await db.execute(
                select(models.ClassSubjectLink)
                .join(
                    models.Class,
                    (models.Class.organization_id == models.ClassSubjectLink.organization_id)
                    & (models.Class.id == models.ClassSubjectLink.class_id),
                )
                .where(
                    models.ClassSubjectLink.organization_id == organization_id,
                    models.ClassSubjectLink.teacher_id.is_not(None),
                    models.ClassSubjectLink.grade_level == models.Class.grade_level,
                    models.Class.is_archived.is_(False),
                    models.Class.start_year <= school_year.start_date.year,
                    models.Class.end_year >= school_year.start_date.year,
                )
                .order_by(models.ClassSubjectLink.class_id, models.ClassSubjectLink.subject_id)
            )
        )
        .scalars()
        .all()
    )
    modules_by_subject: dict[int, list[models.Module]] = defaultdict(list)
    if rows:
        modules = (
            await db.scalars(
                select(models.Module)
                .where(
                    models.Module.organization_id == organization_id,
                    models.Module.subject_id.in_({row.subject_id for row in rows}),
                )
                .order_by(models.Module.subject_id, models.Module.order, models.Module.id)
            )
        ).all()
        for module in modules:
            modules_by_subject[module.subject_id].append(module)

    assignments = {
        (row.class_id, row.subject_id): row
        for row in (
            await db.scalars(
                select(CurricularAssignment).where(
                    CurricularAssignment.organization_id == organization_id,
                    CurricularAssignment.school_year_id == school_year.id,
                )
            )
        ).all()
    }
    live: dict[tuple[int, int], list[models.Module]] = {}
    for row in rows:
        subject_modules = modules_by_subject.get(row.subject_id) or []
        if not subject_modules:
            continue
        live[(row.class_id, row.subject_id)] = subject_modules
        assignment = assignments.get((row.class_id, row.subject_id))
        if assignment is None:
            assignment = CurricularAssignment(
                organization_id=organization_id,
                school_year_id=school_year.id,
                class_id=row.class_id,
                subject_id=row.subject_id,
                teacher_id=row.teacher_id,
            )
            db.add(assignment)
            await db.flush()
            assignments[(row.class_id, row.subject_id)] = assignment
        elif assignment.teacher_id != row.teacher_id:
            assignment.teacher_id = row.teacher_id

    assignment_by_id = {row.id: row for row in assignments.values()}
    requirement_rows = (
        await db.scalars(
            select(CurricularRequirement).where(
                CurricularRequirement.organization_id == organization_id,
                CurricularRequirement.assignment_id.in_(list(assignment_by_id)),
            )
        )
    ).all()
    requirements: dict[int, dict[int, CurricularRequirement]] = defaultdict(dict)
    for requirement in requirement_rows:
        requirements[requirement.assignment_id][requirement.module_id] = requirement

    for (class_id, subject_id), subject_modules in live.items():
        assignment = assignments[(class_id, subject_id)]
        stored = requirements[assignment.id]
        live_module_ids = set()
        for sequence, module in enumerate(subject_modules, start=1):
            live_module_ids.add(module.id)
            requirement = stored.get(module.id)
            if requirement is None:
                db.add(
                    CurricularRequirement(
                        organization_id=organization_id,
                        assignment_id=assignment.id,
                        module_id=module.id,
                        sequence=sequence,
                        required_minutes=module.required_minutes,
                    )
                )
            else:
                requirement.sequence = sequence
                requirement.required_minutes = module.required_minutes
        for module_id, requirement in stored.items():
            if module_id not in live_module_ids:
                await db.delete(requirement)

    for key, assignment in assignments.items():
        if key in live:
            continue
        if await _assignment_has_history(db, organization_id, assignment.id):
            continue
        await db.execute(
            delete(CurricularRequirement).where(
                CurricularRequirement.organization_id == organization_id,
                CurricularRequirement.assignment_id == assignment.id,
            )
        )
        await db.delete(assignment)
    await db.flush()
    return len(live)


async def _assignment_has_history(
    db: AsyncSession, organization_id: int, assignment_id: int
) -> bool:
    for model in (
        SchedulerLessonV1,
        CurricularExecution,
        CurricularDebt,
        SchedulerRecoveryReservationV1,
    ):
        found = await db.scalar(
            select(
                exists().where(
                    model.organization_id == organization_id, model.assignment_id == assignment_id
                )
            )
        )
        if found:
            return True
    return False
