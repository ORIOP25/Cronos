import json
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from svix.webhooks import Webhook, WebhookVerificationError

from app import models
from app.api.deps import get_db
from app.config import settings
from app.services.member_webhook_service import enqueue_and_process_clerk_event

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["webhooks"])
MAX_WEBHOOK_BODY_BYTES = 256 * 1024


@router.post("/clerk")
async def handle_clerk_webhook(
    request: Request, db: Annotated[AsyncSession, Depends(get_db, scope="function")]
):
    svix_id = request.headers.get("svix-id")
    svix_timestamp = request.headers.get("svix-timestamp")
    svix_signature = request.headers.get("svix-signature")

    if not settings.CLERK_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Clerk webhook secret is not configured")
    if not all([svix_id, svix_timestamp, svix_signature]):
        raise HTTPException(status_code=400, detail="Missing Svix headers")

    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_WEBHOOK_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Webhook body is too large")

    payload = await request.body()
    if len(payload) > MAX_WEBHOOK_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Webhook body is too large")
    try:
        wh = Webhook(settings.CLERK_WEBHOOK_SECRET)
        wh.verify(
            payload,
            {
                "webhook-id": svix_id,
                "webhook-timestamp": svix_timestamp,
                "webhook-signature": svix_signature,
            },
        )
    except (WebhookVerificationError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid webhook signature") from exc

    data = json.loads(payload)
    event = await enqueue_and_process_clerk_event(db, svix_id=svix_id, payload=data)
    logger.info(
        "Clerk webhook processed",
        svix_id=svix_id,
        event_type=event.event_type,
        status=event.processing_status.value,
    )
    if event.processing_status in {
        models.ClerkWebhookProcessingStatus.processing,
        models.ClerkWebhookProcessingStatus.received,
        models.ClerkWebhookProcessingStatus.retryable_failed,
    }:
        return JSONResponse(status_code=503, content={"status": event.processing_status.value})
    return {"status": event.processing_status.value}
