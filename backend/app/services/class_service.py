from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.future import select
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app import models, schemas


# --- HELPERS INTERNOS ---
async def _get_class_by_org(db: AsyncSession, class_id: int, org_id: int):
    """Busca uma turma por id + org_id (isolamento de tenant)."""
    result = await db.execute(
        select(models.Class).where(
            models.Class.id == class_id,
            models.Class.organization_id == org_id
        )
    )
    return result.scalars().first()


async def _get_course_by_org(db: AsyncSession, course_id: int, org_id: int):
    result = await db.execute(
        select(models.Course).where(
            models.Course.id == course_id,
            models.Course.organization_id == org_id
        )
    )
    return result.scalars().first()


async def _get_class_by_course_and_org(db: AsyncSession, class_id: int, course_id: int, org_id: int):
    result = await db.execute(
        select(models.Class).where(
            models.Class.id == class_id,
            models.Class.course_id == course_id,
            models.Class.organization_id == org_id
        )
    )
    return result.scalars().first()


# --- ASYNC (API) ---
async def get_classes_by_org(db: AsyncSession, org_id: int):
    # Ordenar por nome
    result = await db.execute(select(models.Class).where(models.Class.organization_id == org_id).order_by(models.Class.name))
    return result.scalars().all()

async def get_class_details(db: AsyncSession, class_id: int, org_id: int):
    """
    Busca turma com o curso associado (Eager Load).
    
    🔐 Security: Filtra por org_id - cada organização só vê suas turmas
    ⚙️ Stability: selectinload previne N+1 queries e lazy loading em async context
    ⚡ Optimization: Uma query com JOIN retorna tudo de uma vez
    📈 Scalability: Padrão aplicável a qualquer entity com relationships
    
    Retorna: Class com course populated, ou None se não encontrada
    """
    query = select(models.Class).where(
        models.Class.id == class_id,
        models.Class.organization_id == org_id
    ).options(
        selectinload(models.Class.course)  # Carrega o curso associado
    )
    
    result = await db.execute(query)
    return result.scalars().first()

async def create_class(db: AsyncSession, item: schemas.ClassCreate, org_id: int):
    db_course = await _get_course_by_org(db, item.course_id, org_id)
    if not db_course:
        return "COURSE_NOT_FOUND"

    db_item = models.Class(**item.model_dump(), organization_id=org_id)
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

async def update_class(
    db: AsyncSession, 
    class_id: int, 
    class_in: schemas.ClassUpdate,
    org_id: int
):
    db_class = await _get_class_by_org(db, class_id, org_id)
    
    if not db_class:
        return None

    update_data = class_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_class, field, value)

    if db_class.end_year <= db_class.start_year:
        return "INVALID_YEAR_RANGE"

    db.add(db_class)
    await db.commit()
    await db.refresh(db_class)
    return db_class

async def delete_class(db: AsyncSession, class_id: int, org_id: int):
    """Remove uma turma e dependências associadas (cascade explícito)."""
    item = await _get_class_by_org(db, class_id, org_id)
    
    if not item:
        return "NOT_FOUND"

    await _delete_class_with_dependencies(db, item.id)
    await db.commit()
    return "SUCCESS"


async def get_classes_by_course(db: AsyncSession, course_id: int, org_id: int):
    query = (
        select(models.Class)
        .where(
            models.Class.course_id == course_id,
            models.Class.organization_id == org_id
        )
        .order_by(models.Class.grade_level, models.Class.name)
    )
    result = await db.execute(query)
    return result.scalars().all()


async def create_class_in_course(db: AsyncSession, course_id: int, item: schemas.ClassCreateInCourse, org_id: int):
    db_course = await _get_course_by_org(db, course_id, org_id)
    if not db_course:
        return "COURSE_NOT_FOUND"

    db_item = models.Class(
        **item.model_dump(),
        course_id=course_id,
        organization_id=org_id
    )
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item


async def update_class_in_course(
    db: AsyncSession,
    course_id: int,
    class_id: int,
    class_in: schemas.ClassUpdateInCourse,
    org_id: int,
):
    db_class = await _get_class_by_course_and_org(db, class_id, course_id, org_id)
    if not db_class:
        return "NOT_FOUND"

    update_data = class_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_class, field, value)

    if db_class.end_year <= db_class.start_year:
        return "INVALID_YEAR_RANGE"

    db.add(db_class)
    await db.commit()
    await db.refresh(db_class)
    return db_class


