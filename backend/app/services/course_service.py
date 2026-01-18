from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select
from app import models, schemas

async def get_courses_by_org(db: AsyncSession, org_id: int):
    # CORREÇÃO CRÍTICA:
    # Usamos .options(selectinload(...)) para forçar o carregamento das disciplinas.
    # Sem isto, a @property subject_ids retorna lista vazia.
    query = select(models.Course)\
        .where(models.Course.organization_id == org_id)\
        .options(selectinload(models.Course.subjects))
    
    result = await db.execute(query)
    return result.scalars().all()

async def create_course(db: AsyncSession, item: schemas.CourseCreate, org_id: int):
    # Extrair subject_ids antes de despejar (pois não é campo direto do modelo)
    subject_ids = item.subject_ids if hasattr(item, 'subject_ids') else []
    
    # Criar o curso com os dados básicos
    course_data = item.model_dump(exclude={'subject_ids'})
    db_item = models.Course(**course_data, organization_id=org_id)
    
    # Associar disciplinas (se houver)
    if subject_ids:
        result = await db.execute(select(models.Subject).where(models.Subject.id.in_(subject_ids)))
        subjects = result.scalars().all()
        db_item.subjects = subjects
    
    db.add(db_item)
    await db.commit()
    return await get_course_with_subjects(db, db_item.id, org_id)

# Helper function para garantir consistência (podes adicionar no fim do ficheiro)
async def get_course_with_subjects(db: AsyncSession, course_id: int, org_id: int):
    result = await db.execute(
        select(models.Course)
        .where(models.Course.id == course_id, models.Course.organization_id == org_id)
        .options(selectinload(models.Course.subjects))
    )
    return result.scalars().first()

async def update_course(db: AsyncSession, course_id: int, item: schemas.CourseUpdate, org_id: int):
    # 1. Eager Loading (Correção MissingGreenlet): 
    # Carregamos 'subjects' explicitamente para poder alterá-los sem erro.
    query = select(models.Course).where(
        models.Course.id == course_id, 
        models.Course.organization_id == org_id
    ).options(selectinload(models.Course.subjects))
    
    result = await db.execute(query)
    db_item = result.scalars().first()
    
    if not db_item:
        return None

    # 2. Atualizar campos simples (ignora subject_ids aqui)
    update_data = item.model_dump(exclude_unset=True, exclude={"subject_ids"})
    for field, value in update_data.items():
        setattr(db_item, field, value)

    # 3. Atualizar Relação N:M
    if item.subject_ids is not None:
        # Validar e buscar os objetos das disciplinas
        # Isto garante que não associamos IDs fantasmas
        stmt_subjects = select(models.Subject).where(
            models.Subject.id.in_(item.subject_ids),
            models.Subject.organization_id == org_id
        )
        subjects_result = await db.execute(stmt_subjects)
        new_subjects = subjects_result.scalars().all()
        
        # SQLAlchemy gere a tabela de associação magicamente aqui
        db_item.subjects = list(new_subjects)

    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

async def delete_course(db: AsyncSession, course_id: int, org_id: int):
    # 1. Verificar existência
    result = await db.execute(select(models.Course).where(models.Course.id == course_id, models.Course.organization_id == org_id))
    course = result.scalars().first()
    if not course:
        return "NOT_FOUND"

    # 2. Verificar dependências (Turmas)
    # Não apagamos cursos que têm turmas ativas
    result_classes = await db.execute(select(models.Class).where(models.Class.course_id == course_id))
    if result_classes.first():
        return "DEPENDENCY_ERROR"

    await db.delete(course)
    await db.commit()
    return "SUCCESS"