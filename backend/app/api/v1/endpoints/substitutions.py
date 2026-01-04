from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Any
from datetime import date

from app import schemas, models
from app.api import deps
from app.services import substitution_service

router = APIRouter()

@router.get("/suggestions", response_model=List[schemas.ReplacementSuggestion])
async def get_suggestions(
    timeslot_id: int,
    date_str: str, # Recebemos como string "2026-03-12" e convertemos
    original_teacher_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """
    Retorna professores sugeridos para uma data específica.
    """
    try:
        date_obj = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Data inválida. Use YYYY-MM-DD")

    suggestions = await substitution_service.find_available_teachers(
        db=db,
        timeslot_id=timeslot_id,
        date_of_substitution=date_obj,
        exclude_teacher_id=original_teacher_id,
        org_id=current_user.organization_id # Assumindo que User tem org_id
    )
    return suggestions

@router.post("/", response_model=schemas.SubstitutionResponse)
async def create_substitution(
    sub_in: schemas.SubstitutionCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_admin), # Apenas Admin/Diretor
):
    """
    Grava a substituição e dispara notificações (futuro).
    """
    new_sub = await substitution_service.create_substitution(db, sub_in)
    
    # TODO: Chamar Celery Task aqui para enviar email ao original e ao substituto
    
    return new_sub

@router.get("/", response_model=List[schemas.SubstitutionResponse])
async def read_substitutions(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """
    Retorna a lista de substituições ativas (para pintar no calendário).
    """
    # Precisamos de criar esta função no service (ver passo seguinte)
    substitutions = await substitution_service.get_active_substitutions(db, skip=skip, limit=limit)
    return substitutions