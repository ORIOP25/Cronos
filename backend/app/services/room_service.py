from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.future import select
from app import models, schemas
from app.models import ScheduleOutput

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

async def update_room(
    db: AsyncSession, 
    room_id: int, 
    room_in: schemas.RoomUpdate,
    org_id: int
):
    query = select(models.Room).where(
        models.Room.id == room_id,
        models.Room.organization_id == org_id
    )
    result = await db.execute(query)
    room = result.scalars().first()
    
    if not room:
        return None

    update_data = room_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(room, field, value)

    db.add(room)
    await db.commit()
    await db.refresh(room)
    return room

async def delete_room(
    db: AsyncSession, 
    room_id: int,
    org_id: int
) -> str:
    """
    Remove uma sala. Protege se houver aulas agendadas nela.
    """
    # 1. Buscar sala
    query = select(models.Room).where(
        models.Room.id == room_id,
        models.Room.organization_id == org_id
    )
    result = await db.execute(query)
    room = result.scalars().first()
    
    if not room:
        return "NOT_FOUND"

    # 2. VERIFICAÇÃO DE INTEGRIDADE
    # Verificamos se a sala está atribuída em algum horário gerado (ScheduleOutput).
    # Se estiver, não deixamos apagar para não "esburacar" o horário visível.
    query_dep = select(models.ScheduleOutput).where(models.ScheduleOutput.room_id == room_id)
    result_dep = await db.execute(query_dep)
    
    if result_dep.first():
        return "DEPENDENCY_ERROR"

    # 3. Apagar
    await db.delete(room)
    await db.commit()
    return "SUCCESS"

# --- SYNC (SOLVER) ---
def get_rooms_by_org_sync(db: Session, org_id: int):
    return db.query(models.Room).filter(models.Room.organization_id == org_id).all()