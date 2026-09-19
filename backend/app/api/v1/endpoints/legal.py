from fastapi import APIRouter

from app import schemas
from app.api import deps
from app.core.exceptions import AppError
from app.services.legal_acceptance_service import (
    LegalAcceptanceAuthorityError,
    LegalAcceptanceError,
    LegalAcceptanceService,
    LegalDocumentVersionStaleError,
)

router = APIRouter(prefix="/legal", tags=["Legal"])


def _raise_legal_error(exc: LegalAcceptanceError) -> None:
    kind = {403: "forbidden", 409: "conflict"}.get(exc.status_code, "bad_request")
    raise AppError(kind=kind, code=exc.code, detail=str(exc)) from exc


@router.get("/status", response_model=schemas.LegalStatusResponse)
async def get_legal_status(
    current_user: deps.SessionActor,
    db: deps.DbSession,
):
    return await LegalAcceptanceService(db).status(current_user.organization_id)


@router.post("/acceptance", response_model=schemas.LegalAcceptanceRead)
async def accept_legal_documents(
    command: schemas.LegalAcceptanceCreate,
    current_user: deps.LegalAdminActor,
    db: deps.DbSession,
):
    try:
        return await LegalAcceptanceService(db).accept(
            current_user.organization_id, current_user, command
        )
    except LegalDocumentVersionStaleError as exc:
        _raise_legal_error(exc)
    except LegalAcceptanceAuthorityError as exc:
        _raise_legal_error(exc)
    except LegalAcceptanceError as exc:
        _raise_legal_error(exc)