async def delete_class_in_course(db: AsyncSession, course_id: int, class_id: int, org_id: int):
    db_class = await _get_class_by_course_and_org(db, class_id, course_id, org_id)
    if not db_class:
        return "NOT_FOUND"

    await _delete_class_with_dependencies(db, db_class.id)
    await db.commit()
    return "SUCCESS"


async def _delete_class_with_dependencies(db: AsyncSession, class_id: int):
    lesson_ids_query = select(models.Lesson.id).where(models.Lesson.class_id == class_id)

    await db.execute(
        delete(models.Substitution).where(
            models.Substitution.lesson_id.in_(lesson_ids_query)
        )
    )

    await db.execute(
        delete(models.ScheduleOutput).where(
            models.ScheduleOutput.lesson_id.in_(lesson_ids_query)
        )
    )

    await db.execute(delete(models.Lesson).where(models.Lesson.class_id == class_id))
    await db.execute(delete(models.Class).where(models.Class.id == class_id))

async def get_class_curriculum(db: AsyncSession, class_id: int, org_id: int):
    """
    Retorna a lista de disciplinas que a turma precisa ter.
    
    A turma está associada a um curso, e o curso tem disciplinas.
    Esta função facilita o frontend para apresentar qual disciplinas a turma necessita.
    
    Útil para a "Matriz de Distribuição de Serviço" (Atribuição de Professores).
    
    Retorna: List[SubjectRead]
    """
    # 1. Buscar a Turma
    db_class = await _get_class_by_org(db, class_id, org_id)
    
    if not db_class:
        return []
    
    # 2. Se não tiver curso associado, retorna vazio
    if not db_class.course_id:
        return []
    
    # 3. Buscar o Curso e carregar as Disciplinas (LEFT JOIN)
    course_query = (
        select(models.Course)
        .where(models.Course.id == db_class.course_id)
        .options(selectinload(models.Course.subjects))
    )
    course_result = await db.execute(course_query)
    course = course_result.scalars().first()
    
    if not course:
        return []
    
    # 4. Retornar as disciplinas do curso
    return course.subjects if course.subjects else []

# --- SYNC (SOLVER) ---
def get_classes_by_org_sync(db: Session, org_id: int):
    return db.query(models.Class).filter(models.Class.organization_id == org_id).all()


# ==========================================
#  DASHBOARD DA TURMA (ClassFullDetail)
# ==========================================

def _build_module_data(module, progress_map: dict) -> dict:
    """Constrói dados de um módulo com o seu progresso atual."""
    progress = progress_map.get(module.id)
    hours_done = progress.hours_completed if progress else 0
    hours_debt = progress.hours_debt if progress else 0
    completed = progress.is_completed if progress else False
    pct = min(100.0, round((hours_done / module.hours_total) * 100, 1)) if module.hours_total > 0 else 0.0

    return {
        "id": module.id,
        "name": module.name,
        "code": module.code,
        "hours_total": module.hours_total,
        "order": module.order,
        "hours_completed": hours_done,
        "hours_debt": hours_debt,
        "is_completed": completed,
        "percentage": pct,
    }


def _build_subject_with_progress(subject, progress_map: dict) -> dict:
    """Constrói dados de uma disciplina com módulos e progresso agregado."""
    modules_data = []
    subject_total = 0
    subject_completed = 0

    for module in sorted(subject.modules, key=lambda m: m.order):
        module_data = _build_module_data(module, progress_map)
        modules_data.append(module_data)
        subject_total += module.hours_total
        subject_completed += module_data["hours_completed"]

    overall_pct = min(100.0, round((subject_completed / subject_total) * 100, 1)) if subject_total > 0 else 0.0

    return {
        "id": subject.id,
        "name": subject.name,
        "required_room_type": subject.required_room_type,
        "modules": modules_data,
        "total_hours": subject_total,
        "completed_hours": subject_completed,
        "overall_percentage": overall_pct,
    }


