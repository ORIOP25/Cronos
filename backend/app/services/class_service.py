from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.future import select
from app import models, schemas
from app.models import Lesson

# --- ASYNC (API) ---
async def get_classes_by_org(db: AsyncSession, org_id: int):
    # Ordenar por nome
    result = await db.execute(select(models.Class).where(models.Class.organization_id == org_id).order_by(models.Class.name))
    return result.scalars().all()

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