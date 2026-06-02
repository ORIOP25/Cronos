from typing import Annotated
import json
import structlog
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from svix.webhooks import Webhook, WebhookVerificationError
from app.config import settings
from app.api.deps import get_db
from app.services import clerk_sync
from app.schemas_webhooks import ClerkWebhookEvent

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["webhooks"])


@router.post("/clerk")
async def handle_clerk_webhook(request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
    svix_id = request.headers.get("svix-id")
    svix_timestamp = request.headers.get("svix-timestamp")
    svix_signature = request.headers.get("svix-signature")

    if not all([svix_id, svix_timestamp, svix_signature]):
        raise HTTPException(status_code=400, detail="Missing Svix headers")

    payload = await request.body()

    try:
        wh = Webhook(settings.CLERK_WEBHOOK_SECRET)
        wh.verify(payload, {
            "webhook-id": svix_id,
            "webhook-timestamp": svix_timestamp,
            "webhook-signature": svix_signature,
        })
    except WebhookVerificationError:
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    data = json.loads(payload)
    event = ClerkWebhookEvent(**data)

    logger.info("Webhook recebido", clerk_event=event.type)

    match event.type:
        case "user.created":
            await _handle_user_created(db, event.data)
        case "user.updated":
            await _handle_user_updated(db, event.data)
        case "user.deleted":
            await _handle_user_deleted(db, event.data)
        case "organization.created":
            await _handle_organization_created(db, event.data)
        case "organization.updated":
            await _handle_organization_updated(db, event.data)
        case "organization.deleted":
            await _handle_organization_deleted(db, event.data)
        case "organizationMembership.created":
            await _handle_membership_created(db, event.data)
        case "organizationMembership.updated":
            await _handle_membership_updated(db, event.data)
        case "organizationMembership.deleted":
            await _handle_membership_deleted(db, event.data)
        case _:
            logger.info("Evento ignorado", clerk_event=event.type)

    await db.commit()
    return {"status": "ok"}


async def _handle_user_created(db: AsyncSession, data: dict):
    clerk_user_id = data["id"]
    email = None
    if data.get("email_addresses"):
        email = data["email_addresses"][0]["email_address"]
    name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip() or None
    teacher_id = data.get("public_metadata", {}).get("teacher_id")

    await clerk_sync.ensure_user_exists(
        db=db,
        clerk_user_id=clerk_user_id,
        email=email,
        name=name,
        teacher_id=teacher_id,
    )


async def _handle_user_updated(db: AsyncSession, data: dict):
    await _handle_user_created(db, data)


async def _handle_user_deleted(db: AsyncSession, data: dict):
    clerk_user_id = data["id"]
    await clerk_sync.deactivate_user_by_clerk_id(db, clerk_user_id)


async def _handle_organization_created(db: AsyncSession, data: dict):
    await clerk_sync.ensure_organization_exists(
        db=db,
        clerk_org_id=data["id"],
        org_name=data["name"],
    )


async def _handle_organization_updated(db: AsyncSession, data: dict):
    org = await clerk_sync.ensure_organization_exists(
        db=db,
        clerk_org_id=data["id"],
        org_name=data["name"],
    )
    if org.name != data["name"]:
        org.name = data["name"]
        await db.flush()


async def _handle_organization_deleted(db: AsyncSession, data: dict):
    clerk_org_id = data.get("id")
    if not clerk_org_id:
        return
    await clerk_sync.deactivate_organization_by_clerk_id(db, clerk_org_id)
    logger.info("Organization desativada localmente", clerk_org_id=clerk_org_id)


async def _handle_membership_created(db: AsyncSession, data: dict):
    clerk_user_id = data.get("public_user_data", {}).get("user_id")
    clerk_org_id = data.get("organization", {}).get("id")
    role = data.get("role")
    teacher_id = data.get("public_metadata", {}).get("teacher_id")

    if not clerk_user_id or not clerk_org_id:
        logger.error("Membership sem user_id ou org_id")
        return

    user_data = data.get("public_user_data", {})
    email = user_data.get("identifier")

    org = await clerk_sync.ensure_organization_exists(
        db, clerk_org_id, data["organization"]["name"]
    )

    await clerk_sync.ensure_user_exists(
        db=db,
        clerk_user_id=clerk_user_id,
        email=email,
        role=role,
        organization_id=org.id,
        teacher_id=teacher_id,
    )


async def _handle_membership_updated(db: AsyncSession, data: dict):
    await _handle_membership_created(db, data)


async def _handle_membership_deleted(db: AsyncSession, data: dict):
    clerk_user_id = data.get("public_user_data", {}).get("user_id")
    if not clerk_user_id:
        return

    await clerk_sync.deactivate_user_by_clerk_id(db, clerk_user_id)
