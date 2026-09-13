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
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.ActiveActor,
):
    return await timeslot_service.get_timeslots_by_org(db, current_user.organization_id)
