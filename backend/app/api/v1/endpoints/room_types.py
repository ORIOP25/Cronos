from fastapi import APIRouter

from app import schemas
from app.api import deps
from app.services import room_type_service

router = APIRouter()


@router.get("/", response_model=list[schemas.RoomTypeRead])
async def read_room_types(
    current_user: deps.AdminActor,
    db: deps.DbSession,
):
    return await room_type_service.list_room_types(
        db,
        organization_id=current_user.organization_id,
    )


@router.post("/", response_model=schemas.RoomTypeRead, status_code=201)
async def create_room_type(
    room_type: schemas.RoomTypeCreate,
    db: deps.DbSession,
    current_user: deps.AdminActor,
):
    return await room_type_service.create_room_type(
        db,
        room_type,
        organization_id=current_user.organization_id,
    )


@router.patch(
    "/{room_type_id}",
    response_model=schemas.RoomTypeRead,
    responses={404: {"description": "Tipo de sala não encontrado"}},
)
async def update_room_type(
    room_type_id: int,
    room_type_in: schemas.RoomTypeUpdate,
    db: deps.DbSession,
    current_user: deps.AdminActor,
):
    return await room_type_service.rename_room_type(
        db,
        room_type_id,
        room_type_in,
        current_user.organization_id,
    )


@router.delete(
    "/{room_type_id}",
    responses={
        404: {"description": "Tipo de sala não encontrado"},
        409: {"description": "Tipo fixo ou em uso"},
    },
)
async def delete_room_type(
    room_type_id: int,
    db: deps.DbSession,
    current_user: deps.AdminActor,
):
    remove_effect = await room_type_service.remove_room_type(
        db,
        room_type_id,
        current_user.organization_id,
    )
    return {"message": "Tipo de sala removido com sucesso", "remove_effect": remove_effect}
