from datetime import date

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import models, schemas
from app.core.exceptions import AppError
from app.models import Availability
from app.scheduler.infrastructure.operations import class_progress_map
from app.schemas import AvailabilitySelfCreate
from app.services import grid_version_service
from app.services.availability_matrix_service import AvailabilityMatrixInspector
from app.services.scheduler_state_service import record_scheduler_change

logger = structlog.get_logger(__name__)


def _availability_snapshot(rows) -> list[dict]:
    return sorted(
        ({"timeslot_id": int(row[0]), "score": int(row[1])} for row in rows),
        key=lambda item: item["timeslot_id"],
    )


async def _teacher_is_scheduled(db: AsyncSession, organization_id: int, teacher_id: int) -> bool:
    assignment_id = await db.scalar(
        select(models.ClassSubjectLink.id)
        .where(
            models.ClassSubjectLink.organization_id == organization_id,
            models.ClassSubjectLink.teacher_id == teacher_id,
        )
        .limit(1)
    )
    return assignment_id is not None


async def _get_teacher_or_404(
    db: AsyncSession, teacher_id: int, organization_id: int
) -> models.Teacher:
    teacher = await db.scalar(
        select(models.Teacher).where(
            models.Teacher.id == teacher_id,
            models.Teacher.organization_id == organization_id,
        )
    )
    if teacher is None:
        raise AppError(
            kind="not_found",
            code="resource_not_found",
            detail=f"Teacher {teacher_id} was not found in organization {organization_id}.",
        )
    return teacher


# ==========================================
#  FUNÇÕES ASSÍNCRONAS (Para usar na API/FastAPI)
# ==========================================


async def get_teachers_by_org(
    db: AsyncSession, organization_id: int, skip: int = 0, limit: int = 100
):
    """Return teachers with account data derived from their membership."""
    stmt = (
        select(
            models.Teacher,
            models.User.email,
            (
                models.OrganizationMembership.lifecycle_status
                == models.MembershipLifecycleStatus.active
            ).label("is_active"),
        )
        .join(
            models.OrganizationMembership,
            models.OrganizationMembership.id == models.Teacher.organization_membership_id,
        )
        .join(
            models.User,
            models.User.id == models.OrganizationMembership.account_id,
        )
        .where(models.Teacher.organization_id == organization_id)
        .options(selectinload(models.Teacher.subjects))
        .order_by(models.Teacher.name)
        .offset(skip)
        .limit(limit)
    )

    result = await db.execute(stmt)
    rows = result.all()

    final_list = []
    for teacher, user_email, is_active in rows:
        teacher.login_email = user_email
        teacher.email = user_email
        teacher.is_active = is_active
        final_list.append(teacher)

    return final_list


async def get_teacher_availability(
    db: AsyncSession,
    teacher_id: int,
    organization_id: int,
    on_date: date | None = None,
) -> list[dict]:
    """Lê disponibilidades de um professor dentro da organização autenticada (sintetiza NEUTRAL em memória)."""
    teacher_query = select(models.Teacher).where(
        models.Teacher.id == teacher_id,
        models.Teacher.organization_id == organization_id,
    )
    teacher_result = await db.execute(teacher_query)
    db_teacher = teacher_result.scalars().first()
    if not db_teacher:
        raise AppError(
            kind="not_found",
            code="resource_not_found",
            detail=f"Teacher {teacher_id} was not found in organization {organization_id}.",
        )

    resolved = await grid_version_service.resolve_grid(
        db,
        organization_id,
        on_date or await grid_version_service.school_today(db, organization_id),
    )
    timeslots = sorted(
        resolved.blocks,
        key=lambda ts: (ts.day_of_week, ts.start_time, ts.id),
    )
    timeslot_ids = [ts.id for ts in timeslots]

    inspection = await AvailabilityMatrixInspector.inspect(
        db,
        organization_id=organization_id,
        teacher_ids=[teacher_id],
        timeslot_ids=timeslot_ids,
    )

    return [
        {
            "timeslot_id": ts.id,
            "score": inspection.get_score(teacher_id, ts.id),
        }
        for ts in timeslots
    ]


