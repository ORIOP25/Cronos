from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Annotated

from app import schemas, models
from app.api import deps
from app.services import substitution_service

router = APIRouter()

@router.get(
    "/suggestions",
    deprecated=True,
    responses={410: {"description": "Endpoint legado descontinuado"}},
)
async def get_suggestions(
    timeslot_id: int,
    date_str: str, # Recebemos como string "2026-03-12" e convertemos
    original_teacher_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)],
):
    """Endpoint legado descontinuado em favor do fluxo canónico por ocorrência."""
    _ = (timeslot_id, date_str, original_teacher_id, db, current_user)
    raise HTTPException(
        status_code=410,
        detail=(
            "Endpoint legado descontinuado. Use o fluxo canónico de ocorrências: "
            "GET /api/v1/occurrences/{occurrence_id}/substitutes/recommendations"
        ),
    )

@router.post("/", response_model=schemas.SubstitutionResponse, responses={400: {"description": "Aula, timeslot ou professor inválidos"}})
async def create_substitution(
    sub_in: schemas.SubstitutionCreate,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)], # Apenas Admin/Diretor
):
    """
    Grava a substituição e dispara notificações (futuro).
    """
    try:
        new_sub = await substitution_service.create_substitution(
            db,
            sub_in,
            current_user.organization_id,
        )
    except substitution_service.SubstitutionServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

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
        organization_id=current_user.organization_id,
        skip=skip,
        limit=limit
    )
    return substitutions