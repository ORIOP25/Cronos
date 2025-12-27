from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.future import select
from app import models, schemas

# --- ASYNC (API) ---
async def get_rooms_by_org(db: AsyncSession, org_id: int):
    result = await db.execute(select(models.Room).where(models.Room.organization_id == org_id))
    return result.scalars().all()

async def create_room(db: AsyncSession, item: schemas.RoomCreate, org_id: int):
    db_item = models.Room(name=item.name, type=item.type, organization_id=org_id)
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

async def delete_room(db: AsyncSession, room_id: int, org_id: int):
    result = await db.execute(select(models.Room).where(models.Room.id == room_id, models.Room.organization_id == org_id))
    item = result.scalars().first()
    if item:
        await db.delete(item)
        await db.commit()
        return True
    return False

# --- SYNC (SOLVER) ---
def get_rooms_by_org_sync(db: Session, org_id: int):
    return db.query(models.Room).filter(models.Room.organization_id == org_id).all()