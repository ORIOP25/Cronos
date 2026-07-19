from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.api import deps
from app.services import timeslot_service

router = APIRouter()


# --- 1. Ler Timeslots (Usado na pÃ¡gina "HorÃ¡rios") ---
@router.get("/", response_model=list[schemas.TimeslotRead])
async def read_timeslots(
    db: Annotated[AsyncSession, Depends(deps.get_db)], current_user: deps.ActiveActor
):
    return await timeslot_service.get_timeslots_by_org(db, current_user.organization_id)


# --- 2. Gerar em Massa (Usado na pÃ¡gina "ConfiguraÃ§Ã£o") ---
@router.post("/generate", response_model=dict)
async def generate_timeslots(
    settings: schemas.TimeslotBulkCreate,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: deps.AdminActor,
):
    # Chama o serviÃ§o que limpa os antigos e cria os novos
    count = await timeslot_service.create_bulk_timeslots(
        db,
        settings,
        current_user.organization_id,
        changed_by_membership_id=current_user.membership_id,
    )
    return {"message": f"{count} blocos horÃ¡rios gerados com sucesso."}
