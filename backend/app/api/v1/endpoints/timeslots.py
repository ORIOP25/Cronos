from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app import schemas
from app.api import deps
from app.core.exceptions import AppError
from app.services import grid_version_service, timeslot_service

router = APIRouter()


# --- 1. Ler Timeslots (Usado na pÃ¡gina "HorÃ¡rios") ---
@router.get("/", response_model=list[schemas.TimeslotRead])
async def read_timeslots(
    db: deps.DbSession,
    current_user: deps.ActiveActor,
    on_date: Annotated[
        date | None,
        Query(description="Data escolar cuja versão da grelha deve ser usada"),
    ] = None,
):
    return await timeslot_service.get_timeslots_by_org(
        db, current_user.organization_id, on_date=on_date
    )


# --- 2. Blocos por data (semanas que atravessam a vigência de duas grelhas) ---
@router.get("/range", response_model=schemas.WeekGridVersionsResponse)
async def read_timeslots_range(
    db: deps.DbSession,
    current_user: deps.ActiveActor,
    from_date: Annotated[date, Query(description="Primeira data do intervalo")],
    to_date: Annotated[date, Query(description="Última data do intervalo")],
):
    try:
        payload = await grid_version_service.week_grid_versions(
            db, current_user.organization_id, from_date, to_date
        )
    except ValueError as exc:
        raise AppError(kind="validation", code="grid_range_invalid", detail=str(exc)) from exc
    return schemas.WeekGridVersionsResponse.model_validate(payload)
