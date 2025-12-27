from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app import schemas
from app.api import deps
from app.services import teacher_service
from app import models

router = APIRouter()

@router.get("/", response_model=List[schemas.TeacherRead])
async def read_teachers(
    current_user: models.User = Depends(deps.get_current_user), 
    skip: int = 0, 
    limit: int = 100, 
    db: AsyncSession = Depends(deps.get_db)
):
    return await teacher_service.get_teachers_by_org(
        db, 
        org_id=current_user.organization_id, # <--- Usamos o ID do token
        skip=skip, 
        limit=limit
    )

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

@router.delete("/{teacher_id}")
async def delete_teacher(
    teacher_id: int, 
    org_id: int, 
    db: AsyncSession = Depends(deps.get_db)
):
    success = await teacher_service.delete_teacher(db, teacher_id, org_id)
    if not success:
        raise HTTPException(status_code=404, detail="Professor não encontrado")
    return {"ok": True}