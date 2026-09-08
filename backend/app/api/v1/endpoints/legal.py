from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.api import deps
from app.services.legal_acceptance_service import (
    LegalAcceptanceAuthorityError,
    LegalAcceptanceError,
    LegalAcceptanceService,
    LegalDocumentVersionStaleError,
)

router = APIRouter(prefix="/legal", tags=["Legal"])


@router.get("/status", response_model=schemas.LegalStatusResponse)
async def get_legal_status(
    current_user: deps.SessionActor,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
):
    return await LegalAcceptanceService(db).status(current_user.organization_id)


@router.post("/acceptance", response_model=schemas.LegalAcceptanceRead)
async def accept_legal_documents(
    command: schemas.LegalAcceptanceCreate,
    current_user: deps.LegalAdminActor,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
):
    try:
        return await LegalAcceptanceService(db).accept(
            current_user.organization_id, current_user, command
        )
    except LegalDocumentVersionStaleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except LegalAcceptanceAuthorityError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except LegalAcceptanceError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
