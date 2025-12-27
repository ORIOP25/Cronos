from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app import schemas
from app.api import deps
from app.services import room_service
from app import models

router = APIRouter()

#@router.get("/", response_model=List[schemas.RoomRead])
#async def read_rooms(org_id: int, db: AsyncSession = Depends(deps.get_db)):
    #return await room_service.get_rooms_by_org(db, org_id)
@router.get("/", response_model=List[schemas.RoomRead])
async def read_rooms(
    current_user: models.User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db)
):
    return await room_service.get_rooms_by_org(
        db,
        org_id=current_user.organization_id,
    )

@router.post("/", response_model=schemas.RoomRead)
async def create_room(
    room: schemas.RoomCreate,
    db: AsyncSession = Depends(deps.get_db),
    # A Correção: Pedimos o Utilizador Logado, não o org_id direto
    current_user: models.User = Depends(deps.get_current_user) 
):
    """
    Cria uma nova sala.
    O org_id é preenchido automaticamente com base no utilizador logado.
    """
    return await room_service.create_room(
        db, 
        room, 
        org_id=current_user.organization_id # <--- Passamos o ID aqui internamente
    )

@router.delete("/{room_id}")
async def delete_room(room_id: int, org_id: int, db: AsyncSession = Depends(deps.get_db)):
    success = await room_service.delete_room(db, room_id, org_id)
    if not success:
        raise HTTPException(status_code=404, detail="Sala não encontrada")
    return {"ok": True}