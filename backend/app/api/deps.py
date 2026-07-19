# Ficheiro: backend/app/api/deps.py
from collections.abc import AsyncGenerator
from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.core.auth import Actor
from app.core.clerk import ClerkGateway, verify_clerk_request
from app.db.database import SessionLocal
from app.db.tenant import set_async_tenant_context
from app.scheduler.infrastructure.task_dispatcher import CelerySchedulerTaskDispatcher
from app.services.clerk_access_service import ClerkAccessService
from app.services.member_access_operation_service import MemberAccessOperationService

logger = structlog.get_logger(__name__)


# --- DATABASE ---
async def get_db() -> AsyncGenerator:
    async with SessionLocal() as db:
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise


# --- CLERK AUTH ---
def get_clerk_gateway(request: Request) -> ClerkGateway:
    return request.app.state.clerk


def get_member_access_operation_service(
    gateway: Annotated[ClerkGateway, Depends(get_clerk_gateway)],
) -> MemberAccessOperationService:
    return MemberAccessOperationService(SessionLocal, ClerkAccessService(gateway))


async def get_clerk_payload(
    request: Request,
    gateway: Annotated[ClerkGateway, Depends(get_clerk_gateway)] = None,
) -> dict:
    state = await verify_clerk_request(request, gateway)
    if not state.is_signed_in:
        reason_value = getattr(getattr(state, "reason", None), "value", None)
        reason = reason_value[0] if isinstance(reason_value, tuple) else reason_value
        category = (
            "INVALID_AUTHORIZED_PARTY"
            if reason == "token-invalid-authorized-parties"
            else "NOT_AUTHENTICATED"
        )
        logger.warning("clerk_auth_rejected", auth_failure_category=category.lower())
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": category,
                "message": "Not authenticated; authentication could not be verified.",
            },
        )
    return state.payload or {}


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    payload: Annotated[dict | None, Depends(get_clerk_payload)] = None,
) -> Actor:
    if payload is None:
        payload = await get_clerk_payload(request)
    clerk_user_id = payload.get("sub")
    clerk_org_id = (payload.get("o") or {}).get("id")
    if not clerk_user_id:
        raise HTTPException(status_code=401, detail="No user ID in token")
    if not clerk_org_id:
        raise HTTPException(status_code=403, detail="Organization required")

    from sqlalchemy import text

    result = await db.execute(
        text(
            """
            SELECT account_id, organization_id, membership_id,
                   can_admin, can_teach, teacher_id
            FROM app_security.resolve_principal(:clerk_user_id, :clerk_org_id)
            """
        ),
        {"clerk_user_id": clerk_user_id, "clerk_org_id": clerk_org_id},
    )
    principal = result.mappings().one_or_none()
    if principal is None:
        raise HTTPException(status_code=403, detail="Active organization membership required")

    organization_id = int(principal["organization_id"])
    await set_async_tenant_context(db, organization_id)
    request.state.current_organization_id = organization_id
    return Actor(
        account_id=int(principal["account_id"]),
        clerk_user_id=clerk_user_id,
        organization_id=organization_id,
        membership_id=int(principal["membership_id"]),
        can_admin=bool(principal["can_admin"]),
        can_teach=bool(principal["can_teach"]),
        teacher_id=(int(principal["teacher_id"]) if principal["teacher_id"] is not None else None),
    )


async def get_current_active_user(
    current_user: Annotated[Actor, Depends(get_current_user)],
) -> Actor:
    return current_user


def user_has_capability(
    current_user: Actor,
    capability: models.MembershipCapability,
) -> bool:
    return (
        current_user.can_admin
        if capability == models.MembershipCapability.admin
        else current_user.can_teach
    )


def user_has_admin_capability(current_user: Actor) -> bool:
    return user_has_capability(current_user, models.MembershipCapability.admin)


def user_has_teacher_capability(current_user: Actor) -> bool:
    return bool(
        user_has_capability(current_user, models.MembershipCapability.teacher)
        and current_user.teacher_id is not None
    )


def actor_role(current_user: Actor) -> str:
    if user_has_admin_capability(current_user):
        return "admin"
    if user_has_teacher_capability(current_user):
        return "teacher"
    return "member"


def get_current_active_admin(
    current_user: Annotated[Actor, Depends(get_current_active_user)],
) -> Actor:
    if not user_has_admin_capability(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


DbSession = Annotated[AsyncSession, Depends(get_db, scope="function")]
ClerkGatewayDep = Annotated[ClerkGateway, Depends(get_clerk_gateway)]
MemberAccessOperationDep = Annotated[
    MemberAccessOperationService,
    Depends(get_member_access_operation_service),
]
ActiveActor = Annotated[Actor, Depends(get_current_active_user)]
AdminActor = Annotated[Actor, Depends(get_current_active_admin)]


def get_scheduler_task_dispatcher() -> CelerySchedulerTaskDispatcher:
    return CelerySchedulerTaskDispatcher()
