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

@router.put("/{room_id}", response_model=schemas.RoomRead)
async def update_room(
    room_id: int,
    room_in: schemas.RoomUpdate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_admin)
):
    room = await room_service.update_room(db, room_id, room_in, current_user.organization_id)
    if not room:
        raise HTTPException(status_code=404, detail="Sala não encontrada")
    return room

@router.delete("/{room_id}")
async def delete_room(
    room_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_admin)
):
    status = await room_service.delete_room(db, room_id, current_user.organization_id)
    
    if status == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Sala não encontrada")
    
    if status == "DEPENDENCY_ERROR":
        raise HTTPException(
            status_code=400, 
            detail="Não é possível apagar esta sala pois existem aulas agendadas nela."
        )
    
    return {"message": "Sala removida com sucesso"}