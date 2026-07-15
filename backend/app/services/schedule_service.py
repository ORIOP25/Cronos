from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.future import select
from app import models, schemas
from app.services.scheduler_state_service import record_scheduler_change

# ==========================================
#  ASYNC (API / FRONTEND)
# ==========================================

# --- TIMESLOTS ---
async def get_timeslots_by_org(db: AsyncSession, organization_id: int):
    result = await db.execute(select(models.Timeslot).where(models.Timeslot.organization_id == organization_id))
    return result.scalars().all()

async def create_timeslot(
    db: AsyncSession,
    item: schemas.TimeslotCreate,
    organization_id: int,
    changed_by_user_id: int | None = None,
):
    # O item.model_dump() já vai ter 'start_time' como objeto time.
    db_item = models.Timeslot(**item.model_dump(), organization_id=organization_id)
    db.add(db_item)
    await db.flush()
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="TIMESLOT",
        entity_id=db_item.id,
        operation=models.SchedulerStateChangeOperation.CREATE,
        before=None,
        after=item.model_dump(),
        changed_by_user_id=changed_by_user_id,
    )
    await db.commit()
    await db.refresh(db_item)
    return db_item

# --- LESSONS ---
async def get_lessons_by_org(db: AsyncSession, organization_id: int):
    result = await db.execute(select(models.Lesson).where(models.Lesson.organization_id == organization_id))
    return result.scalars().all()

async def create_lesson(
    db: AsyncSession,
    item: schemas.LessonCreate,
    organization_id: int,
    changed_by_user_id: int | None = None,
):
    """
    Cria uma atribuição de professor a uma disciplina/turma.
    
    VALIDAÇÃO CRÍTICA: Verifica se o professor tem competência na disciplina.
    Isto evita que dados "lixo" cheguem ao Solver.
    """
    # 1. Validar turma pertence à organização
    class_query = select(models.Class).where(
        models.Class.id == item.class_id,
        models.Class.organization_id == organization_id
    )
    class_result = await db.execute(class_query)
    db_class = class_result.scalars().first()
    if not db_class:
        raise ValueError(f"Turma com ID {item.class_id} não encontrada na organização")

    # 2. Validar disciplina pertence à organização
    subject_query = select(models.Subject).where(
        models.Subject.id == item.subject_id,
        models.Subject.organization_id == organization_id
    )
    subject_result = await db.execute(subject_query)
    db_subject = subject_result.scalars().first()
    if not db_subject:
        raise ValueError(f"Disciplina com ID {item.subject_id} não encontrada na organização")

    # 3. Validar disciplina faz parte do curso da turma
    course_subject_query = select(models.Course).where(
        models.Course.id == db_class.course_id
    ).where(
        models.Course.subjects.any(models.Subject.id == item.subject_id)
    )
    course_subject_result = await db.execute(course_subject_query)
    if not course_subject_result.scalars().first():
        raise ValueError("A disciplina não pertence ao curso desta turma")

    # 4. Buscar o Professor e as suas Competências (Subjects)
    from sqlalchemy.orm import selectinload
    
    teacher_query = (
        select(models.Teacher)
        .where(
            models.Teacher.id == item.teacher_id,
            models.Teacher.organization_id == organization_id
        )
        .options(selectinload(models.Teacher.subjects))
    )
    teacher_result = await db.execute(teacher_query)
    teacher = teacher_result.scalars().first()
    
    if not teacher:
        raise ValueError(f"Professor com ID {item.teacher_id} não encontrado na organização")
    
    # 5. VALIDAÇÃO CRÍTICA: Verificar competência
    teacher_subject_ids = [s.id for s in teacher.subjects]
    if item.subject_id not in teacher_subject_ids:
        # Obter nome da disciplina para melhor mensagem de erro
        subject_query = select(models.Subject).where(models.Subject.id == item.subject_id)
        subject_result = await db.execute(subject_query)
        subject = subject_result.scalars().first()
        subject_name = subject.name if subject else f"ID {item.subject_id}"
        
        raise ValueError(
            f"O professor '{teacher.name}' não tem competência para lecionar '{subject_name}'. "
            f"Competências atuais: {', '.join([s.name for s in teacher.subjects]) or 'nenhuma'}."
        )
    
    # 6. Verificar se já existe Lesson para esta turma/disciplina/professor
    # (Evita duplicados)
    existing_query = select(models.Lesson).where(
        models.Lesson.class_id == item.class_id,
        models.Lesson.subject_id == item.subject_id,
        models.Lesson.teacher_id == item.teacher_id,
        models.Lesson.organization_id == organization_id
    )
    existing_result = await db.execute(existing_query)
    if existing_result.scalars().first():
        raise ValueError(
            "Já existe uma atribuição deste professor para esta disciplina/turma. "
            "Para mudar o professor, edite a atribuição existente."
        )
    
    # 4. Criar a Lesson
    db_item = models.Lesson(**item.model_dump(), organization_id=organization_id)
    db.add(db_item)
    await db.flush()
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="TEACHER_ASSIGNMENT",
        entity_id=db_item.id,
        operation=models.SchedulerStateChangeOperation.CREATE,
        before=None,
        after={
            "class_id": db_item.class_id,
            "subject_id": db_item.subject_id,
            "teacher_id": db_item.teacher_id,
        },
        changed_by_user_id=changed_by_user_id,
        active_resource=not db_class.is_archived,
    )
    await db.commit()
    await db.refresh(db_item)
    return db_item

