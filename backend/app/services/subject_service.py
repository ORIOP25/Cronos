from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy import select
from app import models, schemas
# Importamos Lesson para garantir que não apagamos disciplinas em uso
from app.models import Lesson 

# --- ASYNC (API) ---
async def get_subjects_by_org(db: AsyncSession, org_id: int):
    stmt = select(models.Subject).where(models.Subject.organization_id == org_id).order_by(models.Subject.name)
    result = await db.execute(stmt)
    return result.scalars().all()

async def create_subject(db: AsyncSession, item: schemas.SubjectCreate, org_id: int):
    # Usamos **item.model_dump() para passar automaticamente 'name' e 'required_room_type'
    db_item = models.Subject(**item.model_dump(), organization_id=org_id)
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

async def update_subject(
    db: AsyncSession, 
    subject_id: int, 
    subject_in: schemas.SubjectUpdate,
    org_id: int
):
    """
    Atualiza nome ou tipo de sala da disciplina.
    """
    query = select(models.Subject).where(
        models.Subject.id == subject_id,
        models.Subject.organization_id == org_id
    )
    result = await db.execute(query)
    subject = result.scalars().first()
    
    if not subject:
        return None

    # Atualização parcial (apenas os campos enviados)
    update_data = subject_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(subject, field, value)

    db.add(subject)
    await db.commit()
    await db.refresh(subject)
    return subject

async def delete_subject(db: AsyncSession, subject_id: int, org_id: int):
    """
    Remove uma disciplina. Protege se existirem aulas associadas.
    """
    # 1. Buscar disciplina
    result = await db.execute(select(models.Subject).where(models.Subject.id == subject_id, models.Subject.organization_id == org_id))
    item = result.scalars().first()
    
    if not item:
        return "NOT_FOUND"

    # 2. VERIFICAÇÃO DE INTEGRIDADE
    # Verifica se existem aulas (Lessons) desta disciplina
    query_dep = select(models.Lesson).where(models.Lesson.subject_id == subject_id)
    result_dep = await db.execute(query_dep)
    
    if result_dep.first():
        return "DEPENDENCY_ERROR"

    # 3. Apagar
    await db.delete(item)
    await db.commit()
    return "SUCCESS"

# --- SYNC (SOLVER) ---
def get_subjects_by_org_sync(db: Session, org_id: int):
    return db.query(models.Subject).filter(models.Subject.organization_id == org_id).all()