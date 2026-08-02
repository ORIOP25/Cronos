from fastapi import APIRouter, Request, Response, status

from app.core.ratelimit import limiter
from app.schemas import ContactSubmission
from app.services import contact_email_service

router = APIRouter()


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/day")
@limiter.limit("5/hour")
async def submit_contact(request: Request, submission: ContactSubmission) -> Response:
    await contact_email_service.send_contact_email(submission)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