async def get_class_full_details(db: AsyncSession, class_id: int, org_id: int):
    """
    Busca turma com curso, disciplinas, módulos e progresso.
    Retorna a árvore completa para o dashboard da turma (ClassDetails.jsx).
    
    FONTE DE VERDADE: ClassSubjectLink (as disciplinas atribuídas à turma),
    NÃO a lista de disciplinas do curso. Isto permite que cada turma tenha
    disciplinas diferentes, refletindo a gestão feita na página ClassSubjects.
    
    4 Pilares:
    🔐 Security: Filtra por org_id — cada organização só vê suas turmas
    ⚡ Optimization: 2 queries com selectinload (vs N+1 de lazy loading)
    ⚙️ Stability: Progresso calculado server-side como fonte de verdade única
    📈 Scalability: Padrão extensível para futuras features (alunos, notas)
    """
    # 1. Buscar turma com curso
    query = select(models.Class).where(
        models.Class.id == class_id,
        models.Class.organization_id == org_id
    ).options(
        selectinload(models.Class.course),
    )
    result = await db.execute(query)
    db_class = result.scalars().first()
    
    if not db_class:
        return None
    
    # 2. Construir base da resposta
    response = {
        "id": db_class.id,
        "name": db_class.name,
        "size": db_class.size,
        "grade_level": db_class.grade_level,
        "start_year": db_class.start_year,
        "end_year": db_class.end_year,
        "organization_id": db_class.organization_id,
        "course_id": db_class.course_id,
        "course": db_class.course,
        "subjects": []
    }
    
    # 3. Buscar disciplinas da turma via ClassSubjectLink (fonte de verdade)
    links_query = select(models.ClassSubjectLink).where(
        models.ClassSubjectLink.class_id == class_id,
        models.ClassSubjectLink.grade_level == db_class.grade_level
    ).options(
        selectinload(models.ClassSubjectLink.subject).selectinload(models.Subject.modules)
    )
    links_result = await db.execute(links_query)
    links = links_result.scalars().all()
    
    if not links:
        return response
    
    # 4. Buscar progresso EXPLICITAMENTE por class_id (isolamento de turma)
    #    Query directa em vez de relationship para garantir que não há
    #    contaminação entre turmas via cache do ORM (identity map).
    progress_query = select(models.ClassProgress).where(
        models.ClassProgress.class_id == class_id
    )
    progress_result = await db.execute(progress_query)
    progress_records = progress_result.scalars().all()
    progress_map = {p.module_id: p for p in progress_records}
    
    # 5. Construir árvore de disciplinas com progresso
    for link in sorted(links, key=lambda l: l.subject.name if l.subject else ""):
        subject = link.subject
        if not subject:
            continue
        response["subjects"].append(_build_subject_with_progress(subject, progress_map))
    
    return response


async def update_class_progress(
    db: AsyncSession, 
    class_id: int, 
    progress_updates: list[schemas.ClassProgressUpdate],
    org_id: int
):
    """
    Atualiza o progresso de módulos para uma turma (upsert).
    Auto-calcula is_completed quando hours_completed >= hours_total.
    
    FONTE DE VERDADE: ClassSubjectLink — só permite atualizar módulos
    de disciplinas effectivamente atribuídas à turma.
    
    4 Pilares:
    🔐 Security: Valida turma pertence à org + módulo pertence às disciplinas da turma
    ⚡ Optimization: Upsert batch via ON CONFLICT (evita N queries individuais)
    ⚙️ Stability: Transação atómica — ou atualiza tudo ou nada
    📈 Scalability: Suporta atualização de múltiplos módulos de uma vez
    """
    from datetime import datetime, timezone
    
    # 1. Validar turma existe e pertence à org
    db_class = await _get_class_by_org(db, class_id, org_id)
    
    if not db_class:
        return "NOT_FOUND"
    
    # 2. Buscar módulos válidos das disciplinas atribuídas à turma (ClassSubjectLink)
    links_query = select(models.ClassSubjectLink).where(
        models.ClassSubjectLink.class_id == class_id,
        models.ClassSubjectLink.grade_level == db_class.grade_level
    ).options(
        selectinload(models.ClassSubjectLink.subject).selectinload(models.Subject.modules)
    )
    links_result = await db.execute(links_query)
    links = links_result.scalars().all()
    
    if not links:
        return "NO_SUBJECTS"
    
    # 3. Construir mapa de módulos válidos: {module_id: hours_total}
    valid_modules = {}
    for link in links:
        if link.subject:
            for module in link.subject.modules:
                valid_modules[module.id] = module.hours_total
    
    # 4. Validar que todos os module_ids pertencem às disciplinas da turma
    for update in progress_updates:
        if update.module_id not in valid_modules:
            return f"INVALID_MODULE:{update.module_id}"
    
    # 5. Upsert via PostgreSQL ON CONFLICT
    now = datetime.now(timezone.utc)
    for update in progress_updates:
        hours_total = valid_modules[update.module_id]
        # Clamp: não permitir mais horas que o total
        hours = min(update.hours_completed, hours_total)
        is_done = hours >= hours_total
        
        stmt = pg_insert(models.ClassProgress).values(
            class_id=class_id,
            module_id=update.module_id,
            hours_completed=hours,
            is_completed=is_done,
            updated_at=now
        ).on_conflict_do_update(
            constraint="uq_class_module",
            set_={
                "hours_completed": hours,
                "is_completed": is_done,
                "updated_at": now
            }
        )
        await db.execute(stmt)
    
    await db.commit()
    return "SUCCESS"


