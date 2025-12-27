from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.api import deps
from app import models, schemas
from app.services import (
    teacher_service, 
    class_service, 
    subject_service, 
    room_service, 
    schedule_service
)

router = APIRouter()

# --- TIMESLOTS ---
@router.get("/timeslots", response_model=List[schemas.TimeslotRead])
async def get_import_timeslots(
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user)
):
    # O Frontend usa isto para saber que tempos existem
    return await schedule_service.get_timeslots_by_org(db, current_user.organization_id)

# --- TEACHERS ---
@router.get("/teachers", response_model=List[schemas.TeacherRead])
async def get_import_teachers(
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user)
):
    return await teacher_service.get_teachers_by_org(db, current_user.organization_id)

# --- ROOMS (Estava a dar 404) ---
@router.get("/rooms", response_model=List[schemas.RoomRead])
async def get_import_rooms(
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user)
):
    return await room_service.get_rooms_by_org(db, current_user.organization_id)

# --- CLASSES (Estava a dar 404) ---
@router.get("/classes", response_model=List[schemas.ClassRead])
async def get_import_classes(
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user)
):
    return await class_service.get_classes_by_org(db, current_user.organization_id)

# --- SUBJECTS (Estava a dar 404) ---
@router.get("/subjects", response_model=List[schemas.SubjectRead])
async def get_import_subjects(
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user)
):
    return await subject_service.get_subjects_by_org(db, current_user.organization_id)

# --- LESSONS (Estava a dar 404) ---
@router.get("/lessons", response_model=List[schemas.LessonRead])
async def get_import_lessons(
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_user)
):
    return await schedule_service.get_lessons_by_org(db, current_user.organization_id)