# --- CONSTRAINTS ---
class ConstraintSemanticValidationError(ValueError):
    pass


async def _validate_constraint_references(
    db: AsyncSession,
    item: schemas.ConstraintCreate,
    organization_id: int,
) -> None:
    payload = item.rule_payload.model_dump()
    rule_type = item.rule_type.value
    invalid = False

    async def owned(model, entity_id: int):
        return await db.scalar(
            select(model).where(
                model.id == entity_id,
                model.organization_id == organization_id,
            )
        )

    timeslot_id = payload.get("timeslot_id")
    if timeslot_id is not None and await owned(models.Timeslot, timeslot_id) is None:
        invalid = True

    teacher_id = payload.get("teacher_id")
    if teacher_id is not None:
        teacher = await owned(models.Teacher, teacher_id)
        if teacher is None or teacher.archived_at is not None:
            invalid = True

    if rule_type in {"specific_room", "lock_time"}:
        class_row = await owned(models.Class, payload["class_id"])
        subject_row = await owned(models.Subject, payload["subject_id"])
        relationship = await db.scalar(
            select(models.ClassSubjectLink.id).where(
                models.ClassSubjectLink.organization_id == organization_id,
                models.ClassSubjectLink.class_id == payload["class_id"],
                models.ClassSubjectLink.subject_id == payload["subject_id"],
                models.ClassSubjectLink.grade_level == class_row.grade_level
                if class_row is not None
                else False,
            )
        )
        if (
            class_row is None
            or class_row.is_archived
            or subject_row is None
            or relationship is None
        ):
            invalid = True
        if rule_type == "specific_room":
            room = await owned(models.Room, payload["room_id"])
            if (
                room is None
                or class_row is None
                or subject_row is None
                or room.capacity < class_row.size
                or room.type != subject_row.required_room_type
            ):
                invalid = True

    if invalid:
        raise ConstraintSemanticValidationError(
            "One or more scheduler constraint references are unavailable."
        )


async def create_constraint(
    db: AsyncSession,
    item: schemas.ConstraintCreate,
    organization_id: int,
    changed_by_user_id: int | None = None,
):
    await _validate_constraint_references(db, item, organization_id)
    payload = item.model_dump(mode="json")
    db_item = models.Constraint(
        rule_type=models.ConstraintType(payload["rule_type"]),
        rule_payload=payload["rule_payload"],
        organization_id=organization_id,
    )
    db.add(db_item)
    await db.flush()
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="SCHEDULER_CONSTRAINT",
        entity_id=db_item.id,
        operation=models.SchedulerStateChangeOperation.CREATE,
        before=None,
        after={"rule_type": db_item.rule_type, "rule_payload": db_item.rule_payload},
        changed_by_user_id=changed_by_user_id,
    )
    await db.commit()
    await db.refresh(db_item)
    return db_item

async def get_constraints_by_org(db: AsyncSession, organization_id: int):
    """Lista todas as restrições."""
    result = await db.execute(select(models.Constraint).where(models.Constraint.organization_id == organization_id))
    return result.scalars().all()

async def delete_constraint(
    db: AsyncSession,
    constraint_id: int,
    organization_id: int,
    changed_by_user_id: int | None = None,
):
    """Apaga uma regra de horário."""
    query = select(models.Constraint).where(
        models.Constraint.id == constraint_id,
        models.Constraint.organization_id == organization_id
    )
    result = await db.execute(query)
    item = result.scalars().first()
    
    if item:
        before = {"rule_type": item.rule_type, "rule_payload": item.rule_payload}
        await db.delete(item)
        await record_scheduler_change(
            db,
            organization_id,
            entity_type="SCHEDULER_CONSTRAINT",
            entity_id=item.id,
            operation=models.SchedulerStateChangeOperation.DELETE,
            before=before,
            after=None,
            changed_by_user_id=changed_by_user_id,
        )
        await db.commit()
        return True
    return False


async def get_latest_schedule_by_org(db: AsyncSession, organization_id: int):
    latest_generation_id = await db.scalar(
        select(models.ScheduleOutput.generation_id)
        .where(
            models.ScheduleOutput.organization_id == organization_id,
            models.ScheduleOutput.is_draft.is_(False),
        )
        .order_by(models.ScheduleOutput.id.desc())
        .limit(1)
    )
    if latest_generation_id is None:
        return []

    result = await db.execute(
        select(models.ScheduleOutput)
        .where(
            models.ScheduleOutput.organization_id == organization_id,
            models.ScheduleOutput.generation_id == latest_generation_id,
            models.ScheduleOutput.is_draft.is_(False),
        )
        .order_by(
            models.ScheduleOutput.date.asc().nulls_last(),
            models.ScheduleOutput.timeslot_id.asc(),
            models.ScheduleOutput.id.asc(),
        )
    )
    return result.scalars().all()


# ==========================================
#  SYNC (SOLVER / CELERY)
# ==========================================
# Estas funções são usadas pelo Celery Worker que não suporta bem async/await.

def get_lessons_by_org_sync(db: Session, organization_id: int):
    return db.query(models.Lesson).filter(models.Lesson.organization_id == organization_id).all()

def get_timeslots_by_org_sync(db: Session, organization_id: int):
    return db.query(models.Timeslot).filter(models.Timeslot.organization_id == organization_id).all()

