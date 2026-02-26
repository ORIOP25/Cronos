# Ficheiro: backend/app/api/endpoints/teachers.py

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Annotated
from app import schemas
from app.api import deps
from app.services import teacher_service
from app.core.ratelimit import limiter
from app import models

router = APIRouter()

# --- 1. Ler Professores ---
@router.get("/", response_model=List[schemas.TeacherRead])
async def read_teachers(
    current_user: Annotated[models.User, Depends(deps.get_current_user)],
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    skip: int = 0, 
    limit: int = 100,
):
    return await teacher_service.get_teachers_by_org(
        db, 
        org_id=current_user.organization_id, 
        skip=skip, 
        limit=limit
    )

# --- 2. Criar Professor ---
@router.post("/", response_model=schemas.TeacherRead)
async def create_teacher(
    teacher: schemas.TeacherCreate,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_user)]
):
    return await teacher_service.create_teacher(
        db,
        teacher,
        org_id=current_user.organization_id
    )

# --- 4. NOVO ENDPOINT: Gravar Disponibilidades ---
# Chama o serviço que já existe em teacher_service.py
@router.post("/{teacher_id}/availability")
@limiter.limit("30/minute")
async def update_teacher_availability(
    request: Request,
    teacher_id: int,
    availability_data: List[schemas.AvailabilitySelfCreate], # Recebe a lista do Frontend
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)]
):
    """
    Grava as preferências de horário chamando o serviço dedicado.
    """
    # Professores só podem atualizar a própria disponibilidade
    if current_user.role == models.UserRole.teacher and current_user.teacher_id != teacher_id:
        raise HTTPException(status_code=403, detail="Sem permissões para atualizar outro professor")

    result = await teacher_service.set_teacher_availability(
        db, 
        teacher_id, 
        availability_data,
        org_id=current_user.organization_id
    )

    if result == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Professor não encontrado")

    if result == "INVALID_TIMESLOT":
        raise HTTPException(status_code=400, detail="Timeslot inválido ou fora da organização")

    return result

# --- 3. Atualizar Professor (PATCH) ---
@router.patch("/{teacher_id}", response_model=schemas.TeacherRead)
async def update_teacher(
    teacher_id: int,
    teacher_in: schemas.TeacherUpdate,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)] # Apenas Admins
):
    """
    Atualiza dados do professor (ex: Nome).
    """
    teacher = await teacher_service.update_teacher(
        db, 
        teacher_id, 
        teacher_in, 
        org_id=current_user.organization_id
    )
    if not teacher:
        raise HTTPException(status_code=404, detail="Professor não encontrado")
    return teacher

# --- 4. Apagar Professor (DELETE) ---
@router.delete("/{teacher_id}")
async def delete_teacher(
    teacher_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)] # Apenas Admins
):
    """
    Remove um professor. Falha se o professor tiver aulas atribuídas.
    """
    status_result = await teacher_service.delete_teacher(
        db, 
        teacher_id, 
        org_id=current_user.organization_id
    )
    
    if status_result == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Professor não encontrado")
    
    if status_result == "DEPENDENCY_ERROR":
        # Erro 400 ou 409 (Conflict) é adequado aqui.
        raise HTTPException(
            status_code=400, 
            detail="Não é possível apagar este professor pois ele tem aulas atribuídas. Remova as aulas primeiro."
        )
    
    return {"message": "Professor removido com sucesso"}