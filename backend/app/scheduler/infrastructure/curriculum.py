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


async def sync_curricular_projection(
    db: AsyncSession,
    organization_id: int,
    school_year: models.SchedulerSchoolYear,
) -> int:
    """Upsert live class/subject links and drop projections that no longer apply.

    Each link projects only its selected modules. A retired module (left the
    selection) is closed in place when it keeps execution credit, so the ledger
    stays replayable; without credit its requirement is dropped. A link with a
    teacher and no selected module cannot reach the solver and fails here.
    """
    link_rows = (
        await db.execute(
            select(models.ClassSubjectLink, models.Class.name)
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
    ).all()
    modules_by_subject: dict[int, list[models.Module]] = defaultdict(list)
    selected_by_link: dict[int, set[int]] = defaultdict(set)
    subject_names: dict[int, str] = {}
    if link_rows:
        link_ids = [link.id for link, _ in link_rows]
        subject_ids = {link.subject_id for link, _ in link_rows}
        modules = (
            await db.scalars(
                select(models.Module)
                .where(
                    models.Module.organization_id == organization_id,
                    models.Module.subject_id.in_(subject_ids),
                )
                .order_by(models.Module.subject_id, models.Module.order, models.Module.id)
            )
        ).all()
        for module in modules:
            modules_by_subject[module.subject_id].append(module)
        subject_names = dict(
            (
                await db.execute(
                    select(models.Subject.id, models.Subject.name).where(
                        models.Subject.organization_id == organization_id,
                        models.Subject.id.in_(subject_ids),
                    )
                )
            ).all()
        )
        for link_id, module_id in (
            await db.execute(
                select(
                    models.class_subject_module.c.class_subject_link_id,
                    models.class_subject_module.c.module_id,
                ).where(
                    models.class_subject_module.c.organization_id == organization_id,
                    models.class_subject_module.c.class_subject_link_id.in_(link_ids),
                )
            )
        ).all():
            selected_by_link[link_id].add(module_id)

    link_by_key = {(link.class_id, link.subject_id): link for link, _ in link_rows}
    live: dict[tuple[int, int], tuple[list[models.Module], set[int]]] = {}
    for link, class_name in link_rows:
        subject_modules = modules_by_subject.get(link.subject_id) or []
        selected_ids = selected_by_link.get(link.id, set())
        if not any(module.id in selected_ids for module in subject_modules):
            raise SnapshotConfigurationError(
                "CLASS_SUBJECT_WITHOUT_MODULES",
                f"A turma {class_name} tem a disciplina "
                f"{subject_names.get(link.subject_id, link.subject_id)} sem módulos "
                "selecionados. Remova a disciplina ou selecione pelo menos um módulo.",
            )
        live[(link.class_id, link.subject_id)] = (subject_modules, selected_ids)

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
    for key, link in link_by_key.items():
        if key not in live:
            continue
        assignment = assignments.get(key)
        if assignment is None:
            assignment = CurricularAssignment(
                organization_id=organization_id,
                school_year_id=school_year.id,
                class_id=key[0],
                subject_id=key[1],
                teacher_id=link.teacher_id,
            )
            db.add(assignment)
            await db.flush()
            assignments[key] = assignment
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
    credited = await _credited_modules(db, organization_id, list(assignment_by_id))

    for (class_id, subject_id), (subject_modules, selected_ids) in live.items():
        assignment = assignments[(class_id, subject_id)]
        stored = requirements[assignment.id]
        has_credit = credited.get(assignment.id, set())
        for module in subject_modules:
            requirement = stored.get(module.id)
            sequence = module.order + 1
            if module.id in selected_ids:
                if requirement is None:
                    db.add(
                        CurricularRequirement(
                            organization_id=organization_id,
                            assignment_id=assignment.id,
                            module_id=module.id,
                            sequence=sequence,
                            required_minutes=module.required_minutes,
                            planned=True,
                        )
                    )
                else:
                    requirement.sequence = sequence
                    requirement.required_minutes = module.required_minutes
                    requirement.planned = True
            elif requirement is not None and module.id in has_credit:
                requirement.sequence = sequence
                requirement.required_minutes = module.required_minutes
                requirement.planned = False
            elif requirement is not None:
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


async def _credited_modules(
    db: AsyncSession, organization_id: int, assignment_ids: list[int]
) -> dict[int, set[int]]:
    """Module IDs with at least one execution credit, per assignment."""
    credited: dict[int, set[int]] = defaultdict(set)
    if not assignment_ids:
        return credited
    rows = (
        await db.execute(
            select(CurricularExecution.assignment_id, CurricularExecutionCredit.module_id)
            .join(
                CurricularExecutionCredit,
                CurricularExecutionCredit.execution_id == CurricularExecution.id,
            )
            .where(
                CurricularExecution.organization_id == organization_id,
                CurricularExecution.assignment_id.in_(assignment_ids),
                CurricularExecutionCredit.organization_id == organization_id,
            )
            .distinct()
        )
    ).all()
    for assignment_id, module_id in rows:
        credited[assignment_id].add(module_id)
    return credited


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
