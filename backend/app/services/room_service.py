from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.future import select
from app import models, schemas
from app.models import ScheduleOutput
from app.services.scheduler_state_service import record_scheduler_change


def _room_snapshot(room: models.Room) -> dict:
    return {"type": room.type, "capacity": room.capacity}

# --- ASYNC (API) ---
async def get_rooms_by_org(db: AsyncSession, organization_id: int):
    result = await db.execute(select(models.Room).where(models.Room.organization_id == organization_id))
    return result.scalars().all()

async def create_room(
    db: AsyncSession,
    item: schemas.RoomCreate,
    organization_id: int,
    changed_by_user_id: int | None = None,
):
    db_item = models.Room(
        name=item.name,
        type=item.type,
        capacity=item.capacity,
        organization_id=organization_id,
    )
    db.add(db_item)
    await db.flush()
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="ROOM",
        entity_id=db_item.id,
        operation=models.SchedulerStateChangeOperation.CREATE,
        before=None,
        after=_room_snapshot(db_item),
        changed_by_user_id=changed_by_user_id,
    )
    await db.commit()
    await db.refresh(db_item)
    return db_item

async def update_room(
    db: AsyncSession, 
    room_id: int, 
    room_in: schemas.RoomUpdate,
    organization_id: int,
    changed_by_user_id: int | None = None,
):
    query = select(models.Room).where(
        models.Room.id == room_id,
        models.Room.organization_id == organization_id
    )
    result = await db.execute(query)
    room = result.scalars().first()
    
    if not room:
        return None

    before = _room_snapshot(room)
    update_data = room_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(room, field, value)

    db.add(room)
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="ROOM",
        entity_id=room.id,
        operation=models.SchedulerStateChangeOperation.UPDATE,
        before=before,
        after=_room_snapshot(room),
        changed_by_user_id=changed_by_user_id,
    )
    await db.commit()
    await db.refresh(room)
    return room

async def delete_room(
    db: AsyncSession, 
    room_id: int,
    organization_id: int,
    changed_by_user_id: int | None = None,
) -> str:
    """
    Remove uma sala. Protege se houver aulas agendadas nela.
    """
    # 1. Buscar sala
    query = select(models.Room).where(
        models.Room.id == room_id,
        models.Room.organization_id == organization_id
    )
    result = await db.execute(query)
    room = result.scalars().first()
    
    if not room:
        return "NOT_FOUND"

    # 2. VERIFICAÇÃO DE INTEGRIDADE
    # Verificamos se a sala está atribuída em algum horário gerado (ScheduleOutput).
    # Se estiver, não deixamos apagar para não "esburacar" o horário visível.
    query_dep = select(models.ScheduleOutput).where(
        models.ScheduleOutput.room_id == room_id,
        models.ScheduleOutput.organization_id == organization_id,
    )
    result_dep = await db.execute(query_dep)
    
    if result_dep.first():
        return "DEPENDENCY_ERROR"

    # 3. Apagar
    before = _room_snapshot(room)
    await db.delete(room)
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="ROOM",
        entity_id=room.id,
        operation=models.SchedulerStateChangeOperation.DELETE,
        before=before,
        after=None,
        changed_by_user_id=changed_by_user_id,
    )
    await db.commit()
    return "SUCCESS"

# --- SYNC (SOLVER) ---
def get_rooms_by_org_sync(db: Session, organization_id: int):
    return db.query(models.Room).filter(models.Room.organization_id == organization_id).all()
