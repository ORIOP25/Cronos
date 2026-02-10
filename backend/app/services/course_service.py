from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy import select, insert, delete
from fastapi import HTTPException
from app import models, schemas

# --- LEITURA ---
async def get_courses_by_org(db: AsyncSession, org_id: int, skip: int = 0, limit: int = 100):
    """
    Lista cursos da organização com paginação offset/limit.
    
    4º Pilar:
    - Optimization: selectinload carrega subjects+classes em 3 queries (não N+1)
    - Scalability: offset/limit permite crescimento sem impacto
    
    Nota: Carregamos subjects e classes porque a tabela precisa da contagem
    e o modal de edição precisa dos dados completos para popular o form.
    Para ~50 cursos com ~10 disciplinas cada, o overhead é negligível.
    """
    # Sanitize limit (max 1000 para evitar sobre-carga)
    limit = min(max(limit, 1), 1000)
    skip = max(skip, 0)
    
    query = select(models.Course)\
        .where(models.Course.organization_id == org_id)\
        .options(
            selectinload(models.Course.subjects),
            selectinload(models.Course.classes)
        )\
        .order_by(models.Course.name)\
        .offset(skip)\
        .limit(limit)
    result = await db.execute(query)
    return result.scalars().all()

async def get_course_details(db: AsyncSession, course_id: int, org_id: int):
    """Retorna a árvore completa do curso para a Dashboard"""
    query = select(models.Course).where(
        models.Course.id == course_id, 
        models.Course.organization_id == org_id
    ).options(
        selectinload(models.Course.subjects),
        selectinload(models.Course.classes) # Carregar turmas
    )
    result = await db.execute(query)
    return result.scalars().first()

# --- CRIAÇÃO (O MOTOR NOVO) ---
async def create_course(db: AsyncSession, item: schemas.CourseCreate, org_id: int):
    """
    Cria Curso + Associa Disciplinas + Define Professores + Gera Turmas
    Tudo numa transação atómica.
    """
    # 1. Validar Abreviatura Única (Regra de Negócio)
    q_check = select(models.Course).where(
        models.Course.abbreviation == item.abbreviation.upper(),
        models.Course.organization_id == org_id
    )
    if (await db.execute(q_check)).scalars().first():
        raise HTTPException(400, f"A sigla '{item.abbreviation}' já existe nesta escola.")

    # 2. Preparar as Disciplinas (ANTES DE CRIAR O CURSO)
    # Buscamos as disciplinas primeiro para injetar logo na criação
    subjects_to_link = []
    if item.subject_ids:
        q_subjects = select(models.Subject).where(
            models.Subject.id.in_(item.subject_ids),
            models.Subject.organization_id == org_id 
        )
        subjects_to_link = (await db.execute(q_subjects)).scalars().all()
        
        if len(subjects_to_link) != len(item.subject_ids):
            raise HTTPException(400, "Tentativa de associar disciplinas inválidas ou de outra escola.")

    # 3. Criar o Objeto Curso (SEM disciplinas, evita lazy loading em async)
    course_data = item.model_dump(
        exclude={'subject_ids', 'classes_config', 'teacher_assignments', 'abbreviation'}
    )
    
    db_course = models.Course(
        **course_data, 
        organization_id=org_id,
        abbreviation=item.abbreviation.upper()
        # ❌ NÃO atribuir subjects aqui (trigga lazy loading em async)
    )
    
    db.add(db_course)
    await db.flush()  # Gerar ID do curso
    
    # 3.5. Associar disciplinas via INSERT (evita lazy load em async)
    # ⚠️ NÃO usar db_course.subjects.extend() - causa MissingGreenlet
    if subjects_to_link:
        # Inserir directamente na tabela de ligação
        stmt = insert(models.course_subject_link).values(
            [
                {"course_id": db_course.id, "subject_id": subject.id}
                for subject in subjects_to_link
            ]
        )
        await db.execute(stmt)

    # 4. Criar Turmas Automaticamente
    # Agora que já temos o ID do curso (pós-flush), podemos criar as turmas
    for cls_conf in item.classes_config:
        start_short = cls_conf.start_year % 100
        end_short = cls_conf.end_year % 100
        class_name = f"{db_course.abbreviation} {start_short}/{end_short}"
        
        new_class = models.Class(
            name=class_name,
            size=cls_conf.size,
            course_id=db_course.id,
            organization_id=org_id,
            grade_level=cls_conf.grade_level,
            start_year=cls_conf.start_year,
            end_year=cls_conf.end_year
        )
        db.add(new_class)

    # 5. Commit Final
    await db.commit()
    
    # 6. Retornar com eager load (selectinload) para evitar lazy loading em async
    # ⚠️ NÃO usar .refresh() com relacionamentos - causa MissingGreenlet
    return await get_course_details(db, db_course.id, org_id)

