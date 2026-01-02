# Ficheiro: backend/app/api/endpoints/teachers.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app import schemas
from app.api import deps
from app.services import teacher_service
from app import models

router = APIRouter()

# --- 1. Ler Professores ---
@router.get("/", response_model=List[schemas.TeacherRead])
async def read_teachers(
    current_user: models.User = Depends(deps.get_current_user), 
    skip: int = 0, 
    limit: int = 100, 
    db: AsyncSession = Depends(deps.get_db)
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
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user)
):
    return await teacher_service.create_teacher(
        db,
        teacher,
        org_id=current_user.organization_id
    )

# --- 3. Apagar Professor ---
@router.delete("/{teacher_id}")
async def delete_teacher(
    teacher_id: int, 
    # org_id não vem no path, tiramo-lo do token de segurança para garantir que ninguém apaga profs de outra escola
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user)
):
    success = await teacher_service.delete_teacher(db, teacher_id, current_user.organization_id)
    if not success:
        raise HTTPException(status_code=404, detail="Professor não encontrado")
    return {"ok": True}

# --- 4. NOVO ENDPOINT: Gravar Disponibilidades ---
# Chama o serviço que já existe em teacher_service.py
@router.post("/{teacher_id}/availability")
async def update_teacher_availability(
    teacher_id: int,
    availability_data: List[schemas.AvailabilityCreate], # Recebe a lista do Frontend
    db: AsyncSession = Depends(deps.get_db)
):
    """
    Grava as preferências de horário chamando o serviço dedicado.
    """
    result = await teacher_service.set_teacher_availability(
        db, 
        teacher_id, 
        availability_data
    )
    return result