from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Query, Response

from app import schemas
from app.api import deps
from app.services import bulk_import_service
from app.services.bulk_import_policy import template_filename

router = APIRouter()


def _attachment(filename: str) -> dict[str, str]:
    safe_filename = filename.replace('"', "")
    return {
        "Content-Disposition": (
            f"attachment; filename=\"{safe_filename}\"; filename*=UTF-8''{quote(safe_filename)}"
        )
    }


@router.get("/templates", response_class=Response)
async def download_template_bundle(
    resource: Annotated[list[str], Query(min_length=1)],
    db: deps.DbSession,
    _current_user: deps.AdminActor,
) -> Response:
    content = await bulk_import_service.template_bundle_bytes(
        db, _current_user.organization_id, resource
    )
    return Response(
        content=content,
        media_type="application/zip",
        headers=_attachment("Cronos_Modelos.zip"),
    )


@router.get("/templates/{resource}", response_class=Response)
async def download_template(
    resource: str, db: deps.DbSession, _current_user: deps.AdminActor
) -> Response:
    content = await bulk_import_service.template_bytes(db, _current_user.organization_id, resource)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers=_attachment(template_filename(resource)),
    )


@router.post("/validate", response_model=schemas.BulkImportValidationResponse)
async def validate_import(
    request: schemas.BulkImportFilesRequest,
    db: deps.DbSession,
    current_user: deps.AdminActor,
) -> schemas.BulkImportValidationResponse:
    return await bulk_import_service.validate(db, request, current_user.organization_id)


@router.post(
    "/commit",
    response_model=schemas.BulkImportCommitResponse,
    status_code=201,
)
async def commit_import(
    request: schemas.BulkImportFilesRequest,
    db: deps.DbSession,
    current_user: deps.AdminActor,
) -> schemas.BulkImportCommitResponse:
    return await bulk_import_service.commit_import(
        db,
        request,
        current_user.organization_id,
        current_user,
    )