def get_constraints_by_org_sync(db: Session, organization_id: int):
    return db.query(models.Constraint).filter(models.Constraint.organization_id == organization_id).all()

def get_availabilities_by_org_sync(db: Session, organization_id: int):
    """
    Retorna todas as disponibilidades dos professores desta organização.
    Faz um JOIN com a tabela Teacher para filtrar pelo organization_id.
    """
    return db.query(models.Availability)\
             .join(models.Teacher)\
             .filter(models.Teacher.organization_id == organization_id)\
             .all()

def create_schedule_output_sync(db: Session, lesson_id, timeslot_id, room_id, organization_id, gen_id):
    db_out = models.ScheduleOutput(
        lesson_id=lesson_id,
        timeslot_id=timeslot_id,
        room_id=room_id,
        organization_id=organization_id,
        generation_id=gen_id
    )
    db.add(db_out)
    # Nota: O commit é feito pelo caller no final para performance

def clear_schedule_sync(db: Session, organization_id: int):
    """
    Apaga todos os registos de horários gerados anteriormente para esta organização.
    (Usado pelo Celery antes de gravar um novo horário)
    """
    db.query(models.ScheduleOutput)\
      .filter(models.ScheduleOutput.organization_id == organization_id)\
      .delete()
    # The caller owns the generation transaction.


# ==========================================
#  SYNC — Sprint 1: dados para o solver modular
# ==========================================

def get_active_lessons_with_subject_sync(db: Session, organization_id: int):
    """Lições de turmas não arquivadas, com Subject pré-carregado."""
    return (
        db.query(models.Lesson)
        .join(models.Class, models.Lesson.class_id == models.Class.id)
        .filter(
            models.Lesson.organization_id == organization_id,
            models.Class.is_archived == False,  # noqa: E712
        )
        .options(joinedload(models.Lesson.subject))
        .all()
    )


def _get_active_classes_sync(db: Session, organization_id: int) -> list:
    return (
        db.query(models.Class)
        .filter(
            models.Class.organization_id == organization_id,
            models.Class.is_archived.is_(False),
        )
        .all()
    )


def _collect_desired_pairs_by_links(
    db: Session,
    organization_id: int,
    active_class_ids: set[int],
    class_grade_map: dict[int, int],
) -> tuple[dict[tuple[int, int], int], set[int]]:
    desired_pairs: dict[tuple[int, int], int] = {}
    classes_with_links: set[int] = set()
    link_rows = (
        db.query(models.ClassSubjectLink)
        .filter(
            models.ClassSubjectLink.class_id.in_(active_class_ids),
            models.ClassSubjectLink.organization_id == organization_id,
            models.ClassSubjectLink.teacher_id.isnot(None),
        )
        .all()
    )

    for link in link_rows:
        class_grade = class_grade_map.get(link.class_id)
        if class_grade is None or link.grade_level != class_grade:
            continue
        desired_pairs[(link.class_id, link.subject_id)] = link.teacher_id
        classes_with_links.add(link.class_id)

    return desired_pairs, classes_with_links


def _sync_pair_lessons(
    db: Session,
    organization_id: int,
    desired_pairs: dict[tuple[int, int], int],
    lessons_by_pair: dict[tuple[int, int], list],
) -> tuple[int, int, int]:
    created = 0
    updated = 0
    deleted = 0

    for pair, teacher_id in desired_pairs.items():
        pair_lessons = lessons_by_pair.get(pair, [])
        if not pair_lessons:
            db.add(
                models.Lesson(
                    organization_id=organization_id,
                    class_id=pair[0],
                    subject_id=pair[1],
                    teacher_id=teacher_id,
                )
            )
            created += 1
            continue

        primary_lesson = pair_lessons[0]
        if primary_lesson.teacher_id != teacher_id:
            primary_lesson.teacher_id = teacher_id
            updated += 1

        for extra_lesson in pair_lessons[1:]:
            db.delete(extra_lesson)
            deleted += 1

    return created, updated, deleted


def _delete_stale_class_lessons(
    db: Session,
    lesson_rows: list,
    classes_with_links: set[int],
    desired_pairs: dict[tuple[int, int], int],
) -> int:
    deleted = 0
    for lesson in lesson_rows:
        if lesson.class_id not in classes_with_links:
            continue
        pair = (lesson.class_id, lesson.subject_id)
        if pair in desired_pairs:
            continue
        db.delete(lesson)
        deleted += 1
    return deleted


def sync_lessons_from_class_subject_links_sync(db: Session, organization_id: int) -> dict:
    """Sincroniza Lesson (legado) a partir de ClassSubjectLink (fonte de verdade).

    Regras:
      - Apenas turmas ativas (não arquivadas).
      - Para turmas com links disciplina-professor, os links têm precedência.
      - Turmas sem links mantêm fallback legado via Lesson existente.
    """
    active_classes = _get_active_classes_sync(db, organization_id)
    active_class_ids = {c.id for c in active_classes}
    class_grade_map = {c.id: c.grade_level for c in active_classes}

    if not active_class_ids:
        return {"created": 0, "updated": 0, "deleted": 0}

    desired_pairs, classes_with_links = _collect_desired_pairs_by_links(
        db,
        organization_id,
        active_class_ids,
        class_grade_map,
    )

    lesson_rows = (
        db.query(models.Lesson)
        .filter(
            models.Lesson.organization_id == organization_id,
            models.Lesson.class_id.in_(active_class_ids),
        )
        .all()
    )

    lessons_by_pair: dict[tuple[int, int], list] = defaultdict(list)
    for lesson in lesson_rows:
        lessons_by_pair[(lesson.class_id, lesson.subject_id)].append(lesson)

    created, updated, deleted = _sync_pair_lessons(
        db,
        organization_id,
        desired_pairs,
        lessons_by_pair,
    )

    deleted += _delete_stale_class_lessons(
        db,
        lesson_rows,
        classes_with_links,
        desired_pairs,
    )

    if created or updated or deleted:
        db.flush()

    return {"created": created, "updated": updated, "deleted": deleted}


