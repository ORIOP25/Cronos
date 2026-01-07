from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from typing import List
from app import schemas, models
from app.api import deps
from app.services import timeslot_service

router = APIRouter()

@router.get("/", response_model=List[schemas.TimeslotRead])
async def read_timeslots(
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user)
):
    return await timeslot_service.get_timeslots_by_org(db, current_user.organization_id)

@router.post("/", response_model=schemas.TimeslotRead)
async def create_timeslot(
    item: schemas.TimeslotCreate, 
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_admin)
):
    return await timeslot_service.create_timeslot(db, item, current_user.organization_id)

@router.put("/{timeslot_id}", response_model=schemas.TimeslotRead)
async def update_timeslot(
    timeslot_id: int,
    item: schemas.TimeslotUpdate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_admin)
):
    try:
        updated = await timeslot_service.update_timeslot(db, timeslot_id, item, current_user.organization_id)
        if not updated:
            raise HTTPException(status_code=404, detail="Bloco horário não encontrado")
        return updated
    except IntegrityError:
        # Captura a tentativa de editar para um horário que já existe
        raise HTTPException(
            status_code=409, 
            detail="Já existe um bloco horário definido para este dia e hora de início."
        )

@router.delete("/{timeslot_id}")
async def delete_timeslot(
    timeslot_id: int, 
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_admin)
):
    status = await timeslot_service.delete_timeslot(db, timeslot_id, current_user.organization_id)
    
    if status == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Bloco horário não encontrado")
    
    if status == "DEPENDENCY_ERROR_AVAILABILITY":
        raise HTTPException(status_code=400, detail="Não pode apagar: Professores já marcaram disponibilidade neste bloco.")
        
    if status == "DEPENDENCY_ERROR_SCHEDULE":
        raise HTTPException(status_code=400, detail="Não pode apagar: Existem horários gerados que usam este bloco.")
    
    return {"message": "Bloco removido com sucesso"}