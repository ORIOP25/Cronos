from collections import defaultdict
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.future import select
from sqlalchemy import delete, desc
from app import models, schemas

# ==========================================
#  ASYNC (API / FRONTEND)
# ==========================================

# --- TIMESLOTS ---
async def get_timeslots_by_org(db: AsyncSession, org_id: int):
    result = await db.execute(select(models.Timeslot).where(models.Timeslot.organization_id == org_id))
    return result.scalars().all()

async def create_timeslot(db: AsyncSession, item: schemas.TimeslotCreate, org_id: int):
    # O item.model_dump() já vai ter 'start_time' como objeto time.
    db_item = models.Timeslot(**item.model_dump(), organization_id=org_id)
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

# --- LESSONS ---
async def get_lessons_by_org(db: AsyncSession, org_id: int):
    result = await db.execute(select(models.Lesson).where(models.Lesson.organization_id == org_id))
    return result.scalars().all()

async def create_lesson(db: AsyncSession, item: schemas.LessonCreate, org_id: int):
    """
    Cria uma atribuição de professor a uma disciplina/turma.
    
    VALIDAÇÃO CRÍTICA: Verifica se o professor tem competência na disciplina.
    Isto evita que dados "lixo" cheguem ao Solver.
    """
    # 1. Validar turma pertence à organização
    class_query = select(models.Class).where(
        models.Class.id == item.class_id,
        models.Class.organization_id == org_id
    )
    class_result = await db.execute(class_query)
    db_class = class_result.scalars().first()
    if not db_class:
        raise ValueError(f"Turma com ID {item.class_id} não encontrada na organização")

    # 2. Validar disciplina pertence à organização
    subject_query = select(models.Subject).where(
        models.Subject.id == item.subject_id,
        models.Subject.organization_id == org_id
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
    from app.services import teacher_service
    
    teacher_query = (
        select(models.Teacher)
        .where(
            models.Teacher.id == item.teacher_id,
            models.Teacher.organization_id == org_id
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
        models.Lesson.organization_id == org_id
    )
    existing_result = await db.execute(existing_query)
    if existing_result.scalars().first():
        raise ValueError(
            "Já existe uma atribuição deste professor para esta disciplina/turma. "
            "Para mudar o professor, edite a atribuição existente."
        )
    
    # 4. Criar a Lesson
    db_item = models.Lesson(**item.model_dump(), organization_id=org_id)
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

# --- CONSTRAINTS ---
async def create_constraint(db: AsyncSession, item: schemas.ConstraintCreate, org_id: int):
    db_item = models.Constraint(**item.dict(), organization_id=org_id)
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

async def get_constraints_by_org(db: AsyncSession, org_id: int):
    """Lista todas as restrições."""
    result = await db.execute(select(models.Constraint).where(models.Constraint.organization_id == org_id))
    return result.scalars().all()

async def delete_constraint(db: AsyncSession, constraint_id: int, org_id: int):
    """Apaga uma regra de horário."""
    query = select(models.Constraint).where(
        models.Constraint.id == constraint_id,
        models.Constraint.organization_id == org_id
    )
    result = await db.execute(query)
    item = result.scalars().first()
    
    if item:
        await db.delete(item)
        await db.commit()
        return True
    return False

# --- OUTPUT (RESULTADOS) ---
async def get_latest_schedule_by_org(db: AsyncSession, org_id: int):
    """Vai buscar o horário gerado mais recente."""
    
    # 1. Descobrir qual é o último generation_id
    gen_query = select(models.ScheduleOutput.generation_id)\
        .where(models.ScheduleOutput.organization_id == org_id)\
        .order_by(desc(models.ScheduleOutput.id))\
        .limit(1)
    
    gen_res = await db.execute(gen_query)
    latest_gen_id = gen_res.scalars().first()
    
    if not latest_gen_id:
        return []
        
    # 2. Buscar tudo desse ID
    lines_query = select(models.ScheduleOutput).where(
        models.ScheduleOutput.organization_id == org_id,
        models.ScheduleOutput.generation_id == latest_gen_id
    )
    lines_res = await db.execute(lines_query)
    return lines_res.scalars().all()

# --- LIMPEZA GERAL (Reset) ---
async def delete_all_schedule_data(db: AsyncSession, org_id: int):
    """Apaga Outputs, Constraints, Aulas e Slots de uma organização."""
    # Ordem importa por causa das Foreign Keys
    await db.execute(delete(models.ScheduleOutput).where(models.ScheduleOutput.organization_id == org_id))
    await db.execute(delete(models.Constraint).where(models.Constraint.organization_id == org_id))
    await db.execute(delete(models.Lesson).where(models.Lesson.organization_id == org_id))
    await db.execute(delete(models.Timeslot).where(models.Timeslot.organization_id == org_id))
    await db.commit()

# ==========================================
#  SYNC (SOLVER / CELERY)
# ==========================================
# Estas funções são usadas pelo Celery Worker que não suporta bem async/await.

def get_lessons_by_org_sync(db: Session, org_id: int):
    return db.query(models.Lesson).filter(models.Lesson.organization_id == org_id).all()

def get_timeslots_by_org_sync(db: Session, org_id: int):
    return db.query(models.Timeslot).filter(models.Timeslot.organization_id == org_id).all()

def get_constraints_by_org_sync(db: Session, org_id: int):
    return db.query(models.Constraint).filter(models.Constraint.organization_id == org_id).all()

def get_availabilities_by_org_sync(db: Session, org_id: int):
    """
    Retorna todas as disponibilidades dos professores desta organização.
    Faz um JOIN com a tabela Teacher para filtrar pelo org_id.
    """
    return db.query(models.Availability)\
             .join(models.Teacher)\
             .filter(models.Teacher.organization_id == org_id)\
             .all()

def create_schedule_output_sync(db: Session, lesson_id, timeslot_id, room_id, org_id, gen_id):
    db_out = models.ScheduleOutput(
        lesson_id=lesson_id,
        timeslot_id=timeslot_id,
        room_id=room_id,
        organization_id=org_id,
        generation_id=gen_id
    )
    db.add(db_out)
    # Nota: O commit é feito pelo caller no final para performance

def clear_schedule_sync(db: Session, org_id: int):
    """
    Apaga todos os registos de horários gerados anteriormente para esta organização.
    (Usado pelo Celery antes de gravar um novo horário)
    """
    db.query(models.ScheduleOutput)\
      .filter(models.ScheduleOutput.organization_id == org_id)\
      .delete()
    # Não fazemos commit aqui porque o solver_tasks.py faz commit no final de tudo.


# ==========================================
#  SYNC — Sprint 1: dados para o solver modular
# ==========================================

def get_active_lessons_with_subject_sync(db: Session, org_id: int):
    """Lições de turmas não arquivadas, com Subject pré-carregado."""
    return (
        db.query(models.Lesson)
        .join(models.Class, models.Lesson.class_id == models.Class.id)
        .filter(
            models.Lesson.organization_id == org_id,
            models.Class.is_archived == False,  # noqa: E712
        )
        .options(joinedload(models.Lesson.subject))
        .all()
    )


def _get_active_classes_sync(db: Session, org_id: int) -> list:
    return (
        db.query(models.Class)
        .filter(
            models.Class.organization_id == org_id,
            models.Class.is_archived.is_(False),
        )
        .all()
    )


def _collect_desired_pairs_by_links(
    db: Session,
    active_class_ids: set[int],
    class_grade_map: dict[int, int],
) -> tuple[dict[tuple[int, int], int], set[int]]:
    desired_pairs: dict[tuple[int, int], int] = {}
    classes_with_links: set[int] = set()
    link_rows = (
        db.query(models.ClassSubjectLink)
        .filter(
            models.ClassSubjectLink.class_id.in_(active_class_ids),
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
    org_id: int,
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
                    organization_id=org_id,
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


def sync_lessons_from_class_subject_links_sync(db: Session, org_id: int) -> dict:
    """Sincroniza Lesson (legado) a partir de ClassSubjectLink (fonte de verdade).

    Regras:
      - Apenas turmas ativas (não arquivadas).
      - Para turmas com links disciplina-professor, os links têm precedência.
      - Turmas sem links mantêm fallback legado via Lesson existente.
    """
    active_classes = _get_active_classes_sync(db, org_id)
    active_class_ids = {c.id for c in active_classes}
    class_grade_map = {c.id: c.grade_level for c in active_classes}

    if not active_class_ids:
        return {"created": 0, "updated": 0, "deleted": 0}

    desired_pairs, classes_with_links = _collect_desired_pairs_by_links(
        db,
        active_class_ids,
        class_grade_map,
    )

    lesson_rows = (
        db.query(models.Lesson)
        .filter(
            models.Lesson.organization_id == org_id,
            models.Lesson.class_id.in_(active_class_ids),
        )
        .all()
    )

    lessons_by_pair: dict[tuple[int, int], list] = defaultdict(list)
    for lesson in lesson_rows:
        lessons_by_pair[(lesson.class_id, lesson.subject_id)].append(lesson)

    created, updated, deleted = _sync_pair_lessons(
        db,
        org_id,
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


def get_modules_by_subject_sync(db: Session, org_id: int) -> dict:
    """Retorna {subject_id: [Module ordenado]} para todos os subjects da org."""
    modules = (
        db.query(models.Module)
        .join(models.Subject, models.Module.subject_id == models.Subject.id)
        .filter(models.Subject.organization_id == org_id)
        .order_by(models.Module.subject_id, models.Module.order)
        .all()
    )
    result: dict = defaultdict(list)
    for module in modules:
        result[module.subject_id].append(module)
    return dict(result)


def get_class_progress_map_sync(db: Session, org_id: int) -> dict:
    """Retorna {(class_id, module_id): hours_completed} para toda a org."""
    records = (
        db.query(models.ClassProgress)
        .join(models.Class, models.ClassProgress.class_id == models.Class.id)
        .filter(models.Class.organization_id == org_id)
        .all()
    )
    return {(r.class_id, r.module_id): r.hours_completed for r in records}


def get_org_settings_sync(db: Session, org_id: int):
    """Retorna as OrganizationSettings desta org, da mais recente para a mais antiga."""
    return (
        db.query(models.OrganizationSettings)
        .filter(models.OrganizationSettings.org_id == org_id)
        .order_by(models.OrganizationSettings.id.desc())
        .all()
    )


def get_calendar_events_sync(db: Session, org_id: int):
    """Retorna todos os SchoolCalendarEvents desta org."""
    return (
        db.query(models.SchoolCalendarEvent)
        .filter(models.SchoolCalendarEvent.org_id == org_id)
        .all()
    )


def update_class_projected_end_date_sync(db: Session, class_id: int, end_date: date) -> None:
    """Atualiza projected_end_date de uma turma."""
    db.query(models.Class).filter(models.Class.id == class_id).update(
        {"projected_end_date": end_date}
    )


def clear_future_schedule_sync(db: Session, org_id: int) -> None:
    """Apaga apenas ScheduleOutput com date > hoje (imutabilidade do passado).
    Registos sem data (legado) também são apagados para não quebrar FK consistency.
    """
    today = date.today()
    db.query(models.ScheduleOutput).filter(
        models.ScheduleOutput.organization_id == org_id,
        (models.ScheduleOutput.date == None) | (models.ScheduleOutput.date > today),  # noqa: E711
    ).delete(synchronize_session="fetch")


def create_schedule_output_with_date_sync(
    db: Session,
    lesson_id: int,
    timeslot_id: int,
    room_id: int,
    output_date: date,
    org_id: int,
    gen_id: str,
    is_draft: bool = False,
) -> None:
    """Cria uma linha de ScheduleOutput com data absoluta."""
    db.add(
        models.ScheduleOutput(
            lesson_id=lesson_id,
            timeslot_id=timeslot_id,
            room_id=room_id,
            date=output_date,
            organization_id=org_id,
            generation_id=gen_id,
            is_draft=is_draft,
        )
    )


# ---------------------------------------------------------------------------
# Funções de gestão de rascunhos (Sprint 3)
# ---------------------------------------------------------------------------

def get_active_future_pattern_sync(db: Session, org_id: int) -> dict:
    """Retorna o padrão semanal ativo como dict {(lesson_id, ts_id): 1}.

    Usado pelo solver em modo 'repair' para minimizar perturbações.
    Lê apenas ScheduleOutput futuros (date > hoje) não-draft.
    """
    today = date.today()
    rows = (
        db.query(models.ScheduleOutput.lesson_id, models.ScheduleOutput.timeslot_id)
        .filter(
            models.ScheduleOutput.organization_id == org_id,
            models.ScheduleOutput.is_draft.is_(False),
            models.ScheduleOutput.date > today,
        )
        .distinct()
        .all()
    )
    return {(r.lesson_id, r.timeslot_id): 1 for r in rows}


def list_draft_gen_ids_sync(db: Session, org_id: int) -> list[dict]:
    """Lista rascunhos pendentes de aprovação para esta organização.

    Retorna um registo por generation_id com contagem, intervalo de datas.
    """
    from sqlalchemy import func as sa_func

    rows = (
        db.query(
            models.ScheduleOutput.generation_id,
            sa_func.count(models.ScheduleOutput.id).label("count"),
            sa_func.min(models.ScheduleOutput.date).label("earliest_date"),
            sa_func.max(models.ScheduleOutput.date).label("latest_date"),
        )
        .filter(
            models.ScheduleOutput.organization_id == org_id,
            models.ScheduleOutput.is_draft.is_(True),
        )
        .group_by(models.ScheduleOutput.generation_id)
        .all()
    )
    return [
        {
            "generation_id": r.generation_id,
            "count": r.count,
            "earliest_date": r.earliest_date,
            "latest_date": r.latest_date,
        }
        for r in rows
    ]


def approve_draft_sync(db: Session, org_id: int, gen_id: str) -> int:
    """Aprova um rascunho: elimina o horário ativo futuro e promove o rascunho.

    Retorna o número de blocos promovidos.
    """
    today = date.today()
    # 1. Apagar horário ativo futuro
    db.query(models.ScheduleOutput).filter(
        models.ScheduleOutput.organization_id == org_id,
        models.ScheduleOutput.is_draft.is_(False),
        (models.ScheduleOutput.date == None) | (models.ScheduleOutput.date > today),  # noqa: E711
    ).delete(synchronize_session="fetch")

    # 2. Promover rascunho a ativo
    count = (
        db.query(models.ScheduleOutput)
        .filter(
            models.ScheduleOutput.organization_id == org_id,
            models.ScheduleOutput.generation_id == gen_id,
            models.ScheduleOutput.is_draft.is_(True),
        )
        .update({"is_draft": False}, synchronize_session="fetch")
    )
    db.commit()
    return count


def reject_draft_sync(db: Session, org_id: int, gen_id: str) -> int:
    """Rejeita e elimina um rascunho. Retorna o número de registos apagados."""
    count = (
        db.query(models.ScheduleOutput)
        .filter(
            models.ScheduleOutput.organization_id == org_id,
            models.ScheduleOutput.generation_id == gen_id,
            models.ScheduleOutput.is_draft.is_(True),
        )
        .delete(synchronize_session="fetch")
    )
    db.commit()
    return count


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
    """Fetches active module data per (class_id, subject_id) pair."""
    active: dict[tuple, dict | None] = {}
    for cls_id, subj_id in pairs:
        modules = (
            db.query(models.Module)
            .filter(models.Module.subject_id == subj_id)
            .order_by(models.Module.order)
            .all()
        )
        if not modules:
            active[(cls_id, subj_id)] = None
            continue
        progress_rows = db.query(models.ClassProgress).filter(
            models.ClassProgress.class_id == cls_id,
            models.ClassProgress.module_id.in_([m.id for m in modules]),
        ).all()
        progress_map = {p.module_id: p for p in progress_rows}
        mod = _find_active_module(modules, progress_map)
        active[(cls_id, subj_id)] = (
            {"id": mod.id, "name": mod.name, "hours_total": mod.hours_total}
            if mod else None
        )
    return active


def _build_week_slot(
    output: models.ScheduleOutput,
    occurrences: dict,
    active_modules: dict,
    today: date,
) -> dict:
    """Builds a single WeekSlotRead dict from a ScheduleOutput row."""
    occ = occurrences.get(output.id)
    lesson = output.lesson
    ts = output.timeslot
    mod_data = active_modules.get((lesson.class_id, lesson.subject_id))
    return {
        "schedule_output_id": output.id,
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
        "occurrence_status": occ.status.value if occ else None,
        "hours_given": occ.hours_given if occ else None,
    }


def get_week_schedule_sync(
    db: Session,
    org_id: int,
    week_start: date,
    class_id: int | None = None,
    teacher_id: int | None = None,
) -> list[dict]:
    """Returns active schedule slots for a given week, enriched with occurrence data."""
    from datetime import timedelta
    from sqlalchemy.orm import joinedload

    week_end = week_start + timedelta(days=6)
    today = date.today()

    q = (
        db.query(models.ScheduleOutput)
        .join(models.Lesson, models.ScheduleOutput.lesson_id == models.Lesson.id)
        .filter(
            models.ScheduleOutput.organization_id == org_id,
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

    outputs = q.all()
    if not outputs:
        return []

    output_ids = [o.id for o in outputs]
    occ_rows = db.query(models.LessonOccurrence).filter(
        models.LessonOccurrence.schedule_output_id.in_(output_ids)
    ).all()
    occurrences = {o.schedule_output_id: o for o in occ_rows}

    pairs = list({(o.lesson.class_id, o.lesson.subject_id) for o in outputs})
    active_modules = _fetch_active_modules(db, pairs)

    return [
        _build_week_slot(output, occurrences, active_modules, today)
        for output in outputs
    ]


def get_diff_sync(db: Session, org_id: int, gen_id: str) -> dict:
    """Computa o diff entre o rascunho e o horário ativo.

    Retorna:
      added   — blocos no rascunho mas não no ativo (mesmo timeslot+data)
      removed — blocos no ativo mas não no rascunho
      total_draft   — total de blocos no rascunho
      total_active  — total de blocos ativos futuros
    """
    today = date.today()

    def _fetch_set(is_draft_val: bool, generation_filter=None):
        q = db.query(
            models.ScheduleOutput.lesson_id,
            models.ScheduleOutput.timeslot_id,
            models.ScheduleOutput.room_id,
            models.ScheduleOutput.date,
        ).filter(
            models.ScheduleOutput.organization_id == org_id,
            models.ScheduleOutput.is_draft.is_(is_draft_val),
            models.ScheduleOutput.date > today,
        )
        if generation_filter:
            q = q.filter(models.ScheduleOutput.generation_id == generation_filter)
        return {(r.lesson_id, r.timeslot_id, r.date) for r in q.all()}

    draft_set = _fetch_set(True, gen_id)
    active_set = _fetch_set(False)

    added = len(draft_set - active_set)
    removed = len(active_set - draft_set)

    return {
        "added": added,
        "removed": removed,
        "unchanged": len(draft_set & active_set),
        "total_draft": len(draft_set),
        "total_active": len(active_set),
    }