def get_modules_by_subject_sync(db: Session, organization_id: int) -> dict:
    """Retorna {subject_id: [Module ordenado]} para todos os subjects da org."""
    modules = (
        db.query(models.Module)
        .join(models.Subject, models.Module.subject_id == models.Subject.id)
        .filter(models.Subject.organization_id == organization_id)
        .filter(models.Module.organization_id == organization_id)
        .order_by(models.Module.subject_id, models.Module.order)
        .all()
    )
    result: dict = defaultdict(list)
    for module in modules:
        result[module.subject_id].append(module)
    return dict(result)


def get_class_progress_map_sync(db: Session, organization_id: int) -> dict:
    """Retorna {(class_id, module_id): hours_completed} para toda a org."""
    records = (
        db.query(models.ClassProgress)
        .join(models.Class, models.ClassProgress.class_id == models.Class.id)
        .filter(models.Class.organization_id == organization_id)
        .filter(models.ClassProgress.organization_id == organization_id)
        .all()
    )
    return {(r.class_id, r.module_id): r.hours_completed for r in records}


def get_org_settings_sync(db: Session, organization_id: int):
    """Retorna as OrganizationSettings desta org, da mais recente para a mais antiga."""
    return (
        db.query(models.OrganizationSettings)
        .filter(models.OrganizationSettings.organization_id == organization_id)
        .order_by(models.OrganizationSettings.id.desc())
        .all()
    )


def get_grid_settings_sync(db: Session, organization_id: int):
    """Retorna as OrganizationGridSettings desta org (única por org), ou None."""
    return (
        db.query(models.OrganizationGridSettings)
        .filter(models.OrganizationGridSettings.organization_id == organization_id)
        .first()
    )


def get_calendar_events_sync(db: Session, organization_id: int):
    """Retorna todos os SchoolCalendarEvents desta org."""
    return (
        db.query(models.SchoolCalendarEvent)
        .filter(models.SchoolCalendarEvent.organization_id == organization_id)
        .all()
    )


def update_class_projected_end_date_sync(db: Session, organization_id: int, class_id: int, end_date: date) -> None:
    """Atualiza projected_end_date de uma turma."""
    db.query(models.Class).filter(
        models.Class.id == class_id,
        models.Class.organization_id == organization_id,
    ).update(
        {"projected_end_date": end_date}
    )


def clear_future_schedule_sync(db: Session, organization_id: int) -> None:
    """Apaga apenas ScheduleOutput com date > hoje (imutabilidade do passado).
    Registos sem data (legado) também são apagados para não quebrar FK consistency.
    """
    today = date.today()
    db.query(models.ScheduleOutput).filter(
        models.ScheduleOutput.organization_id == organization_id,
        (models.ScheduleOutput.date == None) | (models.ScheduleOutput.date > today),  # noqa: E711
    ).delete(synchronize_session="fetch")


def clear_schedule_window_sync(
    db: Session,
    organization_id: int,
    start_date: date,
    end_date: date,
) -> int:
    """Apaga outputs ativos numa janela [start_date, end_date], preservando slots com ocorrencias.

    Esta funcao garante idempotencia da regeneracao numa janela concreta sem remover
    historico ja confirmado em LessonOccurrence.
    """
    if end_date < start_date:
        return 0

    output_ids = [
        row[0]
        for row in db.query(models.ScheduleOutput.id)
        .filter(
            models.ScheduleOutput.organization_id == organization_id,
            models.ScheduleOutput.is_draft.is_(False),
            models.ScheduleOutput.date.between(start_date, end_date),
        )
        .all()
    ]

    if not output_ids:
        return 0

    locked_ids = {
        row[0]
        for row in db.query(models.LessonOccurrence.schedule_output_id)
        .filter(models.LessonOccurrence.schedule_output_id.in_(output_ids))
        .all()
    }

    deletable_ids = [output_id for output_id in output_ids if output_id not in locked_ids]
    if not deletable_ids:
        return 0

    deleted = (
        db.query(models.ScheduleOutput)
        .filter(models.ScheduleOutput.id.in_(deletable_ids))
        .delete(synchronize_session="fetch")
    )
    return deleted


def _get_lesson_identity_sync(db: Session, lesson_id: int) -> tuple[int, int] | None:
    lesson = (
        db.query(models.Lesson.class_id, models.Lesson.teacher_id)
        .filter(models.Lesson.id == lesson_id)
        .first()
    )
    if lesson is None:
        return None
    return (lesson.class_id, lesson.teacher_id)


