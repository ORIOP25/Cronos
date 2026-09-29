from fastapi import APIRouter

from app import schemas
from app.api import deps
from app.services import room_service

router = APIRouter()


@router.get("/", response_model=list[schemas.RoomRead])
async def read_rooms(
    current_user: deps.ActiveActor,
    db: deps.DbSession,
):
    return await room_service.get_rooms_by_org(
        db,
        organization_id=current_user.organization_id,
    )


@router.post("/", response_model=schemas.RoomRead)
async def create_room(
    room: schemas.RoomCreate,
    db: deps.DbSession,
    # A CorreÃ§Ã£o: Pedimos o Utilizador Logado, nÃ£o o org_id direto
    current_user: deps.AdminActor,
):
    """
    Cria uma nova sala.
    O org_id Ã© preenchido automaticamente com base no utilizador logado.
    """
    return await room_service.create_room(
        db,
        room,
        organization_id=current_user.organization_id,  # <--- Passamos o ID aqui internamente
        changed_by_membership_id=current_user.membership_id,
    )


@router.patch(
    "/{room_id}",
    response_model=schemas.RoomRead,
    responses={404: {"description": "Sala nÃ£o encontrada"}},
)
async def update_room(
    room_id: int,
    room_in: schemas.RoomUpdate,
    db: deps.DbSession,
    current_user: deps.AdminActor,
):
    return await room_service.update_room(
        db,
        room_id,
        room_in,
        current_user.organization_id,
        changed_by_membership_id=current_user.membership_id,
    )


@router.delete(
    "/{room_id}",
    responses={
        404: {"description": "Sala nÃ£o encontrada"},
        400: {"description": "DependÃªncias existentes"},
    },
)
async def delete_room(
    room_id: int,
    db: deps.DbSession,
    current_user: deps.AdminActor,
):
    remove_effect = await room_service.delete_room(
        db,
        room_id,
        current_user.organization_id,
        changed_by_membership_id=current_user.membership_id,
    )

    return {"message": "Sala removida com sucesso", "remove_effect": remove_effect}
