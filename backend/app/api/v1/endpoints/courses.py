from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app import schemas, models
from app.api import deps
from app.services import course_service

router = APIRouter()

@router.get("/", response_model=List[schemas.CourseRead])
async def read_courses(
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user)
):
    return await course_service.get_courses_by_org(db, current_user.organization_id)

@router.post("/", response_model=schemas.CourseRead)
async def create_course(
    item: schemas.CourseCreate, 
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_admin)
):
    return await course_service.create_course(db, item, current_user.organization_id)

@router.delete("/{course_id}")
async def delete_course(
    course_id: int, 
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_admin)
):
    status = await course_service.delete_course(db, course_id, current_user.organization_id)
    
    if status == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Curso não encontrado")
    
    if status == "DEPENDENCY_ERROR":
        raise HTTPException(status_code=400, detail="Não é possível apagar: Existem turmas associadas a este curso.")
    
    return {"message": "Curso removido com sucesso"}