def _find_conflicting_active_output_ids_sync(
    db: Session,
    organization_id: int,
    lesson_id: int,
    timeslot_id: int,
    output_date: date,
) -> list[int]:
    identity = _get_lesson_identity_sync(db, lesson_id)
    if identity is None:
        return []

    class_id, teacher_id = identity
    rows = (
        db.query(models.ScheduleOutput.id)
        .join(models.Lesson, models.ScheduleOutput.lesson_id == models.Lesson.id)
        .filter(
            models.ScheduleOutput.organization_id == organization_id,
            models.ScheduleOutput.is_draft.is_(False),
            models.ScheduleOutput.timeslot_id == timeslot_id,
            models.ScheduleOutput.date == output_date,
            (
                (models.ScheduleOutput.lesson_id == lesson_id)
                | (models.Lesson.class_id == class_id)
                | (models.Lesson.teacher_id == teacher_id)
            ),
        )
        .all()
    )
    return [row[0] for row in rows]


def _split_locked_output_ids(db: Session, output_ids: list[int]) -> tuple[list[int], list[int]]:
    if not output_ids:
        return ([], [])

    locked_ids = {
        row[0]
        for row in db.query(models.LessonOccurrence.schedule_output_id)
        .filter(models.LessonOccurrence.schedule_output_id.in_(output_ids))
        .all()
    }

    deletable_ids = [output_id for output_id in output_ids if output_id not in locked_ids]
    blocked_ids = [output_id for output_id in output_ids if output_id in locked_ids]
    return (deletable_ids, blocked_ids)


def create_schedule_output_with_date_sync(
    db: Session,
    lesson_id: int,
    timeslot_id: int,
    room_id: int,
    output_date: date,
    organization_id: int,
    gen_id: str,
    is_draft: bool = False,
) -> None:
    """Cria uma linha de ScheduleOutput com data absoluta."""
    existing_same = (
        db.query(models.ScheduleOutput.id)
        .filter(
            models.ScheduleOutput.organization_id == organization_id,
            models.ScheduleOutput.lesson_id == lesson_id,
            models.ScheduleOutput.timeslot_id == timeslot_id,
            models.ScheduleOutput.date == output_date,
            models.ScheduleOutput.is_draft.is_(is_draft),
        )
        .first()
    )
    if existing_same is not None:
        return

    if not is_draft:
        conflicting_ids = _find_conflicting_active_output_ids_sync(
            db,
            organization_id,
            lesson_id,
            timeslot_id,
            output_date,
        )
        deletable_ids, blocked_ids = _split_locked_output_ids(db, conflicting_ids)

        if deletable_ids:
            db.query(models.ScheduleOutput).filter(
                models.ScheduleOutput.id.in_(deletable_ids)
            ).delete(synchronize_session="fetch")

        if blocked_ids:
            # Mantem histórico confirmado; evita criar novo conflito no mesmo slot.
            return

    db.add(
        models.ScheduleOutput(
            lesson_id=lesson_id,
            timeslot_id=timeslot_id,
            room_id=room_id,
            date=output_date,
            organization_id=organization_id,
            generation_id=gen_id,
            is_draft=is_draft,
        )
    )


# ==========================================
#  SPRINT 4 — VISUALIZAÇÃO SEMANAL
# ==========================================

def _find_active_module(modules: list, progress_map: dict):
    """Returns the first non-completed module, or the last if all done."""
    for module in modules:
        prog = progress_map.get(module.id)
        if not prog or not prog.is_completed:
            return module
    return modules[-1] if modules else None


def _fetch_active_modules(
    db: Session, pairs: list[tuple]
) -> dict[tuple, dict | None]:
    """Fetches active module data per (class_id, subject_id) pair without N+1 queries."""
    active: dict[tuple, dict | None] = {}
    if not pairs:
        return active

    unique_pairs = list(set(pairs))
    subject_ids = {subject_id for _, subject_id in unique_pairs}
    class_ids = {class_id for class_id, _ in unique_pairs}

    modules_rows = (
        db.query(models.Module)
        .filter(models.Module.subject_id.in_(subject_ids))
        .order_by(models.Module.subject_id, models.Module.order)
        .all()
    )

    modules_by_subject: dict[int, list[models.Module]] = {}
    module_ids: list[int] = []
    for module in modules_rows:
        modules_by_subject.setdefault(module.subject_id, []).append(module)
        module_ids.append(module.id)

    progress_lookup: dict[tuple[int, int], models.ClassProgress] = {}
    if module_ids and class_ids:
        progress_rows = db.query(models.ClassProgress).filter(
            models.ClassProgress.class_id.in_(class_ids),
            models.ClassProgress.module_id.in_(module_ids),
        ).all()
        progress_lookup = {
            (row.class_id, row.module_id): row
            for row in progress_rows
        }

    for cls_id, subj_id in unique_pairs:
        modules = modules_by_subject.get(subj_id, [])
        if not modules:
            active[(cls_id, subj_id)] = None
            continue

        progress_map = {
            module.id: progress_lookup.get((cls_id, module.id))
            for module in modules
        }
        mod = _find_active_module(modules, progress_map)
        active[(cls_id, subj_id)] = (
            {"id": mod.id, "name": mod.name, "hours_total": mod.hours_total}
            if mod else None
        )

    return active


