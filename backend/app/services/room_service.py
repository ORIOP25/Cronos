from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from app import models, schemas
from app.core.exceptions import AppError
from app.services import resource_removal
from app.services.room_type_service import resolve_active_room_type
from app.services.scheduler_state_service import record_scheduler_change


def _room_snapshot(room: models.Room) -> dict:
    return {"room_type_id": room.room_type_id, "capacity": room.capacity}


async def _room_with_type(
    db: AsyncSession, room_id: int, organization_id: int
) -> models.Room | None:
    """A sala da escola com o tipo já carregado, para a resposta."""
    return await db.scalar(
        select(models.Room)
        .options(joinedload(models.Room.room_type))
        .where(
            models.Room.id == room_id,
            models.Room.organization_id == organization_id,
        )
    )


# --- ASYNC (API) ---
async def get_rooms_by_org(db: AsyncSession, organization_id: int):
    result = await db.execute(
        select(models.Room)
        .options(joinedload(models.Room.room_type))
        .where(
            models.Room.organization_id == organization_id,
            models.Room.is_archived.is_(False),
        )
    )
    return result.scalars().all()


async def create_room(
    db: AsyncSession,
    item: schemas.RoomCreate,
    organization_id: int,
    changed_by_membership_id: int | None = None,
):
    room_type = await resolve_active_room_type(db, organization_id, item.room_type_id)
    db_item = models.Room(
        name=item.name,
        room_type_id=room_type.id,
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
        changed_by_membership_id=changed_by_membership_id,
    )
    await db.flush()
    await db.refresh(db_item)
    return await _room_with_type(db, db_item.id, organization_id)


async def update_room(
    db: AsyncSession,
    room_id: int,
    room_in: schemas.RoomUpdate,
    organization_id: int,
    changed_by_membership_id: int | None = None,
):
    room_type = None
    if "room_type_id" in room_in.model_fields_set:
        room_type = await resolve_active_room_type(db, organization_id, room_in.room_type_id)

    query = select(models.Room).where(
        models.Room.id == room_id, models.Room.organization_id == organization_id
    )
    result = await db.execute(query)
    room = result.scalars().first()

    if not room:
        raise AppError(
            kind="not_found",
            code="resource_not_found",
            detail=f"Room {room_id} was not found in organization {organization_id}.",
        )

    before = _room_snapshot(room)
    update_data = room_in.model_dump(exclude_unset=True)
    if room_type is not None:
        update_data["room_type_id"] = room_type.id
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
        changed_by_membership_id=changed_by_membership_id,
    )
    await db.flush()
    await db.refresh(room)
    return await _room_with_type(db, room.id, organization_id)


async def delete_room(
    db: AsyncSession,
    room_id: int,
    organization_id: int,
    changed_by_membership_id: int | None = None,
) -> str:
    """Remove uma sala da gestão atual e devolve o efeito aplicado.

    Uma sala publicada ou com operação em curso fica bloqueada. Uma sala com
    histórico é arquivada; sem qualquer referência é eliminada fisicamente.
    As regras de configuração que apontam para a sala são retiradas na mesma
    transação.
    """
    query = select(models.Room).where(
        models.Room.id == room_id, models.Room.organization_id == organization_id
    )
    result = await db.execute(query)
    room = result.scalars().first()

    if not room:
        raise AppError(
            kind="not_found",
            code="resource_not_found",
            detail=f"Room {room_id} was not found in organization {organization_id}.",
        )

    if await resource_removal.room_in_use(db, organization_id, room_id):
        raise AppError(
            kind="conflict",
            code="resource_in_use",
            detail=f"Room {room_id} is used by the active schedule.",
        )

    before = _room_snapshot(room)
    effect = (
        "archive"
        if await resource_removal.room_has_history(db, organization_id, room_id)
        else "hard_delete"
    )
    await resource_removal.remove_room_configuration(db, organization_id, room_id)

    if effect == "hard_delete":
        operation = models.SchedulerStateChangeOperation.DELETE
        after = None
        await db.delete(room)
    else:
        operation = models.SchedulerStateChangeOperation.UPDATE
        room.is_archived = True
        after = {**before, "is_archived": True}

    await record_scheduler_change(
        db,
        organization_id,
        entity_type="ROOM",
        entity_id=room.id,
        operation=operation,
        before=before,
        after=after,
        changed_by_membership_id=changed_by_membership_id,
        active_resource=False,
    )
    await db.flush()
    return effect