async def set_teacher_availability(
    db: AsyncSession,
    teacher_id: int,
    availabilities: list[AvailabilitySelfCreate],
    organization_id: int,
    changed_by_membership_id: int | None = None,
    on_date: date | None = None,
):
    """
    Define as disponibilidades de um professor.
    Exige exatamente uma entrada por timeslot ativo da organização.
    """
    # 1. Validar que o professor pertence a esta organização
    teacher_query = select(models.Teacher).where(
        models.Teacher.id == teacher_id, models.Teacher.organization_id == organization_id
    )
    teacher_result = await db.execute(teacher_query)
    db_teacher = teacher_result.scalars().first()

    if not db_teacher:
        raise AppError(
            kind="not_found",
            code="resource_not_found",
            detail=f"Teacher {teacher_id} was not found in organization {organization_id}.",
        )
    active_resource = await _teacher_is_scheduled(db, organization_id, teacher_id)

    existing_rows = await db.execute(
        select(Availability.timeslot_id, Availability.score).where(
            Availability.organization_id == organization_id,
            Availability.teacher_id == teacher_id,
        )
    )
    previous_values = existing_rows.all()

    # 2. Validar que o payload contém exatamente os blocos da versão visível
    resolved = await grid_version_service.resolve_grid(
        db,
        organization_id,
        on_date or await grid_version_service.school_today(db, organization_id),
    )
    all_org_timeslot_ids = {slot.id for slot in resolved.blocks}
    before = _availability_snapshot(
        (slot_id, score) for slot_id, score in previous_values if slot_id in all_org_timeslot_ids
    )

    timeslot_ids = [item.timeslot_id for item in availabilities]
    if len(timeslot_ids) != len(set(timeslot_ids)):
        raise AppError(
            kind="bad_request",
            code="duplicate_timeslot",
            detail=f"Teacher {teacher_id} submitted duplicate timeslots.",
        )

    if set(timeslot_ids) != all_org_timeslot_ids:
        raise AppError(
            kind="bad_request",
            code="bad_request",
            detail=f"Teacher {teacher_id} submitted an invalid timeslot set.",
        )

    # 4. Mutação transacional
    # (outras estratégias são possíveis, mas replace-all mantém consistência simples)
    await db.execute(
        delete(Availability).where(
            Availability.organization_id == organization_id,
            Availability.teacher_id == teacher_id,
            Availability.timeslot_id.in_(all_org_timeslot_ids),
        )
    )

    new_records = [
        Availability(
            organization_id=organization_id,
            teacher_id=teacher_id,
            timeslot_id=item.timeslot_id,
            score=item.score.value,  # Guardamos o inteiro (-1, 0, 1, 2)
        )
        for item in availabilities
    ]

    db.add_all(new_records)
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="TEACHER_AVAILABILITY",
        entity_id=teacher_id,
        operation=models.SchedulerStateChangeOperation.BULK_IMPORT,
        before=before,
        after=_availability_snapshot(
            (item.timeslot_id, item.score.value) for item in availabilities
        ),
        changed_by_membership_id=changed_by_membership_id,
        metadata={
            "item_count": len(new_records),
            **({"on_date": on_date.isoformat()} if on_date else {}),
        },
        active_resource=active_resource,
    )
    await db.flush()
    return {"status": "success", "count": len(new_records)}


# ==========================================
#  PRESENÇA DO PROFESSOR (regra da direção)
# ==========================================


async def get_teacher_presence(
    db: AsyncSession, teacher_id: int, organization_id: int
) -> schemas.TeacherPresence:
    """Lê a regra de presença de um professor dentro da organização autenticada."""
    teacher = await _get_teacher_or_404(db, teacher_id, organization_id)
    return schemas.TeacherPresence.from_teacher(teacher)


async def set_teacher_presence(
    db: AsyncSession,
    teacher_id: int,
    presence: schemas.TeacherPresence,
    organization_id: int,
    changed_by_membership_id: int | None = None,
) -> schemas.TeacherPresence:
    """Define a regra de presença e registra o impacto no motor (D15)."""
    teacher = await _get_teacher_or_404(db, teacher_id, organization_id)
    before = schemas.TeacherPresence.from_teacher(teacher).model_dump()
    teacher.lunch_required = presence.lunch_required
    teacher.minimum_presence_hours = presence.minimum_hours
    teacher.maximum_presence_gap_hours = presence.max_gap_hours
    after = schemas.TeacherPresence.from_teacher(teacher).model_dump()
    if before == after:
        # record_scheduler_change would log a NO_OP event even without a change.
        return schemas.TeacherPresence.from_teacher(teacher)
    active_resource = await _teacher_is_scheduled(db, organization_id, teacher_id)
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="TEACHER_PRESENCE",
        entity_id=teacher_id,
        operation=models.SchedulerStateChangeOperation.UPDATE,
        before=before,
        after=after,
        changed_by_membership_id=changed_by_membership_id,
        active_resource=active_resource,
    )
    await db.flush()
    return schemas.TeacherPresence.from_teacher(teacher)