def _build_week_slot(
    output: models.ScheduleOutput,
    occurrences: dict,
    lesson_logs: dict,
    active_modules: dict,
    today: date,
    timesheet_map: dict | None = None,
    substituted_blocks: set | None = None,
) -> dict:
    """Builds a single WeekSlotRead dict from a ScheduleOutput row."""
    occ = occurrences.get(output.id)
    llog = lesson_logs.get(output.id)
    lesson = output.lesson
    if not lesson:
        return {
            "schedule_output_id": output.id,
            "date": output.date.isoformat() if output.date else None,
            "timeslot": None,
            "subject": None,
            "teacher": None,
            "room": None,
            "class_info": None,
            "module": None,
            "is_past": output.date is not None and output.date < today,
            "occurrence_status": None,
            "hours_given": None,
            "occurrence_id": None,
            "occurrence_decided_at": None,
            "can_create_occurrence": True,
            "can_decide_occurrence": False,
            "lesson_log_id": None,
            "lesson_log_status": None,
            "lesson_log_summary": None,
            "lesson_log_notes": None,
            "lesson_log_logged_at": None,
            "week_timesheet_status": "OPEN",
            "timesheet_id": None,
            "is_substituted_block": False,
        }
    ts = output.timeslot
    mod_data = active_modules.get((lesson.class_id, lesson.subject_id))
    has_occurrence = occ is not None
    teacher_id = lesson.teacher_id if lesson else None
    timesheet_status, timesheet_id = ("OPEN", None)
    if timesheet_map and teacher_id is not None:
        timesheet_status, timesheet_id = timesheet_map.get(teacher_id, ("OPEN", None))

    is_substituted_block = False
    if substituted_blocks and teacher_id is not None and output.date is not None and output.timeslot_id is not None:
        is_substituted_block = (teacher_id, output.date, output.timeslot_id) in substituted_blocks

    return {
        "schedule_output_id": output.id,
        "operational_block_id": None,
        "block_source": "planned",
        "date": output.date.isoformat() if output.date else None,
        "timeslot": {
            "id": ts.id,
            "day_of_week": ts.day_of_week,
            "start_time": str(ts.start_time)[:5],
            "end_time": str(ts.end_time)[:5],
        },
        "subject": (
            {"id": lesson.subject.id, "name": lesson.subject.name}
            if lesson.subject else None
        ),
        "teacher": (
            {"id": lesson.teacher.id, "name": lesson.teacher.name}
            if lesson.teacher else None
        ),
        "room": (
            {"id": output.room.id, "name": output.room.name}
            if output.room else None
        ),
        "class_info": (
            {"id": lesson.class_model.id, "name": lesson.class_model.name}
            if lesson.class_model else None
        ),
        "module": mod_data,
        "is_past": output.date is not None and output.date < today,
        "occurrence_status": occ.status.value if occ and occ.status is not None else None,
        "hours_given": occ.hours_given if occ else None,
        "occurrence_id": occ.id if occ else None,
        "occurrence_decided_at": occ.decided_at if occ else None,
        "can_create_occurrence": not has_occurrence,
        "can_decide_occurrence": has_occurrence,
        # WBS Fase 1: campos de registo de execução
        "lesson_log_id": llog.id if llog else None,
        "lesson_log_status": llog.status.value if llog else None,
        "lesson_log_summary": llog.summary if llog else None,
        "lesson_log_notes": llog.notes if llog else None,
        "lesson_log_logged_at": llog.logged_at if llog else None,
        # WBS Fase 6: estado do fecho semanal do professor
        "week_timesheet_status": timesheet_status,
        "timesheet_id": timesheet_id,
        # WBS V3 Fase 4: indicador de bloco de substituição
        "is_substituted_block": is_substituted_block,
    }

def _build_operational_week_slot(
    block: models.OperationalScheduleBlock,
    lesson_log: models.LessonLog | None,
    active_modules: dict,
    today: date,
    timesheet_map: dict | None = None,
) -> dict:
    timesheet_status, timesheet_id = ("OPEN", None)
    if timesheet_map:
        timesheet_status, timesheet_id = timesheet_map.get(block.teacher_id, ("OPEN", None))

    return {
        "schedule_output_id": None,
        "operational_block_id": block.id,
        "block_source": "operational",
        "date": block.date.isoformat(),
        "timeslot": {
            "id": block.timeslot.id,
            "day_of_week": block.timeslot.day_of_week,
            "start_time": str(block.timeslot.start_time)[:5],
            "end_time": str(block.timeslot.end_time)[:5],
        },
        "subject": {"id": block.subject.id, "name": block.subject.name} if block.subject else None,
        "teacher": {"id": block.teacher.id, "name": block.teacher.name} if block.teacher else None,
        "room": {"id": block.room.id, "name": block.room.name} if block.room else None,
        "class_info": {"id": block.class_.id, "name": block.class_.name} if block.class_ else None,
        "module": active_modules.get((block.class_id, block.subject_id)),
        "is_past": block.date < today,
        "occurrence_status": models.LessonOccurrenceStatus.SUBSTITUTED.value,
        "hours_given": 0.0,
        "occurrence_id": block.source_occurrence_id,
        "occurrence_decided_at": block.source_occurrence.decided_at if block.source_occurrence else None,
        "can_create_occurrence": False,
        "can_decide_occurrence": False,
        "lesson_log_id": lesson_log.id if lesson_log else None,
        "lesson_log_status": lesson_log.status.value if lesson_log else None,
        "lesson_log_summary": lesson_log.summary if lesson_log else None,
        "lesson_log_notes": lesson_log.notes if lesson_log else None,
        "lesson_log_logged_at": lesson_log.logged_at if lesson_log else None,
        "week_timesheet_status": timesheet_status,
        "timesheet_id": timesheet_id,
        "is_substituted_block": True,
    }