# ==========================================
#  DISCIPLINAS DA TURMA (Class-Subject Link)
#  Gestão curso-cêntrica de professores
# ==========================================

async def get_class_subjects(db: AsyncSession, class_id: int, org_id: int):
    """
    Lista disciplinas associadas à turma (para o grade_level atual).
    Inclui professor atribuído (se houver).
    
    Retorna: ClassSubjectsListRead
    """
    # 1. Buscar turma com curso
    class_query = select(models.Class).where(
        models.Class.id == class_id,
        models.Class.organization_id == org_id
    ).options(selectinload(models.Class.course))
    
    result = await db.execute(class_query)
    db_class = result.scalars().first()
    
    if not db_class:
        return None
    
    # 2. Buscar disciplinas associadas à turma para o grade_level atual
    links_query = select(models.ClassSubjectLink).where(
        models.ClassSubjectLink.class_id == class_id,
        models.ClassSubjectLink.grade_level == db_class.grade_level
    ).options(
        selectinload(models.ClassSubjectLink.subject),
        selectinload(models.ClassSubjectLink.teacher)
    )
    
    links_result = await db.execute(links_query)
    links = links_result.scalars().all()
    
    # 3. Construir resposta
    subjects_data = []
    for link in sorted(links, key=lambda l: l.subject.name if l.subject else ""):
        subjects_data.append({
            "id": link.id,
            "subject_id": link.subject_id,
            "subject_name": link.subject.name if link.subject else "",
            "required_room_type": link.subject.required_room_type if link.subject else "normal",
            "grade_level": link.grade_level,
            "teacher_id": link.teacher_id,
            "teacher_name": link.teacher.name if link.teacher else None,
        })
    
    return {
        "class_id": db_class.id,
        "class_name": db_class.name,
        "course_name": db_class.course.name if db_class.course else None,
        "course_abbreviation": db_class.course.abbreviation if db_class.course else None,
        "grade_level": db_class.grade_level,
        "subjects": subjects_data
    }


