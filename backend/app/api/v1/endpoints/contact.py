from fastapi import APIRouter, Request, Response, status

from app.contact.dependencies import ContactServiceDep
from app.core.client_ip import get_client_ip
from app.core.ratelimit import limiter
from app.schemas import ContactSubmission

router = APIRouter()


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/day")
@limiter.limit("5/hour")
async def submit_contact(
    request: Request,
    submission: ContactSubmission,
    service: ContactServiceDep,
) -> Response:
    await service.submit(submission, remote_ip=get_client_ip(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
