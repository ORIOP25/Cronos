from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app import schemas, models
from app.api import deps
from app.services import module_service

router = APIRouter()

@router.get("/", response_model=List[schemas.ModuleRead])
async def read_modules(
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user)
):
    return await module_service.get_modules_by_org(db, current_user.organization_id)

@router.post("/", response_model=schemas.ModuleRead)
async def create_module(
    item: schemas.ModuleCreate, 
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_admin)
):
    result = await module_service.create_module(db, item, current_user.organization_id)
    if result == "INVALID_SUBJECT":
        raise HTTPException(status_code=400, detail="Disciplina inválida ou não pertence à organização")
    return result

@router.patch("/{module_id}", response_model=schemas.ModuleRead)
async def update_module(
    module_id: int,
    item: schemas.ModuleUpdate, 
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_admin)
):
    # Nota: O service deve ter a função update_module. 
    # Se não tiver, verifica o module_service.py também.
    updated = await module_service.update_module(db, module_id, item, current_user.organization_id)
    if updated == "INVALID_SUBJECT":
        raise HTTPException(status_code=400, detail="Disciplina inválida ou não pertence à organização")
    if not updated:
        raise HTTPException(status_code=404, detail="Módulo não encontrado")
    return updated

@router.delete("/{module_id}")
async def delete_module(
    module_id: int, 
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_admin)
):
    status = await module_service.delete_module(db, module_id, current_user.organization_id)
    
    if status == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Módulo não encontrado")
    
    if status == "DEPENDENCY_ERROR":
        raise HTTPException(status_code=400, detail="Não é possível apagar: Existem registos de progresso para este módulo.")
    
    return {"message": "Módulo removido com sucesso"}