def _build_active_week_slot(
    row: tuple,
    occurrences: dict[int, models.LessonOccurrence],
    lesson_logs: dict[int, models.LessonLog],
    active_modules: dict,
    today: date,
    timesheet_map: dict | None = None,
) -> dict:
    block, timeslot, subject, teacher, class_model, room = row
    occurrence = occurrences.get(block.id)
    lesson_log = lesson_logs.get(block.id)
    timesheet_status, timesheet_id = ("OPEN", None)
    if timesheet_map:
        timesheet_status, timesheet_id = timesheet_map.get(
            block.teacher_id, ("OPEN", None)
        )

    return {
        "schedule_output_id": None,
        "active_schedule_block_id": block.id,
        "operational_block_id": None,
        "block_source": "active",
        "date": block.date.isoformat(),
        "timeslot": {
            "id": timeslot.id,
            "day_of_week": timeslot.day_of_week,
            "start_time": str(timeslot.start_time)[:5],
            "end_time": str(timeslot.end_time)[:5],
        },
        "subject": {"id": subject.id, "name": subject.name},
        "teacher": {"id": teacher.id, "name": teacher.name},
        "room": {"id": room.id, "name": room.name},
        "class_info": {"id": class_model.id, "name": class_model.name},
        "module": active_modules.get((block.class_id, block.subject_id)),
        "is_past": block.date < today,
        "occurrence_status": (
            occurrence.status.value
            if occurrence and occurrence.status is not None
            else None
        ),
        "hours_given": occurrence.hours_given if occurrence else None,
        "occurrence_id": occurrence.id if occurrence else None,
        "occurrence_decided_at": occurrence.decided_at if occurrence else None,
        "can_create_occurrence": occurrence is None,
        "can_decide_occurrence": occurrence is not None,
        "lesson_log_id": lesson_log.id if lesson_log else None,
        "lesson_log_status": lesson_log.status.value if lesson_log else None,
        "lesson_log_summary": lesson_log.summary if lesson_log else None,
        "lesson_log_notes": lesson_log.notes if lesson_log else None,
        "lesson_log_logged_at": lesson_log.logged_at if lesson_log else None,
        "week_timesheet_status": timesheet_status,
        "timesheet_id": timesheet_id,
        "is_substituted_block": False,
    }


