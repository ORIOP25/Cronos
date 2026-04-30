from datetime import date
from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.ext.asyncio import AsyncSession
from app import models, schemas
from app.api import deps
from app.services import timesheet_service

router = APIRouter()

@router.get(
    "/",
    response_model=List[schemas.TeacherWeeklyTimesheetRead],
    summary="Listar timesheets semanais",
)
async def list_timesheets(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)],
    week_start_date: Optional[date] = None,
    status: Optional[models.TimesheetStatus] = None,
):
    if current_user.role != models.UserRole.admin and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Acesso negado.")
        
    def _run(sync_db):
        return timesheet_service.list_timesheets_sync(
            sync_db,
            org_id=current_user.organization_id,
            week_start_date=week_start_date,
            status=status
        )
        
    return await db.run_sync(_run)

@router.get(
    "/me/{week_start_date}",
    response_model=schemas.TeacherWeeklyTimesheetRead,
    summary="Obter estado da timesheet do professor autenticado",
)
async def get_my_timesheet(
    week_start_date: date,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)],
):
    if current_user.role != models.UserRole.teacher:
        raise HTTPException(status_code=403, detail="Apenas professores podem consultar a sua timesheet.")
        
    def _run(sync_db):
        return timesheet_service.get_or_create_timesheet_sync(
            sync_db,
            org_id=current_user.organization_id,
            teacher_id=current_user.teacher_id,
            week_start_date=week_start_date
        )
        
    return await db.run_sync(_run)

@router.post(
    "/me/{week_start_date}/submit",
    response_model=schemas.TeacherWeeklyTimesheetRead,
    summary="Submeter a timesheet semanal",
)
async def submit_my_timesheet(
    week_start_date: date,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)],
):
    if current_user.role != models.UserRole.teacher:
        raise HTTPException(status_code=403, detail="Apenas professores podem submeter a sua timesheet.")
        
    def _run(sync_db):
        return timesheet_service.submit_timesheet_sync(
            sync_db,
            org_id=current_user.organization_id,
            teacher_id=current_user.teacher_id,
            week_start_date=week_start_date
        )
        
    return await db.run_sync(_run)

@router.patch(
    "/{timesheet_id}/status",
    response_model=schemas.TeacherWeeklyTimesheetRead,
    summary="Aprovar ou reabrir uma timesheet",
)
async def update_timesheet_status(
    timesheet_id: int,
    payload: schemas.TimesheetStatusUpdate,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)],
):
    if current_user.role != models.UserRole.admin and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Apenas admins podem aprovar ou reabrir timesheets.")
        
    def _run(sync_db):
        return timesheet_service.update_timesheet_status_sync(
            sync_db,
            org_id=current_user.organization_id,
            timesheet_id=timesheet_id,
            status=payload.status,
            admin_user_id=current_user.id
        )
        
    return await db.run_sync(_run)
