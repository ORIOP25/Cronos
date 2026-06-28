from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated, List, Annotated
from app import schemas, models
from app.api import deps
from app.services import timeslot_service

router = APIRouter()

# --- 1. Ler Timeslots (Usado na página "Horários") ---
@router.get("/", response_model=List[schemas.TimeslotRead])
async def read_timeslots(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)]
):
    return await timeslot_service.get_timeslots_by_org(db, current_user.organization_id)

# --- 2. Gerar em Massa (Usado na página "Configuração") ---
@router.post("/generate", response_model=dict)
async def generate_timeslots(
    settings: schemas.TimeslotBulkCreate,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)]
):
    # Chama o serviço que limpa os antigos e cria os novos
    count = await timeslot_service.create_bulk_timeslots(
        db, settings, current_user.organization_id,
        changed_by_user_id=current_user.id,
    )
    return {"message": f"{count} blocos horários gerados com sucesso."}