# ==========================================
#  PROGRESSO DO PROFESSOR (Visão Privada)
# ==========================================


async def get_teacher_progress(
    db: AsyncSession,
    teacher_id: int,
    organization_id: int,
) -> list[dict]:
    """
    Retorna o progresso curricular das disciplinas do professor
    nas turmas em que está assignado.

    Fonte de verdade: ClassSubjectLink (disciplinas atribuídas à turma
    com professor assignado).
    """
    from app.services.class_service import _build_subject_with_progress, _selected_module_map

    teacher_query = select(models.Teacher.id).where(
        models.Teacher.id == teacher_id,
        models.Teacher.organization_id == organization_id,
    )
    teacher_result = await db.execute(teacher_query)
    if teacher_result.scalar_one_or_none() is None:
        return []

    # 1. Buscar todas as atribuições do professor às turmas
    links_query = (
        select(models.ClassSubjectLink)
        .join(models.Class, models.ClassSubjectLink.class_id == models.Class.id)
        .where(
            models.ClassSubjectLink.organization_id == organization_id,
            models.ClassSubjectLink.teacher_id == teacher_id,
            models.Class.organization_id == organization_id,
        )
        .options(
            selectinload(models.ClassSubjectLink.class_).selectinload(models.Class.course),
            selectinload(models.ClassSubjectLink.subject).selectinload(models.Subject.modules),
            selectinload(models.ClassSubjectLink.subject).joinedload(models.Subject.room_type),
        )
    )
    links_result = await db.execute(links_query)
    links = links_result.scalars().all()

    if not links:
        return []

    # 2. Agrupar links por turma
    classes_map: dict[int, dict] = {}
    class_ids = set()
    for link in links:
        if not link.class_ or not link.subject:
            continue
        class_ids.add(link.class_id)
        if link.class_id not in classes_map:
            classes_map[link.class_id] = {
                "class_id": link.class_id,
                "class_name": link.class_.name,
                "course_name": link.class_.course.name if link.class_.course else None,
                "grade_level": link.class_.grade_level,
                "subjects": [],
            }

    # 3. Buscar progresso de todas as turmas relevantes de uma vez
    progress_map = {}
    if class_ids:
        progress_query = (
            select(
                models.ProgressLedgerEntry.class_id,
                models.ProgressLedgerEntry.module_id,
                func.coalesce(func.sum(models.ProgressLedgerEntry.completed_minutes_delta), 0),
                func.coalesce(func.sum(models.ProgressLedgerEntry.debt_minutes_delta), 0),
            )
            .where(
                models.ProgressLedgerEntry.organization_id == organization_id,
                models.ProgressLedgerEntry.class_id.in_(class_ids),
            )
            .group_by(
                models.ProgressLedgerEntry.class_id,
                models.ProgressLedgerEntry.module_id,
            )
        )
        progress_result = await db.execute(progress_query)
        progress_map = {
            (row[0], row[1]): (int(row[2]), int(row[3])) for row in progress_result.all()
        }
        # Use the same v1 accounting projection as the class dashboard.
        # Schools without curricular assignments keep the legacy ledger above.
        for class_id in sorted(class_ids):
            v1_progress = await class_progress_map(db, organization_id, class_id)
            if v1_progress is not None:
                progress_map.update(
                    {(class_id, module_id): minutes for module_id, minutes in v1_progress.items()}
                )

    # 4. Construir dados de disciplinas com progresso por turma
    selected_map = await _selected_module_map(db, organization_id, [link.id for link in links])
    for link in links:
        if not link.class_ or not link.subject:
            continue
        progress_map_for_class = {
            module_id: p for (c_id, module_id), p in progress_map.items() if c_id == link.class_id
        }
        selected_ids = selected_map.get(link.id, set())
        selected_modules = [module for module in link.subject.modules if module.id in selected_ids]
        subject_data = _build_subject_with_progress(
            link.subject, selected_modules, progress_map_for_class
        )
        classes_map[link.class_id]["subjects"].append(subject_data)

    # 5. Ordenar disciplinas alfabeticamente dentro de cada turma
    for class_data in classes_map.values():
        class_data["subjects"].sort(key=lambda s: s["name"])

    # 6. Retornar lista ordenada por nome da turma
    return sorted(classes_map.values(), key=lambda c: c["class_name"])


# ── Clerk Integration ─────────────────────────────────────────────
