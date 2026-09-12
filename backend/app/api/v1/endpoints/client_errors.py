import structlog
from fastapi import APIRouter, Request, Response, status

from app.core.ratelimit import limiter
from app.schemas import ClientErrorReport

router = APIRouter()
logger = structlog.get_logger()


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")
async def report_client_error(request: Request, report: ClientErrorReport) -> Response:
    logger.info(
        "client_error_reported",
        client_error_reference=report.reference,
        category=report.category,
        revision=report.revision,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
