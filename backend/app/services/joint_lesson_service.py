"""Joint lesson group configuration service (WBS 4.3-4.5).

Loads the data, calls the pure rules in :mod:`joint_lesson_policy`, and writes
the group, its member links and its joint modules in one transaction. Every
tenant query filters by ``organization_id`` and the forced RLS backs it up.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.core.exceptions import AppError
from app.scheduler.infrastructure.models import CurricularAssignment
from app.scheduler.infrastructure.progress import load_executed_minutes
from app.services import joint_lesson_policy as policy
from app.services.scheduler_state_service import SchedulerStateService, record_scheduler_change

JOINT_ENTITY_TYPE = "JOINT_LESSON_GROUP"
_STARTED_CODES = (policy.JOINT_MODULE_STARTED, policy.JOINT_CLASS_STARTED)


def _raise_violation(violation: policy.JointRuleViolation) -> None:
    kind = "conflict" if violation.code in _STARTED_CODES else "bad_request"
    raise AppError(kind=kind, code=violation.code, detail=violation.message)


def _not_found(detail: str) -> AppError:
    return AppError(kind="not_found", code="resource_not_found", detail=detail)


def _snapshot(
    subject_id: int,
    class_ids: list[int],
    module_ids: list[int],
    teacher_id: int | None,
) -> dict:
    return {
        "subject_id": subject_id,
        "class_ids": sorted(class_ids),
        "module_ids": sorted(module_ids),
        "teacher_id": teacher_id,
    }


async def _load_subject(db: AsyncSession, organization_id: int, subject_id: int):
    subject = await db.scalar(
        select(models.Subject).where(
            models.Subject.id == subject_id,
            models.Subject.organization_id == organization_id,
            models.Subject.is_archived.is_(False),
        )
    )
    if subject is None:
        raise _not_found(f"Subject {subject_id} was not found in organization {organization_id}.")
    return subject


async def _load_group(
    db: AsyncSession, organization_id: int, group_id: int, *, for_update: bool = False
):
    query = select(models.JointLessonGroup).where(
        models.JointLessonGroup.id == group_id,
        models.JointLessonGroup.organization_id == organization_id,
    )
    if for_update:
        query = query.with_for_update()
    group = await db.scalar(query)
    if group is None:
        raise _not_found(
            f"Joint lesson group {group_id} was not found in organization {organization_id}."
        )
    return group


async def _module_names(db: AsyncSession, organization_id: int, subject_id: int) -> dict[int, str]:
    rows = await db.execute(
        select(models.Module.id, models.Module.name).where(
            models.Module.organization_id == organization_id,
            models.Module.subject_id == subject_id,
        )
    )
    return {module_id: name for module_id, name in rows.all()}


async def _eligible_teacher_ids(
    db: AsyncSession, organization_id: int, subject_id: int
) -> frozenset[int]:
    rows = await db.execute(
        select(models.teacher_subject_link.c.teacher_id)
        .join(
            models.Teacher,
            models.Teacher.id == models.teacher_subject_link.c.teacher_id,
        )
        .join(
            models.OrganizationMembership,
            models.OrganizationMembership.id == models.Teacher.organization_membership_id,
        )
        .where(
            models.teacher_subject_link.c.organization_id == organization_id,
            models.teacher_subject_link.c.subject_id == subject_id,
            models.Teacher.organization_id == organization_id,
            models.OrganizationMembership.organization_id == organization_id,
            models.OrganizationMembership.lifecycle_status
            == models.MembershipLifecycleStatus.active,
            models.OrganizationMembership.can_teach.is_(True),
        )
    )
    return frozenset(row[0] for row in rows.all())


async def _selected_modules_by_link(
    db: AsyncSession, organization_id: int, link_ids: list[int]
) -> dict[int, set[int]]:
    selected: dict[int, set[int]] = defaultdict(set)
    if not link_ids:
        return selected
    rows = await db.execute(
        select(
            models.class_subject_module.c.class_subject_link_id,
            models.class_subject_module.c.module_id,
        ).where(
            models.class_subject_module.c.organization_id == organization_id,
            models.class_subject_module.c.class_subject_link_id.in_(link_ids),
        )
    )
    for link_id, module_id in rows.all():
        selected[link_id].add(module_id)
    return selected


async def _joined_group_by_link(
    db: AsyncSession, organization_id: int, link_ids: list[int]
) -> dict[int, int]:
    if not link_ids:
        return {}
    rows = await db.execute(
        select(
            models.joint_lesson_group_member.c.class_subject_link_id,
            models.joint_lesson_group_member.c.group_id,
        ).where(
            models.joint_lesson_group_member.c.organization_id == organization_id,
            models.joint_lesson_group_member.c.class_subject_link_id.in_(link_ids),
        )
    )
    return {link_id: group_id for link_id, group_id in rows.all()}


async def _started_modules_by_class(
    db: AsyncSession,
    organization_id: int,
    class_ids: list[int],
    subject_id: int,
) -> dict[int, set[int]]:
    """Executed modules per class, scoped to the active school-year projection.

    Only the current school year counts as "started" (J19); progress from a
    previous year must not lock the current joint lesson.
    """
    if not class_ids:
        return {}
    school_year = await SchedulerStateService(db).get_active_school_year(organization_id)
    if school_year is None:
        return {}
    rows = await db.execute(
        select(CurricularAssignment.id, CurricularAssignment.class_id).where(
            CurricularAssignment.organization_id == organization_id,
            CurricularAssignment.school_year_id == school_year.id,
            CurricularAssignment.subject_id == subject_id,
            CurricularAssignment.class_id.in_(class_ids),
        )
    )
    assignment_class = {assignment_id: class_id for assignment_id, class_id in rows.all()}
    executed = await load_executed_minutes(db, organization_id, list(assignment_class))
    started: dict[int, set[int]] = defaultdict(set)
    for assignment_id, modules in executed.items():
        class_id = assignment_class.get(assignment_id)
        if class_id is None:
            continue
        for module_id, minutes in modules.items():
            if minutes > 0:
                started[class_id].add(module_id)
    return started


def _distinct(ids: list[int], field: str) -> list[int]:
    if len(set(ids)) != len(ids):
        raise AppError(
            kind="bad_request",
            code="bad_request",
            detail=f"{field} must not contain duplicates.",
        )
    return ids


async def _link_ids_for_classes(
    db: AsyncSession,
    organization_id: int,
    subject_id: int,
    class_ids: list[int],
) -> list[int]:
    """Link ids for the requested classes at their current grade, for locking."""
    if not class_ids:
        return []
    rows = await db.execute(
        select(models.ClassSubjectLink.id)
        .join(models.Class, models.Class.id == models.ClassSubjectLink.class_id)
        .where(
            models.ClassSubjectLink.organization_id == organization_id,
            models.ClassSubjectLink.subject_id == subject_id,
            models.ClassSubjectLink.class_id.in_(class_ids),
            models.ClassSubjectLink.grade_level == models.Class.grade_level,
        )
    )
    return [row[0] for row in rows.all()]


async def _validate_modules(
    db: AsyncSession,
    organization_id: int,
    subject_id: int,
    module_ids: list[int],
) -> dict[int, str]:
    """Tenant and subject checks for the requested modules (404/400, not policy)."""
    if not module_ids:
        return {}
    rows = await db.execute(
        select(models.Module.id, models.Module.subject_id, models.Module.name).where(
            models.Module.organization_id == organization_id,
            models.Module.id.in_(module_ids),
        )
    )
    found = {row.id: (row.subject_id, row.name) for row in rows.all()}
    missing = [module_id for module_id in module_ids if module_id not in found]
    if missing:
        raise _not_found(f"Module {missing[0]} was not found in organization {organization_id}.")
    wrong_subject = [module_id for module_id in module_ids if found[module_id][0] != subject_id]
    if wrong_subject:
        raise AppError(
            kind="bad_request",
            code="bad_request",
            detail=f"Module {wrong_subject[0]} does not belong to subject {subject_id}.",
        )
    return {module_id: found[module_id][1] for module_id in module_ids}


async def _validate_teacher(db: AsyncSession, organization_id: int, teacher_id: int) -> None:
    teacher = await db.scalar(
        select(models.Teacher.id).where(
            models.Teacher.id == teacher_id,
            models.Teacher.organization_id == organization_id,
        )
    )
    if teacher is None:
        raise _not_found(f"Teacher {teacher_id} was not found in organization {organization_id}.")


async def _lock_scheduler_state(db: AsyncSession, organization_id: int) -> None:
    """Take the same lock order as record_scheduler_change before link locks.

    ``record_scheduler_change`` locks the active school year and its state.
    Acquiring it first keeps a single lock order and avoids an inverted
    state/link deadlock. No other writer locks ``class_subject_link`` rows with
    ``FOR UPDATE``, so this is the only path that takes both locks.
    """
    school_year = await SchedulerStateService(db).get_active_school_year(
        organization_id, for_update=True
    )
    if school_year is None:
        return
    service = SchedulerStateService(db)
    await service.get_or_create_state(organization_id, school_year.id)
    await service.get_state(organization_id, school_year.id, for_update=True)


async def _lock_joint_facts(db: AsyncSession, organization_id: int, link_ids: list[int]) -> None:
    await _lock_scheduler_state(db, organization_id)
    await _lock_links(db, organization_id, link_ids)


async def _load_facts(
    db: AsyncSession,
    organization_id: int,
    subject,
    class_ids: list[int],
) -> tuple[list[policy.JointClassFacts], list[models.ClassSubjectLink]]:
    """Build the pure-rule facts and the matching links for the requested classes."""
    classes = (
        await db.scalars(
            select(models.Class).where(
                models.Class.organization_id == organization_id,
                models.Class.id.in_(class_ids),
            )
        )
    ).all()
    class_by_id = {row.id: row for row in classes}
    missing = [class_id for class_id in class_ids if class_id not in class_by_id]
    if missing:
        raise _not_found(f"Class {missing[0]} was not found in organization {organization_id}.")

    link_rows = (
        await db.scalars(
            select(models.ClassSubjectLink).where(
                models.ClassSubjectLink.organization_id == organization_id,
                models.ClassSubjectLink.subject_id == subject.id,
                models.ClassSubjectLink.class_id.in_(class_ids),
            )
        )
    ).all()
    link_by_class: dict[int, models.ClassSubjectLink] = {}
    for link in link_rows:
        if link.grade_level == class_by_id[link.class_id].grade_level:
            link_by_class[link.class_id] = link

    link_ids = [link.id for link in link_by_class.values()]
    selected = await _selected_modules_by_link(db, organization_id, link_ids)
    joined = await _joined_group_by_link(db, organization_id, link_ids)
    started = await _started_modules_by_class(db, organization_id, class_ids, subject.id)

    facts: list[policy.JointClassFacts] = []
    for class_id in class_ids:
        class_obj = class_by_id[class_id]
        if class_obj.is_archived:
            facts.append(
                policy.JointClassFacts(
                    class_id=class_id,
                    class_name=class_obj.name,
                    has_subject=False,
                    selected_module_ids=frozenset(),
                    started_module_ids=frozenset(),
                    joined_group_id=None,
                )
            )
            continue
        link = link_by_class.get(class_id)
        facts.append(
            policy.JointClassFacts(
                class_id=class_id,
                class_name=class_obj.name,
                has_subject=link is not None,
                selected_module_ids=frozenset(selected.get(link.id, set()))
                if link
                else frozenset(),
                started_module_ids=frozenset(started.get(class_id, set())),
                joined_group_id=joined.get(link.id) if link else None,
            )
        )
    return facts, list(link_by_class.values())


def _member_class_ids(db_rows) -> list[int]:
    return [row.class_id for row in db_rows]


async def _current_members(db: AsyncSession, organization_id: int, group_id: int):
    rows = await db.execute(
        select(
            models.joint_lesson_group_member.c.class_subject_link_id,
            models.ClassSubjectLink.class_id,
            models.ClassSubjectLink.teacher_id,
        )
        .join(
            models.ClassSubjectLink,
            models.ClassSubjectLink.id == models.joint_lesson_group_member.c.class_subject_link_id,
        )
        .where(
            models.joint_lesson_group_member.c.organization_id == organization_id,
            models.joint_lesson_group_member.c.group_id == group_id,
            models.ClassSubjectLink.organization_id == organization_id,
        )
    )
    return rows.all()


async def _current_module_ids(db: AsyncSession, organization_id: int, group_id: int) -> list[int]:
    rows = await db.execute(
        select(models.joint_lesson_group_module.c.module_id)
        .where(
            models.joint_lesson_group_module.c.organization_id == organization_id,
            models.joint_lesson_group_module.c.group_id == group_id,
        )
        .order_by(models.joint_lesson_group_module.c.module_id)
    )
    return [row[0] for row in rows.all()]


async def _lock_links(db: AsyncSession, organization_id: int, link_ids: list[int]) -> None:
    if not link_ids:
        return
    await db.execute(
        select(models.ClassSubjectLink.id)
        .where(
            models.ClassSubjectLink.organization_id == organization_id,
            models.ClassSubjectLink.id.in_(sorted(set(link_ids))),
        )
        .order_by(models.ClassSubjectLink.id)
        .with_for_update()
    )


async def _replace_members(
    db: AsyncSession, organization_id: int, group_id: int, link_ids: list[int]
) -> None:
    await db.execute(
        delete(models.joint_lesson_group_member).where(
            models.joint_lesson_group_member.c.organization_id == organization_id,
            models.joint_lesson_group_member.c.group_id == group_id,
        )
    )
    if link_ids:
        await db.execute(
            models.joint_lesson_group_member.insert().values(
                [
                    {
                        "organization_id": organization_id,
                        "group_id": group_id,
                        "class_subject_link_id": link_id,
                    }
                    for link_id in link_ids
                ]
            )
        )


async def _replace_modules(
    db: AsyncSession, organization_id: int, group_id: int, module_ids: list[int]
) -> None:
    await db.execute(
        delete(models.joint_lesson_group_module).where(
            models.joint_lesson_group_module.c.organization_id == organization_id,
            models.joint_lesson_group_module.c.group_id == group_id,
        )
    )
    if module_ids:
        await db.execute(
            models.joint_lesson_group_module.insert().values(
                [
                    {
                        "organization_id": organization_id,
                        "group_id": group_id,
                        "module_id": module_id,
                    }
                    for module_id in module_ids
                ]
            )
        )


async def _propagate_teacher(
    db: AsyncSession, organization_id: int, link_ids: list[int], teacher_id: int | None
) -> None:
    if not link_ids:
        return
    await db.execute(
        update(models.ClassSubjectLink)
        .where(
            models.ClassSubjectLink.organization_id == organization_id,
            models.ClassSubjectLink.id.in_(link_ids),
        )
        .values(teacher_id=teacher_id)
        .execution_options(synchronize_session=False)
    )


async def create_joint_group(
    db: AsyncSession,
    payload: schemas.JointLessonGroupWrite,
    organization_id: int,
    changed_by_membership_id: int | None = None,
) -> int:
    if payload.subject_id is None:
        raise AppError(
            kind="bad_request",
            code="bad_request",
            detail="subject_id is required.",
        )
    subject = await _load_subject(db, organization_id, payload.subject_id)
    class_ids = _distinct(payload.class_ids, "class_ids")
    module_ids = _distinct(payload.module_ids, "module_ids")
    module_names = await _validate_modules(db, organization_id, subject.id, module_ids)
    await _validate_teacher(db, organization_id, payload.teacher_id)
    eligible_teacher_ids = await _eligible_teacher_ids(db, organization_id, subject.id)

    # Lock before reading the joined/started facts so a concurrent writer cannot
    # join the same member between validation and insert.
    link_ids = await _link_ids_for_classes(db, organization_id, subject.id, class_ids)
    await _lock_joint_facts(db, organization_id, link_ids)
    try:
        facts, links = await _load_facts(db, organization_id, subject, class_ids)
        violation = policy.validate_joint_configuration(
            subject_name=subject.name,
            class_ids=class_ids,
            classes=facts,
            module_ids=module_ids,
            module_names=module_names,
            teacher_id=payload.teacher_id,
            eligible_teacher_ids=eligible_teacher_ids,
        )
        if violation is not None:
            _raise_violation(violation)

        link_ids = [link.id for link in links]
        group = models.JointLessonGroup(organization_id=organization_id, subject_id=subject.id)
        db.add(group)
        await db.flush()
        await _replace_members(db, organization_id, group.id, link_ids)
        await _replace_modules(db, organization_id, group.id, module_ids)
        await _propagate_teacher(db, organization_id, link_ids, payload.teacher_id)
        await record_scheduler_change(
            db,
            organization_id,
            entity_type=JOINT_ENTITY_TYPE,
            entity_id=group.id,
            operation=models.SchedulerStateChangeOperation.CREATE,
            before=None,
            after=_snapshot(subject.id, class_ids, module_ids, payload.teacher_id),
            changed_by_membership_id=changed_by_membership_id,
        )
        await db.flush()
        return group.id
    except IntegrityError as exc:
        raise _member_conflict() from exc


async def update_joint_group(
    db: AsyncSession,
    group_id: int,
    payload: schemas.JointLessonGroupWrite,
    organization_id: int,
    changed_by_membership_id: int | None = None,
) -> int:
    group = await _load_group(db, organization_id, group_id, for_update=True)
    subject = await _load_subject(db, organization_id, group.subject_id)
    members = await _current_members(db, organization_id, group_id)
    previous_link_ids = [row.class_subject_link_id for row in members]
    previous_class_ids = _member_class_ids(members)
    previous_module_ids = await _current_module_ids(db, organization_id, group_id)

    class_ids = _distinct(payload.class_ids, "class_ids")
    module_ids = _distinct(payload.module_ids, "module_ids")
    module_names = await _validate_modules(db, organization_id, subject.id, module_ids)
    await _validate_teacher(db, organization_id, payload.teacher_id)
    eligible_teacher_ids = await _eligible_teacher_ids(db, organization_id, subject.id)

    next_link_ids = await _link_ids_for_classes(db, organization_id, subject.id, class_ids)
    await _lock_joint_facts(db, organization_id, previous_link_ids + next_link_ids)
    try:
        facts, links = await _load_facts(db, organization_id, subject, class_ids)
        started = await _started_modules_by_class(
            db,
            organization_id,
            sorted(set(previous_class_ids) | set(class_ids)),
            subject.id,
        )
        previous_joint_started = any(
            started.get(class_id, set()) & set(previous_module_ids)
            for class_id in previous_class_ids
        )
        violation = policy.validate_joint_configuration(
            subject_name=subject.name,
            class_ids=class_ids,
            classes=facts,
            module_ids=module_ids,
            module_names=module_names,
            teacher_id=payload.teacher_id,
            eligible_teacher_ids=eligible_teacher_ids,
            previous_module_ids=previous_module_ids,
            previous_class_ids=previous_class_ids,
            previous_joint_module_started=previous_joint_started,
            ignore_group_id=group_id,
        )
        if violation is not None:
            _raise_violation(violation)

        next_link_ids = [link.id for link in links]
        before = _snapshot(
            group.subject_id,
            previous_class_ids,
            previous_module_ids,
            members[0].teacher_id if members else None,
        )
        await _replace_members(db, organization_id, group_id, next_link_ids)
        await _replace_modules(db, organization_id, group_id, module_ids)
        await _propagate_teacher(db, organization_id, next_link_ids, payload.teacher_id)
        await record_scheduler_change(
            db,
            organization_id,
            entity_type=JOINT_ENTITY_TYPE,
            entity_id=group_id,
            operation=models.SchedulerStateChangeOperation.UPDATE,
            before=before,
            after=_snapshot(group.subject_id, class_ids, module_ids, payload.teacher_id),
            changed_by_membership_id=changed_by_membership_id,
        )
        await db.flush()
        return group_id
    except IntegrityError as exc:
        raise _member_conflict() from exc


async def delete_joint_group(
    db: AsyncSession,
    group_id: int,
    organization_id: int,
    changed_by_membership_id: int | None = None,
) -> None:
    group = await _load_group(db, organization_id, group_id, for_update=True)
    subject = await _load_subject(db, organization_id, group.subject_id)
    members = await _current_members(db, organization_id, group_id)
    previous_link_ids = [row.class_subject_link_id for row in members]
    previous_class_ids = _member_class_ids(members)
    previous_module_ids = await _current_module_ids(db, organization_id, group_id)

    # Lock the facts before reading the started projection so the decision and
    # the write see the same snapshot.
    await _lock_joint_facts(db, organization_id, previous_link_ids)

    # J19: a started joint module or class cannot leave the group, so undo is
    # refused before any write.
    started = await _started_modules_by_class(db, organization_id, previous_class_ids, subject.id)
    started_modules = frozenset().union(
        *(started.get(class_id, set()) for class_id in previous_class_ids)
    )
    violation = policy.validate_modules_not_started(
        previous_module_ids,
        (),
        started_modules,
        await _module_names(db, organization_id, subject.id),
    )
    if violation is None:
        violation = policy.validate_classes_not_started(
            previous_class_ids,
            (),
            bool(set(previous_module_ids) & started_modules),
        )
    if violation is not None:
        _raise_violation(violation)

    before = _snapshot(
        group.subject_id,
        previous_class_ids,
        previous_module_ids,
        members[0].teacher_id if members else None,
    )
    await db.execute(
        delete(models.joint_lesson_group_module).where(
            models.joint_lesson_group_module.c.organization_id == organization_id,
            models.joint_lesson_group_module.c.group_id == group_id,
        )
    )
    await db.execute(
        delete(models.joint_lesson_group_member).where(
            models.joint_lesson_group_member.c.organization_id == organization_id,
            models.joint_lesson_group_member.c.group_id == group_id,
        )
    )
    await db.delete(group)
    await record_scheduler_change(
        db,
        organization_id,
        entity_type=JOINT_ENTITY_TYPE,
        entity_id=group_id,
        operation=models.SchedulerStateChangeOperation.DELETE,
        before=before,
        after=None,
        changed_by_membership_id=changed_by_membership_id,
    )
    await db.flush()


def _member_conflict() -> AppError:
    return AppError(
        kind="conflict",
        code=policy.JOINT_CLASS_ALREADY_JOINED,
        detail="A turma já tem esta disciplina em conjunto com outras turmas.",
    )


async def get_joint_candidates(
    db: AsyncSession,
    subject_id: int,
    class_id: int,
    organization_id: int,
    group_id: int | None = None,
    include_source: bool = False,
) -> list[schemas.JointCandidateRead]:
    subject = await _load_subject(db, organization_id, subject_id)
    if group_id is not None:
        group = await _load_group(db, organization_id, group_id)
        if group.subject_id != subject.id:
            raise _not_found(
                f"Joint lesson group {group_id} does not belong to subject {subject_id}."
            )

    rows = (
        await db.execute(
            select(
                models.ClassSubjectLink.id.label("link_id"),
                models.Class.id.label("class_id"),
                models.Class.name.label("class_name"),
                models.Class.grade_level.label("grade_level"),
                models.Course.abbreviation.label("course_abbreviation"),
                models.ClassSubjectLink.teacher_id.label("teacher_id"),
            )
            .select_from(models.ClassSubjectLink)
            .join(models.Class, models.Class.id == models.ClassSubjectLink.class_id)
            .join(models.Course, models.Course.id == models.Class.course_id)
            .where(
                models.ClassSubjectLink.organization_id == organization_id,
                models.ClassSubjectLink.subject_id == subject.id,
                models.ClassSubjectLink.grade_level == models.Class.grade_level,
                models.Class.organization_id == organization_id,
                models.Class.is_archived.is_(False),
            )
            .order_by(models.Class.name)
        )
    ).all()
    link_ids = [row.link_id for row in rows]
    selected = await _selected_modules_by_link(db, organization_id, link_ids)
    joined = await _joined_group_by_link(db, organization_id, link_ids)
    class_ids = [row.class_id for row in rows]
    started = await _started_modules_by_class(db, organization_id, class_ids, subject.id)

    if group_id is not None:
        source = next((row for row in rows if row.class_id == class_id), None)
        if source is None or joined.get(source.link_id) != group_id:
            raise _not_found(f"Class {class_id} does not belong to joint lesson group {group_id}.")
    elif include_source and not any(row.class_id == class_id for row in rows):
        # The source class must exist in this organization with a current link.
        raise _not_found(
            f"Class {class_id} has no current subject link in organization {organization_id}."
        )

    result: list[schemas.JointCandidateRead] = []
    for row in rows:
        joined_group = joined.get(row.link_id)
        if group_id is None:
            if row.class_id == class_id and not include_source:
                continue
            if joined_group is not None:
                continue
        elif joined_group is not None and joined_group != group_id:
            continue
        result.append(
            schemas.JointCandidateRead(
                class_id=row.class_id,
                class_name=row.class_name,
                course_abbreviation=row.course_abbreviation,
                grade_level=row.grade_level,
                teacher_id=row.teacher_id,
                selected_module_ids=sorted(selected.get(row.link_id, set())),
                started_module_ids=sorted(started.get(row.class_id, set())),
            )
        )
    return result


async def get_joint_group_read(
    db: AsyncSession,
    organization_id: int,
    group_id: int,
) -> schemas.JointLessonGroupRead | None:
    members = await _current_members(db, organization_id, group_id)
    link_ids = [row.class_subject_link_id for row in members]
    by_link = await load_joint_groups_by_link(db, organization_id, link_ids)
    return next(iter(by_link.values()), None)


async def load_joint_groups_by_link(
    db: AsyncSession,
    organization_id: int,
    link_ids: list[int],
) -> dict[int, schemas.JointLessonGroupRead]:
    """One batched query returning each link's joint group, or an empty map."""
    if not link_ids:
        return {}
    target_groups = (
        select(models.joint_lesson_group_member.c.group_id)
        .where(
            models.joint_lesson_group_member.c.organization_id == organization_id,
            models.joint_lesson_group_member.c.class_subject_link_id.in_(link_ids),
        )
        .scalar_subquery()
        .subquery()
    )
    module_agg = func.array_agg(models.joint_lesson_group_module.c.module_id)
    rows = await db.execute(
        select(
            models.joint_lesson_group_member.c.class_subject_link_id.label("link_id"),
            models.JointLessonGroup.id.label("group_id"),
            models.JointLessonGroup.subject_id.label("subject_id"),
            models.Subject.name.label("subject_name"),
            models.Class.id.label("class_id"),
            models.Class.name.label("class_name"),
            models.Course.abbreviation.label("course_abbreviation"),
            models.Class.grade_level.label("grade_level"),
            models.ClassSubjectLink.teacher_id.label("teacher_id"),
            module_agg.label("module_ids"),
        )
        .select_from(models.joint_lesson_group_member)
        .join(
            models.JointLessonGroup,
            models.JointLessonGroup.id == models.joint_lesson_group_member.c.group_id,
        )
        .join(
            models.Subject,
            models.Subject.id == models.JointLessonGroup.subject_id,
        )
        .join(
            models.ClassSubjectLink,
            models.ClassSubjectLink.id == models.joint_lesson_group_member.c.class_subject_link_id,
        )
        .join(models.Class, models.Class.id == models.ClassSubjectLink.class_id)
        .join(models.Course, models.Course.id == models.Class.course_id)
        .outerjoin(
            models.joint_lesson_group_module,
            models.joint_lesson_group_module.c.group_id == models.JointLessonGroup.id,
        )
        .where(
            models.joint_lesson_group_member.c.organization_id == organization_id,
            models.JointLessonGroup.organization_id == organization_id,
            models.JointLessonGroup.id.in_(select(target_groups.c.group_id)),
        )
        .group_by(
            models.joint_lesson_group_member.c.class_subject_link_id,
            models.JointLessonGroup.id,
            models.Subject.id,
            models.Class.id,
            models.Course.id,
            models.ClassSubjectLink.teacher_id,
        )
    )
    groups: dict[int, dict] = {}
    mapping: dict[int, schemas.JointLessonGroupRead] = {}
    fetched = rows.all()
    for row in fetched:
        group = groups.setdefault(
            row.group_id,
            {
                "id": row.group_id,
                "subject_id": row.subject_id,
                "subject_name": row.subject_name,
                "teacher_id": row.teacher_id,
                "classes": [],
                "module_ids": [value for value in (row.module_ids or []) if value is not None],
            },
        )
        group["classes"].append(
            schemas.JointLessonGroupClassRead(
                class_id=row.class_id,
                class_name=row.class_name,
                course_abbreviation=row.course_abbreviation,
                grade_level=row.grade_level,
            )
        )
    for group_id, data in groups.items():
        data["classes"].sort(key=lambda item: item.class_id)
        data["module_ids"].sort()
        mapping[group_id] = schemas.JointLessonGroupRead(**data)
    return {row.link_id: mapping[row.group_id] for row in fetched if row.group_id in mapping}
