from typing import List, Annotated
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app import schemas, models
from app.api import deps
from app.services import schedule_service

router = APIRouter()

@router.get("/", response_model=List[schemas.LessonRead])
async def read_lessons(
    current_user: Annotated[models.User, Depends(deps.get_current_user)],
    db: Annotated[AsyncSession, Depends(deps.get_db)]
):
    """
    Lista todas as aulas da organização.
    """
    return await schedule_service.get_lessons_by_org(
        db, 
        org_id=current_user.organization_id
    )

@router.post("/", response_model=schemas.LessonRead)
async def create_lesson(
    lesson: schemas.LessonCreate,
    current_user: Annotated[models.User, Depends(deps.get_current_user)],
    db: Annotated[AsyncSession, Depends(deps.get_db)]
):
    """
    Cria uma nova aula (ex: Matemática, 12ºA, Prof. Snape, 2x por semana).
    """
    return await schedule_service.create_lesson(
        db, 
        lesson, 
        org_id=current_user.organization_id
    )