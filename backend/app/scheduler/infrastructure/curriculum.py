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
    CurricularExecutionCredit,
    CurricularRequirement,
    SchedulerLessonV1,
    SchedulerRecoveryReservationV1,
)
from app.scheduler.infrastructure.snapshot import SnapshotConfigurationError

# Temporary offset used while re-sequencing requirements in place.
SEQUENCE_OFFSET = 1_000_000


async def sync_curricular_projection(
    db: AsyncSession,
    organization_id: int,
    school_year: models.SchedulerSchoolYear,
) -> int:
    """Upsert live class/subject links and drop projections that no longer apply.

    The projection follows the selected modules of each link. A module
    deselected with executed credits keeps a ``planned = false`` row so its
    history stays reproducible; a module deselected without credits is deleted.
    An active link (teacher assigned, in range and not archived) without
    selected modules blocks generation with ``CLASS_SUBJECT_WITHOUT_MODULES``.
    A removed link loses its assignment only when no scheduler row references
    it; referenced history is preserved and stays visible to the records.
    """
    links = (
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
    if links:
        modules = (
            await db.scalars(
                select(models.Module)
                .where(
                    models.Module.organization_id == organization_id,
                    models.Module.subject_id.in_({link.subject_id for link in links}),
                )
                .order_by(models.Module.subject_id, models.Module.order, models.Module.id)
            )
        ).all()
        for module in modules:
            modules_by_subject[module.subject_id].append(module)

    selected_by_link: dict[int, set[int]] = defaultdict(set)
    if links:
        selection_rows = await db.execute(
            select(
                models.class_subject_module.c.class_subject_link_id,
                models.class_subject_module.c.module_id,
            ).where(
                models.class_subject_module.c.organization_id == organization_id,
                models.class_subject_module.c.class_subject_link_id.in_(
                    [link.id for link in links]
                ),
            )
        )
        for link_id, module_id in selection_rows.all():
            selected_by_link[link_id].add(module_id)

    for link in links:
        if not selected_by_link.get(link.id):
            raise SnapshotConfigurationError(
                "CLASS_SUBJECT_WITHOUT_MODULES",
                "A class subject has no selected modules. Remove the subject or "
                "select at least one module.",
                public_context={"class_id": link.class_id, "subject_id": link.subject_id},
            )

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
    live: dict[tuple[int, int], models.ClassSubjectLink] = {}
    for link in links:
        live[(link.class_id, link.subject_id)] = link
        assignment = assignments.get((link.class_id, link.subject_id))
        if assignment is None:
            assignment = CurricularAssignment(
                organization_id=organization_id,
                school_year_id=school_year.id,
                class_id=link.class_id,
                subject_id=link.subject_id,
                teacher_id=link.teacher_id,
            )
            db.add(assignment)
            await db.flush()
            assignments[(link.class_id, link.subject_id)] = assignment
        elif assignment.teacher_id != link.teacher_id:
            assignment.teacher_id = link.teacher_id

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

    credited_by_assignment: dict[int, set[int]] = defaultdict(set)
    if assignment_by_id:
        credited_rows = await db.execute(
            select(CurricularExecution.assignment_id, CurricularExecutionCredit.module_id)
            .join(
                CurricularExecutionCredit,
                CurricularExecutionCredit.execution_id == CurricularExecution.id,
            )
            .where(
                CurricularExecution.organization_id == organization_id,
                CurricularExecution.assignment_id.in_(list(assignment_by_id)),
            )
        )
        for assignment_id, module_id in credited_rows.all():
            credited_by_assignment[assignment_id].add(module_id)

    # Re-sequence in two phases: moving every stored row out of the final
    # sequence range first avoids a transient (assignment_id, sequence)
    # collision when several rows shift at once.
    stored_live = [
        requirement for key in live for requirement in requirements[assignments[key].id].values()
    ]
    for requirement in stored_live:
        requirement.sequence += SEQUENCE_OFFSET
    if stored_live:
        await db.flush()

    for key, link in live.items():
        assignment = assignments[key]
        stored = requirements[assignment.id]
        selected_ids = selected_by_link.get(link.id, set())
        credited_ids = credited_by_assignment.get(assignment.id, set())
        kept_ids: set[int] = set()
        for module in modules_by_subject.get(link.subject_id, []):
            if module.id in selected_ids:
                planned = True
            elif module.id in credited_ids:
                planned = False
            else:
                continue
            kept_ids.add(module.id)
            requirement = stored.get(module.id)
            if requirement is None:
                db.add(
                    CurricularRequirement(
                        organization_id=organization_id,
                        assignment_id=assignment.id,
                        module_id=module.id,
                        sequence=module.order + 1,
                        required_minutes=module.required_minutes,
                        planned=planned,
                    )
                )
            else:
                requirement.sequence = module.order + 1
                requirement.required_minutes = module.required_minutes
                requirement.planned = planned
        for module_id, requirement in stored.items():
            if module_id not in kept_ids:
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
