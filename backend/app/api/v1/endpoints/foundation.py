from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.api import deps
from app.services.foundation_service import (
    FoundationAlreadyCompletedError,
    FoundationDraftVersionConflictError,
    FoundationIncompleteDraftError,
    FoundationService,
)

router = APIRouter(prefix="/foundation", tags=["foundation"])


@router.get("/status", response_model=schemas.FoundationStatusResponse)
async def get_foundation_status(
    current_user: deps.SessionActor,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
):
    service = FoundationService(db)
    return await service.get_status(current_user.organization_id)


@router.get("/draft", response_model=schemas.FoundationDraftRead)
async def get_foundation_draft(
    current_user: deps.FoundationAdminActor,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
):
    service = FoundationService(db)
    return await service.get_draft(current_user.organization_id)


@router.put("/draft", response_model=schemas.FoundationDraftRead)
async def save_foundation_draft(
    data: schemas.FoundationDraftWrite,
    current_user: deps.FoundationAdminActor,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
):
    service = FoundationService(db)
    try:
        return await service.save_draft(
            current_user.organization_id,
            data,
            membership_id=current_user.membership_id,
        )
    except FoundationDraftVersionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "FOUNDATION_DRAFT_VERSION_CONFLICT",
                "message": "O rascunho da fundação foi modificado por outro administrador.",
                "current_version": exc.current_version,
            },
        ) from exc
    except FoundationAlreadyCompletedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "FOUNDATION_ALREADY_COMPLETED",
                "message": str(exc),
            },
        ) from exc


@router.post("/complete", response_model=schemas.FoundationCompleteResponse)
async def complete_foundation(
    command: schemas.FoundationCompleteCommand,
    current_user: deps.FoundationAdminActor,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
):
    service = FoundationService(db)
    try:
        return await service.complete_foundation(
            current_user.organization_id,
            command,
            membership_id=current_user.membership_id,
        )
    except FoundationDraftVersionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "FOUNDATION_DRAFT_VERSION_CONFLICT",
                "message": "O rascunho da fundação foi modificado antes da confirmação.",
                "current_version": exc.current_version,
            },
        ) from exc
    except FoundationIncompleteDraftError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "FOUNDATION_INCOMPLETE",
                "message": str(exc),
            },
        ) from exc