async def add_class_subject(
    db: AsyncSession, 
    class_id: int, 
    subject_id: int, 
    org_id: int
):
    """
    Adiciona uma disciplina à turma (para o grade_level atual).
    
    Validações:
    - Turma existe e pertence à org
    - Disciplina existe e pertence à org
    - Disciplina não está já associada à turma neste grade_level
    """
    # 1. Buscar turma
    db_class = await _get_class_by_org(db, class_id, org_id)
    
    if not db_class:
        return "CLASS_NOT_FOUND"
    
    # 2. Buscar disciplina
    subject_query = select(models.Subject).where(
        models.Subject.id == subject_id,
        models.Subject.organization_id == org_id
    )
    subject_result = await db.execute(subject_query)
    db_subject = subject_result.scalars().first()
    
    if not db_subject:
        return "SUBJECT_NOT_FOUND"
    
    # 3. Verificar se já existe
    existing_query = select(models.ClassSubjectLink).where(
        models.ClassSubjectLink.class_id == class_id,
        models.ClassSubjectLink.subject_id == subject_id,
        models.ClassSubjectLink.grade_level == db_class.grade_level
    )
    existing_result = await db.execute(existing_query)
    
    if existing_result.scalars().first():
        return "ALREADY_EXISTS"
    
    # 4. Criar associação
    link = models.ClassSubjectLink(
        class_id=class_id,
        subject_id=subject_id,
        grade_level=db_class.grade_level,
        teacher_id=None
    )
    db.add(link)
    
    # 5. Sync currículo: garantir que a disciplina está no course_subject_link
    existing_cs = await db.execute(
        select(models.course_subject_link).where(
            models.course_subject_link.c.course_id == db_class.course_id,
            models.course_subject_link.c.subject_id == subject_id
        )
    )
    if not existing_cs.first():
        await db.execute(
            models.course_subject_link.insert().values(
                course_id=db_class.course_id, subject_id=subject_id
            )
        )
    
    await db.commit()
    await db.refresh(link)
    
    return link


async def update_class_subject_teacher(
    db: AsyncSession,
    class_id: int,
    subject_id: int,
    payload: schemas.ClassSubjectUpdate,
    org_id: int
):
    """
    Atualiza uma associação disciplina-turma: professor.
    Usa exclude_unset para distinguir entre 'não enviado' e 'enviado como null'.
    
    Validações:
    - Associação existe
    - Se teacher_id não é None, professor existe e tem competência na disciplina
    """
    update_data = payload.model_dump(exclude_unset=True)
    
    # 1. Buscar turma para obter grade_level
    db_class = await _get_class_by_org(db, class_id, org_id)
    
    if not db_class:
        return "CLASS_NOT_FOUND"
    
    # 2. Buscar associação
    link_query = select(models.ClassSubjectLink).where(
        models.ClassSubjectLink.class_id == class_id,
        models.ClassSubjectLink.subject_id == subject_id,
        models.ClassSubjectLink.grade_level == db_class.grade_level
    )
    link_result = await db.execute(link_query)
    link = link_result.scalars().first()
    
    if not link:
        return "LINK_NOT_FOUND"
    
    # 3. Se teacher_id foi enviado, validar
    if "teacher_id" in update_data:
        teacher_id = update_data["teacher_id"]
        if teacher_id is not None:
            # Validar professor existe e pertence à org
            teacher_query = select(models.Teacher).where(
                models.Teacher.id == teacher_id,
                models.Teacher.organization_id == org_id
            ).options(selectinload(models.Teacher.subjects))
            
            teacher_result = await db.execute(teacher_query)
            db_teacher = teacher_result.scalars().first()
            
            if not db_teacher:
                return "TEACHER_NOT_FOUND"
            
            # Validar professor tem competência na disciplina
            teacher_subject_ids = [s.id for s in db_teacher.subjects]
            if subject_id not in teacher_subject_ids:
                return "NO_COMPETENCY"
    
    # 4. Aplicar alterações
    for field, value in update_data.items():
        setattr(link, field, value)
    
    await db.commit()
    await db.refresh(link)
    
    return link


async def remove_class_subject(
    db: AsyncSession,
    class_id: int,
    subject_id: int,
    org_id: int
):
    """
    Remove uma disciplina da turma (para o grade_level atual).
    """
    # 1. Buscar turma
    db_class = await _get_class_by_org(db, class_id, org_id)
    
    if not db_class:
        return "CLASS_NOT_FOUND"
    
    # 2. Buscar associação
    link_query = select(models.ClassSubjectLink).where(
        models.ClassSubjectLink.class_id == class_id,
        models.ClassSubjectLink.subject_id == subject_id,
        models.ClassSubjectLink.grade_level == db_class.grade_level
    )
    link_result = await db.execute(link_query)
    link = link_result.scalars().first()
    
    if not link:
        return "NOT_FOUND"
    
    # 3. Remover
    await db.delete(link)
    
    # 4. Sync currículo: se nenhuma outra turma do curso usa esta disciplina, remover do currículo
    course_id = db_class.course_id
    # Subquery: IDs de turmas do mesmo curso
    course_class_ids = select(models.Class.id).where(models.Class.course_id == course_id)
    other_links = await db.execute(
        select(models.ClassSubjectLink.id).where(
            models.ClassSubjectLink.subject_id == subject_id,
            models.ClassSubjectLink.class_id.in_(course_class_ids),
            models.ClassSubjectLink.id != link.id
        )
    )
    if not other_links.scalars().first():
        await db.execute(
            models.course_subject_link.delete().where(
                models.course_subject_link.c.course_id == course_id,
                models.course_subject_link.c.subject_id == subject_id
            )
        )
    
    await db.commit()
    
    return "SUCCESS"


