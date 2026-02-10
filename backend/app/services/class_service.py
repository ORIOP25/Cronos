from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.future import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app import models, schemas
from app.models import Lesson

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
    # **item.model_dump() injeta 'name' e 'size' automaticamente
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
    query = select(models.Class).where(
        models.Class.id == class_id,
        models.Class.organization_id == org_id
    )
    result = await db.execute(query)
    db_class = result.scalars().first()
    
    if not db_class:
        return None

    update_data = class_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_class, field, value)

    db.add(db_class)
    await db.commit()
    await db.refresh(db_class)
    return db_class

async def delete_class(db: AsyncSession, class_id: int, org_id: int):
    """
    Remove uma turma. Protege se existirem aulas (Lessons) associadas.
    """
    # 1. Buscar turma
    result = await db.execute(select(models.Class).where(models.Class.id == class_id, models.Class.organization_id == org_id))
    item = result.scalars().first()
    
    if not item:
        return "NOT_FOUND"

    # 2. VERIFICAÇÃO DE INTEGRIDADE
    query_dep = select(models.Lesson).where(models.Lesson.class_id == class_id)
    result_dep = await db.execute(query_dep)
    
    if result_dep.first():
        return "DEPENDENCY_ERROR"

    # 3. Apagar
    await db.delete(item)
    await db.commit()
    return "SUCCESS"

async def get_class_curriculum(db: AsyncSession, class_id: int, org_id: int):
    """
    Retorna a lista de disciplinas que a turma precisa ter.
    
    A turma está associada a um curso, e o curso tem disciplinas.
    Esta função facilita o frontend para apresentar qual disciplinas a turma necessita.
    
    Útil para a "Matriz de Distribuição de Serviço" (Atribuição de Professores).
    
    Retorna: List[SubjectRead]
    """
    # 1. Buscar a Turma
    class_query = select(models.Class).where(
        models.Class.id == class_id,
        models.Class.organization_id == org_id
    )
    class_result = await db.execute(class_query)
    db_class = class_result.scalars().first()
    
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

async def get_class_full_details(db: AsyncSession, class_id: int, org_id: int):
    """
    Busca turma com curso, disciplinas, módulos e progresso.
    Retorna a árvore completa para o dashboard da turma (ClassDetails.jsx).
    
    4 Pilares:
    🔐 Security: Filtra por org_id — cada organização só vê suas turmas
    ⚡ Optimization: 2 queries com selectinload (vs N+1 de lazy loading)
    ⚙️ Stability: Progresso calculado server-side como fonte de verdade única
    📈 Scalability: Padrão extensível para futuras features (alunos, notas)
    
    Query 1: Class + Course + ProgressRecords
    Query 2: Course → Subjects → Modules (apenas se há curso)
    """
    # 1. Buscar turma com curso e registos de progresso
    query = select(models.Class).where(
        models.Class.id == class_id,
        models.Class.organization_id == org_id
    ).options(
        selectinload(models.Class.course),
        selectinload(models.Class.progress_records)
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
    
    # 3. Se não tiver curso, retorna sem subjects
    if not db_class.course_id:
        return response
    
    # 4. Buscar disciplinas do curso COM módulos (2ª query otimizada)
    course_query = select(models.Course).where(
        models.Course.id == db_class.course_id
    ).options(
        selectinload(models.Course.subjects).selectinload(models.Subject.modules)
    )
    course_result = await db.execute(course_query)
    course = course_result.scalars().first()
    
    if not course or not course.subjects:
        return response
    
    # 5. Indexar progresso por module_id para lookup O(1)
    progress_map = {p.module_id: p for p in db_class.progress_records}
    
    # 6. Construir árvore de disciplinas com progresso
    for subject in sorted(course.subjects, key=lambda s: s.name):
        modules_data = []
        subject_total = 0
        subject_completed = 0
        
        for module in sorted(subject.modules, key=lambda m: m.order):
            progress = progress_map.get(module.id)
            hours_done = progress.hours_completed if progress else 0
            completed = progress.is_completed if progress else False
            pct = round((hours_done / module.hours_total) * 100, 1) if module.hours_total > 0 else 0.0
            
            modules_data.append({
                "id": module.id,
                "name": module.name,
                "code": module.code,
                "hours_total": module.hours_total,
                "order": module.order,
                "hours_completed": hours_done,
                "is_completed": completed,
                "percentage": pct
            })
            
            subject_total += module.hours_total
            subject_completed += hours_done
        
        overall_pct = round((subject_completed / subject_total) * 100, 1) if subject_total > 0 else 0.0
        
        response["subjects"].append({
            "id": subject.id,
            "name": subject.name,
            "required_room_type": subject.required_room_type,
            "modules": modules_data,
            "total_hours": subject_total,
            "completed_hours": subject_completed,
            "overall_percentage": overall_pct
        })
    
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
    
    4 Pilares:
    🔐 Security: Valida turma pertence à org + módulo pertence ao curso da turma
    ⚡ Optimization: Upsert batch via ON CONFLICT (evita N queries individuais)
    ⚙️ Stability: Transação atómica — ou atualiza tudo ou nada
    📈 Scalability: Suporta atualização de múltiplos módulos de uma vez
    """
    from datetime import datetime, timezone
    
    # 1. Validar turma existe e pertence à org
    class_query = select(models.Class).where(
        models.Class.id == class_id,
        models.Class.organization_id == org_id
    )
    result = await db.execute(class_query)
    db_class = result.scalars().first()
    
    if not db_class:
        return "NOT_FOUND"
    
    # 2. Buscar módulos válidos do curso desta turma
    if not db_class.course_id:
        return "NO_COURSE"
    
    course_query = select(models.Course).where(
        models.Course.id == db_class.course_id
    ).options(
        selectinload(models.Course.subjects).selectinload(models.Subject.modules)
    )
    course_result = await db.execute(course_query)
    course = course_result.scalars().first()
    
    if not course:
        return "NO_COURSE"
    
    # 3. Construir mapa de módulos válidos: {module_id: hours_total}
    valid_modules = {}
    for subject in course.subjects:
        for module in subject.modules:
            valid_modules[module.id] = module.hours_total
    
    # 4. Validar que todos os module_ids pertencem ao curso
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