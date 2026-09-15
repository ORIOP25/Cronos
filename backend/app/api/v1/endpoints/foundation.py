from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.api import deps
from app.core.exceptions import AppError
from app.services.foundation_service import (
    FoundationAlreadyCompletedError,
    FoundationDraftVersionConflictError,
    FoundationIncompleteDraftError,
    FoundationService,
)
from app.services.settings_service import HolidaySyncError

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
        raise AppError(
            kind="conflict",
            code="FOUNDATION_DRAFT_VERSION_CONFLICT",
            detail=str(exc),
            public_context={"current_version": exc.current_version},
        ) from exc
    except FoundationAlreadyCompletedError as exc:
        raise AppError(
            kind="conflict",
            code="FOUNDATION_ALREADY_COMPLETED",
            detail=str(exc),
        ) from exc
    except HolidaySyncError as exc:
        raise AppError(
            kind="unavailable",
            code=exc.code,
            detail=str(exc),
            public_retryable=True,
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
        raise AppError(
            kind="conflict",
            code="FOUNDATION_DRAFT_VERSION_CONFLICT",
            detail=str(exc),
            public_context={"current_version": exc.current_version},
        ) from exc
    except FoundationIncompleteDraftError as exc:
        raise AppError(
            kind="validation",
            code="FOUNDATION_INCOMPLETE",
            detail=str(exc),
        ) from exc
    except HolidaySyncError as exc:
        raise AppError(
            kind="unavailable",
            code=exc.code,
            detail=str(exc),
            public_retryable=True,
        ) from exc