async def get_available_subjects_for_class(
    db: AsyncSession,
    class_id: int,
    org_id: int
):
    """
    Lista disciplinas disponíveis para adicionar à turma.
    (Disciplinas da org que ainda não estão associadas à turma neste grade_level)
    """
    # 1. Buscar turma
    db_class = await _get_class_by_org(db, class_id, org_id)
    
    if not db_class:
        return []
    
    # 2. Buscar IDs das disciplinas já associadas
    existing_query = select(models.ClassSubjectLink.subject_id).where(
        models.ClassSubjectLink.class_id == class_id,
        models.ClassSubjectLink.grade_level == db_class.grade_level
    )
    existing_result = await db.execute(existing_query)
    existing_ids = {row[0] for row in existing_result.all()}
    
    # 3. Buscar todas as disciplinas da org que não estão associadas
    if existing_ids:
        subjects_query = select(models.Subject).options(
            selectinload(models.Subject.modules)
        ).where(
            models.Subject.organization_id == org_id,
            models.Subject.id.notin_(existing_ids)
        ).order_by(models.Subject.name)
    else:
        subjects_query = select(models.Subject).options(
            selectinload(models.Subject.modules)
        ).where(
            models.Subject.organization_id == org_id
        ).order_by(models.Subject.name)
    
    subjects_result = await db.execute(subjects_query)
    return subjects_result.scalars().all()


async def get_eligible_teachers_for_subject(
    db: AsyncSession,
    subject_id: int,
    org_id: int
):
    """
    Lista professores elegíveis para lecionar uma disciplina.
    (Professores que têm competência na disciplina via teacher_subject_link)
    
    Também indica quantas turmas o professor já tem atribuídas.
    
    Optimization (P1): Usa SQL JOIN via teacher_subject_link em vez de
    carregar todos os professores e filtrar em Python.
    """
    from sqlalchemy import func
    
    # 1. Buscar disciplina para validar que pertence à org
    subject_query = select(models.Subject).where(
        models.Subject.id == subject_id,
        models.Subject.organization_id == org_id
    )
    subject_result = await db.execute(subject_query)
    db_subject = subject_result.scalars().first()
    
    if not db_subject:
        return []
    
    # 2. Buscar professores com competência via JOIN (não carrega todos)
    teachers_query = (
        select(models.Teacher)
        .join(
            models.teacher_subject_link,
            models.Teacher.id == models.teacher_subject_link.c.teacher_id
        )
        .where(
            models.teacher_subject_link.c.subject_id == subject_id,
            models.Teacher.organization_id == org_id,
        )
        .order_by(models.Teacher.name)
    )
    
    teachers_result = await db.execute(teachers_query)
    eligible = teachers_result.scalars().all()
    
    if not eligible:
        return []
    
    # 3. Contar quantas turmas cada professor já tem para esta disciplina
    counts_query = select(
        models.ClassSubjectLink.teacher_id,
        func.count(models.ClassSubjectLink.id).label("count")
    ).where(
        models.ClassSubjectLink.subject_id == subject_id,
        models.ClassSubjectLink.teacher_id.isnot(None)
    ).group_by(models.ClassSubjectLink.teacher_id)
    
    counts_result = await db.execute(counts_query)
    counts_map = {row[0]: row[1] for row in counts_result.all()}
    
    # 4. Construir resposta
    result = []
    for teacher in eligible:
        result.append({
            "id": teacher.id,
            "name": teacher.name,
            "is_assigned_elsewhere": teacher.id in counts_map,
            "current_classes_count": counts_map.get(teacher.id, 0)
        })
    
    return result