def get_week_schedule_sync(
    db: Session,
    organization_id: int,
    week_start: date,
    class_id: int | None = None,
    teacher_id: int | None = None,
) -> list[dict]:
    """Returns active schedule slots for a given week, enriched with occurrence data."""
    from sqlalchemy.orm import joinedload

    week_end = week_start + timedelta(days=6)
    today = date.today()

    active_q = (
        db.query(
            models.ActiveScheduleBlock,
            models.Timeslot,
            models.Subject,
            models.Teacher,
            models.Class,
            models.Room,
        )
        .join(models.Timeslot, models.ActiveScheduleBlock.timeslot_id == models.Timeslot.id)
        .join(models.Subject, models.ActiveScheduleBlock.subject_id == models.Subject.id)
        .join(models.Teacher, models.ActiveScheduleBlock.teacher_id == models.Teacher.id)
        .join(models.Class, models.ActiveScheduleBlock.class_id == models.Class.id)
        .join(models.Room, models.ActiveScheduleBlock.room_id == models.Room.id)
        .filter(
            models.ActiveScheduleBlock.organization_id == organization_id,
            models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
            models.ActiveScheduleBlock.date.between(week_start, week_end),
            models.Timeslot.organization_id == organization_id,
            models.Subject.organization_id == organization_id,
            models.Teacher.organization_id == organization_id,
            models.Class.organization_id == organization_id,
            models.Room.organization_id == organization_id,
        )
    )
    all_active_rows = active_q.all()
    active_baseline_owns_week = bool(all_active_rows)
    active_rows = [
        row for row in all_active_rows
        if (class_id is None or row[0].class_id == class_id)
        and (teacher_id is None or row[0].teacher_id == teacher_id)
    ]

    q = (
        db.query(models.ScheduleOutput)
        .join(models.Lesson, models.ScheduleOutput.lesson_id == models.Lesson.id)
        .filter(
            models.ScheduleOutput.organization_id == organization_id,
            models.ScheduleOutput.is_draft.is_(False),
            models.ScheduleOutput.date.between(week_start, week_end),
        )
        .options(
            joinedload(models.ScheduleOutput.lesson).joinedload(models.Lesson.subject),
            joinedload(models.ScheduleOutput.lesson).joinedload(models.Lesson.teacher),
            joinedload(models.ScheduleOutput.lesson).joinedload(models.Lesson.class_model),
            joinedload(models.ScheduleOutput.timeslot),
            joinedload(models.ScheduleOutput.room),
        )
    )
    if class_id is not None:
        q = q.filter(models.Lesson.class_id == class_id)
    if teacher_id is not None:
        q = q.filter(models.Lesson.teacher_id == teacher_id)

    # Once the new baseline owns a week, legacy rows must not be rendered beside it.
    outputs = [] if active_baseline_owns_week else q.all()

    output_ids = [o.id for o in outputs]
    occ_rows = []
    if output_ids:
        occ_rows = db.query(models.LessonOccurrence).filter(
            models.LessonOccurrence.organization_id == organization_id,
            models.LessonOccurrence.schedule_output_id.in_(output_ids),
            models.LessonOccurrence.is_active.is_(True),
        ).all()
    occurrences = {o.schedule_output_id: o for o in occ_rows}

    llog_rows = []
    if output_ids:
        llog_rows = db.query(models.LessonLog).filter(
            models.LessonLog.organization_id == organization_id,
            models.LessonLog.schedule_output_id.in_(output_ids)
        ).all()
    lesson_logs = {ll.schedule_output_id: ll for ll in llog_rows}

    active_block_ids = [row[0].id for row in active_rows]
    active_occurrence_rows = []
    active_lesson_logs = {}
    if active_block_ids:
        active_occurrence_rows = db.query(models.LessonOccurrence).filter(
            models.LessonOccurrence.organization_id == organization_id,
            models.LessonOccurrence.active_schedule_block_id.in_(active_block_ids),
            models.LessonOccurrence.is_active.is_(True),
        ).all()
        active_log_rows = db.query(models.LessonLog).filter(
            models.LessonLog.organization_id == organization_id,
            models.LessonLog.active_schedule_block_id.in_(active_block_ids),
        ).all()
        active_lesson_logs = {
            log.active_schedule_block_id: log for log in active_log_rows
        }
    active_occurrences = {
        occurrence.active_schedule_block_id: occurrence
        for occurrence in active_occurrence_rows
    }

    op_q = db.query(models.OperationalScheduleBlock).filter(
        models.OperationalScheduleBlock.organization_id == organization_id,
        models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
        models.OperationalScheduleBlock.date.between(week_start, week_end),
    ).options(
        joinedload(models.OperationalScheduleBlock.timeslot),
        joinedload(models.OperationalScheduleBlock.subject),
        joinedload(models.OperationalScheduleBlock.teacher),
        joinedload(models.OperationalScheduleBlock.class_),
        joinedload(models.OperationalScheduleBlock.room),
        joinedload(models.OperationalScheduleBlock.source_occurrence),
    )
    if class_id is not None:
        op_q = op_q.filter(models.OperationalScheduleBlock.class_id == class_id)
    if teacher_id is not None:
        op_q = op_q.filter(models.OperationalScheduleBlock.teacher_id == teacher_id)
    operational_blocks = op_q.all()

    operational_logs = {}
    if operational_blocks:
        op_ids = [block.id for block in operational_blocks]
        op_log_rows = db.query(models.LessonLog).filter(
            models.LessonLog.organization_id == organization_id,
            models.LessonLog.operational_block_id.in_(op_ids),
        ).all()
        operational_logs = {log.operational_block_id: log for log in op_log_rows}

    pairs = list(
        {(o.lesson.class_id, o.lesson.subject_id) for o in outputs}
        | {(row[0].class_id, row[0].subject_id) for row in active_rows}
        | {(b.class_id, b.subject_id) for b in operational_blocks}
    )
    active_modules = _fetch_active_modules(db, pairs)

    # WBS V3 Fase 4: identify substitute blocks
    substituted_blocks: set[tuple[int | None, date, int]] = set()
    for occ in occ_rows:
        if occ.status == models.LessonOccurrenceStatus.SUBSTITUTED \
                and occ.substitute_teacher_id is not None \
                and occ.date is not None \
                and occ.schedule_output is not None:
            substituted_blocks.add((
                occ.substitute_teacher_id,
                occ.date,
                occ.schedule_output.timeslot_id,
            ))

    # WBS Fase 6: buscar timesheets dos professores para esta semana
    teacher_ids = {o.lesson.teacher_id for o in outputs if o.lesson and o.lesson.teacher_id}
    teacher_ids.update({row[0].teacher_id for row in active_rows})
    teacher_ids.update({b.teacher_id for b in operational_blocks if b.teacher_id})
    timesheet_map: dict[int, tuple[str, int | None]] = {}
    if teacher_ids:
        timesheet_rows = db.query(
            models.TeacherWeeklyTimesheet.teacher_id,
            models.TeacherWeeklyTimesheet.status,
            models.TeacherWeeklyTimesheet.id,
        ).filter(
            models.TeacherWeeklyTimesheet.organization_id == organization_id,
            models.TeacherWeeklyTimesheet.teacher_id.in_(list(teacher_ids)),
            models.TeacherWeeklyTimesheet.week_start_date == week_start,
        ).all()
        timesheet_map = {
            row.teacher_id: (row.status.value, row.id)
            for row in timesheet_rows
        }

    planned_slots = [
        _build_week_slot(output, occurrences, lesson_logs, active_modules, today, timesheet_map, substituted_blocks)
        for output in outputs
    ]
    active_slots = [
        _build_active_week_slot(
            row,
            active_occurrences,
            active_lesson_logs,
            active_modules,
            today,
            timesheet_map,
        )
        for row in active_rows
    ]
    operational_slots = [
        _build_operational_week_slot(block, operational_logs.get(block.id), active_modules, today, timesheet_map)
        for block in operational_blocks
    ]
    return planned_slots + active_slots + operational_slots