# --- UPDATE E DELETE ---
async def update_course(db: AsyncSession, course_id: int, item: schemas.CourseUpdate, org_id: int):
    """
    Atualiza um curso (PATCH - apenas campos enviados).
    """
    query = select(models.Course).where(
        models.Course.id == course_id, 
        models.Course.organization_id == org_id
    )
    
    result = await db.execute(query)
    db_item = result.scalars().first()
    
    if not db_item:
        return None # Alterado para retornar None (o endpoint trata o 404)

    # SECURITY: Se estão a mudar abbreviation, validar uniqueness
    if item.abbreviation is not None and item.abbreviation.upper() != db_item.abbreviation:
        q_check = select(models.Course).where(
            models.Course.abbreviation == item.abbreviation.upper(),
            models.Course.organization_id == org_id,
            models.Course.id != course_id
        )
        if (await db.execute(q_check)).scalars().first():
            return "ABBREVIATION_EXISTS"

    # 1. Aplicar updates Escalares (Campos simples)
    update_data = item.model_dump(exclude_unset=True, exclude={"subject_ids"})
    for field, value in update_data.items():
        if field == "abbreviation" and value:
            setattr(db_item, field, value.upper())
        else:
            setattr(db_item, field, value)
            
    # Gravar as alterações escalares primeiro
    db.add(db_item)
    await db.flush()

    # 2. Atualizar Relações (SQL Directo para evitar MissingGreenlet)
    if item.subject_ids is not None:
        # CORREÇÃO CRÍTICA: Expirar a relação no ORM para evitar que ele 
        # re-insira os dados antigos durante o commit.
        db.expire(db_item, ['subjects'])

        # Validar IDs
        stmt_subjects = select(models.Subject).where(
            models.Subject.id.in_(item.subject_ids),
            models.Subject.organization_id == org_id
        )
        new_subjects = (await db.execute(stmt_subjects)).scalars().all()
        
        # Remover antigas
        await db.execute(
            delete(models.course_subject_link).where(
                models.course_subject_link.c.course_id == course_id
            )
        )
        
        # Inserir novas
        if new_subjects:
            stmt = insert(models.course_subject_link).values(
                [
                    {"course_id": course_id, "subject_id": subject.id}
                    for subject in new_subjects
                ]
            )
            await db.execute(stmt)

    await db.commit()
    
    # Retornar com eager load fresco
    return await get_course_details(db, course_id, org_id)

async def delete_course(db: AsyncSession, course_id: int, org_id: int):
    # 1. Verificar existência
    result = await db.execute(select(models.Course).where(models.Course.id == course_id, models.Course.organization_id == org_id))
    course = result.scalars().first()
    if not course:
        return "NOT_FOUND"

    # 2. Verificar dependências
    result_classes = await db.execute(select(models.Class).where(models.Class.course_id == course_id))
    if result_classes.first():
        return "DEPENDENCY_ERROR"

    await db.delete(course)
    await db.commit()
    return "SUCCESS"