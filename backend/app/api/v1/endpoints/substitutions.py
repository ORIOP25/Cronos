from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Annotated
from datetime import date

from app import schemas, models
from app.api import deps
from app.services import substitution_service

router = APIRouter()

@router.get("/suggestions", response_model=List[schemas.ReplacementSuggestion], responses={400: {"description": "Data inválida"}, 404: {"description": "Timeslot ou professor não encontrado"}})
async def get_suggestions(
    timeslot_id: int,
    date_str: str, # Recebemos como string "2026-03-12" e convertemos
    original_teacher_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)],
):
    """
    Retorna professores sugeridos para uma data específica.
    """
    try:
        date_obj = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Data inválida. Use YYYY-MM-DD")

    # Validar timeslot pertence à organização
    timeslot_query = select(models.Timeslot).where(
        models.Timeslot.id == timeslot_id,
        models.Timeslot.organization_id == current_user.organization_id
    )
    if not (await db.execute(timeslot_query)).scalars().first():
        raise HTTPException(status_code=404, detail="Timeslot não encontrado")

    # Validar professor original pertence à organização
    teacher_query = select(models.Teacher).where(
        models.Teacher.id == original_teacher_id,
        models.Teacher.organization_id == current_user.organization_id
    )
    if not (await db.execute(teacher_query)).scalars().first():
        raise HTTPException(status_code=404, detail="Professor não encontrado")

    suggestions = await substitution_service.find_available_teachers(
        db=db,
        timeslot_id=timeslot_id,
        date_of_substitution=date_obj,
        exclude_teacher_id=original_teacher_id,
        org_id=current_user.organization_id # Assumindo que User tem org_id
    )
    return suggestions

@router.post("/", response_model=schemas.SubstitutionResponse, responses={400: {"description": "Aula, timeslot ou professor inválidos"}})
async def create_substitution(
    sub_in: schemas.SubstitutionCreate,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)], # Apenas Admin/Diretor
):
    """
    Grava a substituição e dispara notificações (futuro).
    """
    new_sub = await substitution_service.create_substitution(db, sub_in, current_user.organization_id)

    if new_sub == "INVALID_LESSON":
        raise HTTPException(status_code=400, detail="Aula inválida ou fora da organização")
    if new_sub == "INVALID_TIMESLOT":
        raise HTTPException(status_code=400, detail="Timeslot inválido ou fora da organização")
    if new_sub == "INVALID_TEACHER":
        raise HTTPException(status_code=400, detail="Professor inválido ou fora da organização")
    if new_sub == "ORIGINAL_TEACHER_MISMATCH":
        raise HTTPException(status_code=400, detail="Professor original não corresponde à aula")
    
    # Note: Celery Task para enviar email ao original e ao substituto pode ser adicionado aqui no futuro.
    
    return new_sub

@router.get("/", response_model=List[schemas.SubstitutionResponse])
async def read_substitutions(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)],
    skip: int = 0,
    limit: int = 100,
):
    """
    Retorna a lista de substituições ativas (para pintar no calendário).
    """
    # Precisamos de criar esta função no service (ver passo seguinte)
    substitutions = await substitution_service.get_active_substitutions(
        db,
        org_id=current_user.organization_id,
        skip=skip,
        limit=limit
    )
    return substitutions