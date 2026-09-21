from urllib.parse import quote

from fastapi import APIRouter, Response

from app import schemas
from app.api import deps
from app.services import bulk_import_service
from app.services.bulk_import_policy import TEMPLATE_DEFINITIONS

router = APIRouter()


@router.get("/templates/{resource}", response_class=Response)
async def download_template(resource: str, _current_user: deps.AdminActor) -> Response:
    content = bulk_import_service.template_bytes(resource)
    filename = TEMPLATE_DEFINITIONS[resource].filename
    safe_filename = filename.replace('"', "")
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{safe_filename}"; '
                f"filename*=UTF-8''{quote(safe_filename)}"
            )
        },
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
