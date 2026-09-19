# Ficheiro: app/services/teacher_service.py

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import models
from app.models import Availability
from app.schemas import AvailabilitySelfCreate
from app.services.availability_matrix_service import AvailabilityMatrixInspector
from app.services.scheduler_state_service import record_scheduler_change

logger = structlog.get_logger(__name__)


def _teacher_capacity_snapshot(subject_ids) -> dict:
    return {"subject_ids": sorted(int(subject_id) for subject_id in subject_ids)}


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


# Helper Function
async def get_teacher_with_subjects(db: AsyncSession, teacher_id: int, organization_id: int):
    query = (
        select(models.Teacher)
        .where(models.Teacher.id == teacher_id, models.Teacher.organization_id == organization_id)
        .options(selectinload(models.Teacher.subjects))
    )

    result = await db.execute(query)
    return result.scalars().first()


async def get_teacher_details(db: AsyncSession, teacher_id: int, organization_id: int):
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
        .where(models.Teacher.id == teacher_id, models.Teacher.organization_id == organization_id)
        .options(selectinload(models.Teacher.subjects))
        .execution_options(populate_existing=True)
    )

    result = await db.execute(stmt)
    row = result.first()

    if not row:
        return None

    teacher, email, is_active = row
    teacher.login_email = email
    teacher.email = email
    teacher.is_active = is_active

    return teacher


async def find_replacement_teacher(
    db: AsyncSession, organization_id: int, unavailable_slot_id: int, exclude_teacher_id: int
):
    """
    Encontra professores que podem substituir numa aula.
    Lógica de Prioridade:
    1. (Melhor) Preferencial (Score 2)
    2. (Normal) Neutro / Sem Registo (Score 1)
    3. (Pior) Evitar (Score 0) -> Fundo da lista
    Excluídos: Impossível (Score -1)
    """
    # 1. Buscar todos os professores
    all_teachers = await get_teachers_by_org(db, organization_id)

    # 2. Buscar as preferências de TODOS os professores para este slot específico
    avail_stmt = (
        select(Availability)
        .join(
            models.Timeslot,
            Availability.timeslot_id == models.Timeslot.id,
        )
        .where(
            Availability.timeslot_id == unavailable_slot_id,
            models.Timeslot.organization_id == organization_id,
        )
    )
    avail_results = await db.execute(avail_stmt)

    # Mapa rápido: { teacher_id: score }
    teacher_scores = {av.teacher_id: av.score for av in avail_results.scalars().all()}

    suggestions = []

    for teacher in all_teachers:
        if teacher.id == exclude_teacher_id:
            continue

        # Obter score (Default = 1/Neutro se não tiver registo)
        score = teacher_scores.get(teacher.id, 1)  #

        # FILTRO RÍGIDO: Se for Impossível (-1), salta fora.
        if score == -1:
            continue

        # DEFINIR PRIORIDADE (Menor número = Aparece primeiro na lista)
        # 1: Top (Reserva para lógica futura de "Já dá aulas à turma")
        # 2: Preferencial (Score 2)
        # 3: Neutro (Score 1)
        # 4: Evitar (Score 0) -> Fundo da lista

        priority = 3  # Default
        reason = "Disponível"

        if score == 2:
            priority = 2
            reason = "Preferencial (Marcado a Verde)"
        elif score == 0:
            priority = 4
            reason = "Evitar (Marcado a Laranja)"

        suggestions.append(
            {
                "teacher_id": teacher.id,
                "teacher_name": teacher.name,
                "priority": priority,
                "reason": reason,
            }
        )

    # Ordenar: Prioridade (crescente), depois Nome (alfabético)
    suggestions.sort(key=lambda x: (x["priority"], x["teacher_name"]))
    return suggestions


async def get_teacher_availability(
    db: AsyncSession,
    teacher_id: int,
    organization_id: int,
) -> list[dict] | str:
    """Lê disponibilidades de um professor dentro da organização autenticada (sintetiza NEUTRAL em memória)."""
    teacher_query = select(models.Teacher).where(
        models.Teacher.id == teacher_id,
        models.Teacher.organization_id == organization_id,
    )
    teacher_result = await db.execute(teacher_query)
    db_teacher = teacher_result.scalars().first()
    if not db_teacher:
        return "NOT_FOUND"

    timeslots_result = await db.execute(
        select(models.Timeslot)
        .where(models.Timeslot.organization_id == organization_id)
        .order_by(models.Timeslot.day_of_week, models.Timeslot.start_time, models.Timeslot.id)
    )
    timeslots = timeslots_result.scalars().all()
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
        return "NOT_FOUND"
    active_resource = await _teacher_is_scheduled(db, organization_id, teacher_id)

    existing_rows = await db.execute(
        select(Availability.timeslot_id, Availability.score).where(
            Availability.organization_id == organization_id,
            Availability.teacher_id == teacher_id,
        )
    )
    before = _availability_snapshot(existing_rows.all())

    # 2. Validar que o payload contém exatamente todos os timeslots da organização
    all_timeslots_result = await db.execute(
        select(models.Timeslot.id).where(models.Timeslot.organization_id == organization_id)
    )
    all_org_timeslot_ids = set(all_timeslots_result.scalars().all())

    timeslot_ids = [item.timeslot_id for item in availabilities]
    if len(timeslot_ids) != len(set(timeslot_ids)):
        return "DUPLICATE_TIMESLOT"

    if set(timeslot_ids) != all_org_timeslot_ids:
        return "INVALID_TIMESLOT"

    # 4. Mutação transacional
    # (outras estratégias são possíveis, mas replace-all mantém consistência simples)
    await db.execute(
        delete(Availability).where(
            Availability.organization_id == organization_id,
            Availability.teacher_id == teacher_id,
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
        metadata={"item_count": len(new_records)},
        active_resource=active_resource,
    )
    await db.flush()
    return {"status": "success", "count": len(new_records)}


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
    from app.services.class_service import _build_subject_with_progress

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

    # 4. Construir dados de disciplinas com progresso por turma
    for link in links:
        if not link.class_ or not link.subject:
            continue
        progress_map_for_class = {
            module_id: p for (c_id, module_id), p in progress_map.items() if c_id == link.class_id
        }
        subject_data = _build_subject_with_progress(link.subject, progress_map_for_class)
        classes_map[link.class_id]["subjects"].append(subject_data)

    # 5. Ordenar disciplinas alfabeticamente dentro de cada turma
    for class_data in classes_map.values():
        class_data["subjects"].sort(key=lambda s: s["name"])

    # 6. Retornar lista ordenada por nome da turma
    return sorted(classes_map.values(), key=lambda c: c["class_name"])


# ── Clerk Integration ─────────────────────────────────────────────


async def invite_teacher_to_clerk(
    clerk_org_id: str,
    teacher_email: str,
    teacher_id: int,
) -> dict:
    raise RuntimeError("Legacy teacher Clerk invites are disabled. Use ClerkAccessService.")
