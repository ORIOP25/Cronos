from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Annotated
from app import schemas, models
from app.api import deps
from app.services import subject_service

router = APIRouter()

# --- 1. Ler Disciplinas ---
@router.get("/", response_model=List[schemas.SubjectRead])
async def read_subjects(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)]
):
    # Qualquer utilizador autenticado pode ver a lista de disciplinas
    return await subject_service.get_subjects_by_org(db, current_user.organization_id)

# --- 2. Criar Disciplina ---
@router.post("/", response_model=schemas.SubjectRead)
async def create_subject(
    item: schemas.SubjectCreate, 
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)]
):
    return await subject_service.create_subject(db, item, current_user.organization_id)

# --- 3. Atualizar Disciplina ---
@router.patch("/{subject_id}", response_model=schemas.SubjectRead)
async def update_subject(
    subject_id: int,
    subject_in: schemas.SubjectUpdate,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)] # Apenas Admin
):
    subject = await subject_service.update_subject(
        db, 
        subject_id, 
        subject_in, 
        current_user.organization_id
    )
    if not subject:
        raise HTTPException(status_code=404, detail="Disciplina não encontrada")
    return subject

# --- 4. Apagar Disciplina   ---
@router.delete("/{subject_id}")
async def delete_subject(
    subject_id: int, 
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)] # Apenas Admin
):
    status = await subject_service.delete_subject(
        db, 
        subject_id, 
        current_user.organization_id
    )
    
    if status == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Disciplina não encontrada")
    
    if status == "DEPENDENCY_ERROR":
        raise HTTPException(
            status_code=400, 
            detail="Não é possível apagar esta disciplina pois existem aulas associadas a ela."
        )
    
    return {"message": "Disciplina removida com sucesso"}