from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.future import select
from app import models, schemas

# --- ASYNC (API) ---
async def get_classes_by_org(db: AsyncSession, org_id: int):
    result = await db.execute(select(models.Class).where(models.Class.organization_id == org_id))
    return result.scalars().all()

async def create_class(db: AsyncSession, item: schemas.ClassCreate, org_id: int):
    db_item = models.Class(name=item.name, organization_id=org_id)
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

async def delete_class(db: AsyncSession, class_id: int, org_id: int):
    result = await db.execute(select(models.Class).where(models.Class.id == class_id, models.Class.organization_id == org_id))
    item = result.scalars().first()
    if item:
        await db.delete(item)
        await db.commit()
        return True
    return False

# --- SYNC (SOLVER) ---
def get_classes_by_org_sync(db: Session, org_id: int):
    return db.query(models.Class).filter(models.Class.organization_id == org_id).all()