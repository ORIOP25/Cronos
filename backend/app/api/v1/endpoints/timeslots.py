from fastapi import APIRouter

from app import schemas
from app.api import deps
from app.services import timeslot_service

router = APIRouter()


# --- 1. Ler Timeslots (Usado na pÃ¡gina "HorÃ¡rios") ---
@router.get("/", response_model=list[schemas.TimeslotRead])
async def read_timeslots(
    db: deps.DbSession,
    current_user: deps.ActiveActor,
):
    return await timeslot_service.get_timeslots_by_org(db, current_user.organization_id)
