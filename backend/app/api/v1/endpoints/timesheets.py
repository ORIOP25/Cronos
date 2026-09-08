from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.api import deps
from app.services import timesheet_service

router = APIRouter()


def _model_to_read_dict(t: models.TeacherWeeklyTimesheet) -> dict:
    return {
        "id": t.id,
        "organization_id": t.organization_id,
        "teacher_id": t.teacher_id,
        "teacher_name": t.teacher.name if t.teacher else None,
        "week_start_date": t.week_start_date,
        "week_end_date": t.week_start_date + timedelta(days=6),
        "status": t.status,
        "submitted_at": t.submitted_at,
        "approved_at": t.approved_at,
        "approved_by_membership_id": t.approved_by_membership_id,
        "created_at": t.created_at,
        "total_slots": 0,
        "registered_slots": 0,
        "completed_slots": 0,
        "occurrence_slots": 0,
    }


@router.get(
    "/",
    response_model=list[schemas.TeacherWeeklyTimesheetListRead],
    summary="Listar timesheets semanais",
)
async def list_timesheets(
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.ActiveActor,
    week_start_date: date | None = None,
    status: models.TimesheetStatus | None = None,
):
    if not deps.user_has_admin_capability(current_user):
        raise HTTPException(status_code=403, detail="Acesso negado.")

    def _run(sync_db):
        return timesheet_service.list_timesheets_sync(
            sync_db,
            organization_id=current_user.organization_id,
            week_start_date=week_start_date,
            status=status,
        )

    return await db.run_sync(_run)


@router.get(
    "/me/{week_start_date}",
    response_model=schemas.TeacherWeeklyTimesheetRead,
    summary="Obter estado da timesheet do professor autenticado",
)
async def get_my_timesheet(
    week_start_date: date,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.ActiveActor,
):
    if not deps.user_has_teacher_capability(current_user):
        raise HTTPException(
            status_code=403, detail="Apenas professores podem consultar a sua timesheet."
        )

    def _run(sync_db):
        t = timesheet_service.get_or_create_timesheet_sync(
            sync_db,
            organization_id=current_user.organization_id,
            teacher_id=current_user.teacher_id,
            week_start_date=week_start_date,
        )
        sync_db.refresh(t, ["teacher"])
        return _model_to_read_dict(t)

    return await db.run_sync(_run)


@router.post(
    "/me/{week_start_date}/submit",
    response_model=schemas.TeacherWeeklyTimesheetRead,
    summary="Submeter a timesheet semanal",
)
async def submit_my_timesheet(
    week_start_date: date,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.ActiveActor,
):
    if not deps.user_has_teacher_capability(current_user):
        raise HTTPException(
            status_code=403, detail="Apenas professores podem submeter a sua timesheet."
        )

    def _run(sync_db):
        t = timesheet_service.submit_timesheet_sync(
            sync_db,
            organization_id=current_user.organization_id,
            teacher_id=current_user.teacher_id,
            week_start_date=week_start_date,
        )
        sync_db.refresh(t, ["teacher"])
        return _model_to_read_dict(t)

    return await db.run_sync(_run)


@router.get(
    "/{timesheet_id}/pending-occurrences",
    summary="Listar ocorrÃªncias por decidir na semana de uma timesheet",
)
async def get_pending_occurrences_for_timesheet(
    timesheet_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.ActiveActor,
):
    """Devolve as ocorrÃªncias OPEN na semana associada Ã  timesheet."""
    if not deps.user_has_admin_capability(current_user):
        raise HTTPException(status_code=403, detail="Acesso negado.")

    def _run(sync_db):
        return timesheet_service.get_open_occurrences_for_timesheet_sync(
            sync_db,
            organization_id=current_user.organization_id,
            timesheet_id=timesheet_id,
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
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.ActiveActor,
):
    if not deps.user_has_admin_capability(current_user):
        raise HTTPException(
            status_code=403, detail="Apenas admins podem aprovar ou reabrir timesheets."
        )

    def _run(sync_db):
        return timesheet_service.update_timesheet_status_sync(
            sync_db,
            organization_id=current_user.organization_id,
            timesheet_id=timesheet_id,
            status=payload.status,
            admin_membership_id=current_user.membership_id,
        )

    return await db.run_sync(_run)
