from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app import schemas, models
from app.api import deps
from app.services import schedule_service # Assumindo que a lógica está aqui

router = APIRouter()

@router.get("/", response_model=List[schemas.TimeslotRead])
async def read_timeslots(
    current_user: models.User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db)
):
    """
    Lista todos os blocos horários da organização.
    """
    return await schedule_service.get_timeslots_by_org(
        db, 
        org_id=current_user.organization_id
    )

@router.post("/", response_model=schemas.TimeslotRead)
async def create_timeslot(
    timeslot: schemas.TimeslotCreate,
    current_user: models.User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db)
):
    """
    Cria um novo bloco horário (ex: Segunda 08:30-09:30).
    """
    return await schedule_service.create_timeslot(
        db, 
        timeslot, 
        org_id=current_user.organization_id
    )

@router.delete("/{timeslot_id}")
async def delete_timeslot(
    timeslot_id: int,
    current_user: models.User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db)
):
    # Nota: Precisarias de implementar o delete no schedule_service
    # Para o teste agora não é crítico, mas fica a estrutura.
    pass