from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.future import select
from app import models, schemas

# --- ASYNC (API) ---
async def get_subjects_by_org(db: AsyncSession, org_id: int):
    result = await db.execute(select(models.Subject).where(models.Subject.organization_id == org_id))
    return result.scalars().all()

async def create_subject(db: AsyncSession, item: schemas.SubjectCreate, org_id: int):
    db_item = models.Subject(name=item.name, organization_id=org_id)
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

async def delete_subject(db: AsyncSession, subject_id: int, org_id: int):
    result = await db.execute(select(models.Subject).where(models.Subject.id == subject_id, models.Subject.organization_id == org_id))
    item = result.scalars().first()
    if item:
        await db.delete(item)
        await db.commit()
        return True
    return False

# --- SYNC (SOLVER) ---
def get_subjects_by_org_sync(db: Session, org_id: int):
    return db.query(models.Subject).filter(models.Subject.organization_id == org_id).all()