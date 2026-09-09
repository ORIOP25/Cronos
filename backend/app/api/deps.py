# Ficheiro: backend/app/api/deps.py
from collections.abc import AsyncGenerator
from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.core.auth import Actor
from app.core.clerk import ClerkGateway, verify_clerk_request
from app.db.database import SessionLocal
from app.db.tenant import set_async_tenant_context
from app.scheduler.infrastructure.task_dispatcher import CelerySchedulerTaskDispatcher
from app.services.clerk_access_service import ClerkAccessService
from app.services.legal_acceptance_service import LegalAcceptanceService
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
        logger.warning("clerk_auth_rejected", auth_failure_category=reason or category.lower())
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
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
    payload: Annotated[dict | None, Depends(get_clerk_payload)] = None,
) -> Actor:
    if payload is None:
        payload = await get_clerk_payload(request)
    clerk_user_id = payload.get("sub")
    organization_claim = payload.get("o") or {}
    clerk_org_id = organization_claim.get("id")
    token_role = organization_claim.get("rol")
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
        organization_id = await db.scalar(
            text("SELECT app_security.resolve_webhook_organization(:clerk_org_id)"),
            {"clerk_org_id": clerk_org_id},
        )
        if organization_id is not None:
            await set_async_tenant_context(db, int(organization_id))
            from app.services import clerk_sync

            await clerk_sync.sync_user_from_clerk_api(
                db,
                clerk_user_id,
                organization_id=int(organization_id),
                role=token_role,
            )
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


async def get_current_legal_accepted_user(
    current_user: Annotated[Actor, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> Actor:
    status_value = await LegalAcceptanceService(db).status(current_user.organization_id)
    if status_value.requires_acceptance:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "LEGAL_ACCEPTANCE_REQUIRED",
                "message": "A organização deve aceitar os documentos legais antes de continuar.",
                "terms_version": status_value.terms_version,
                "dpa_version": status_value.dpa_version,
                "privacy_version": status_value.privacy_version,
            },
        )
    return current_user


async def get_current_active_user(
    current_user: Annotated[Actor, Depends(get_current_legal_accepted_user)],
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> Actor:
    status_value = await db.scalar(
        select(models.Organization.foundation_status).where(
            models.Organization.id == current_user.organization_id
        )
    )
    if status_value != models.OrganizationFoundationStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "FOUNDATION_REQUIRED",
                "message": "A fundação escolar deve ser concluída antes de aceder aos módulos operacionais.",
                "foundation_status": status_value.value if status_value else "NOT_STARTED",
            },
        )
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


def get_foundation_admin(
    current_user: Annotated[Actor, Depends(get_current_legal_accepted_user)],
) -> Actor:
    if not user_has_admin_capability(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


def get_legal_admin(
    current_user: Annotated[Actor, Depends(get_current_user)],
) -> Actor:
    if not user_has_admin_capability(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "LEGAL_ACCEPTANCE_ADMIN_REQUIRED",
                "message": "A aceitação exige capacidade de administrador.",
            },
        )
    return current_user


def get_current_active_admin(
    current_user: Annotated[Actor, Depends(get_current_active_user)],
) -> Actor:
    if not user_has_admin_capability(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


# FastAPI 0.139 supports function-scoped yield dependencies. SonarPython does
# not yet recognize the scope keyword in this Depends signature.
DbSession = Annotated[
    AsyncSession,
    Depends(get_db, scope="function"),  # NOSONAR
]
ClerkGatewayDep = Annotated[ClerkGateway, Depends(get_clerk_gateway)]
MemberAccessOperationDep = Annotated[
    MemberAccessOperationService,
    Depends(get_member_access_operation_service),
]
SessionActor = Annotated[Actor, Depends(get_current_user)]
LegalAcceptedActor = Annotated[Actor, Depends(get_current_legal_accepted_user)]
LegalAdminActor = Annotated[Actor, Depends(get_legal_admin)]
FoundationAdminActor = Annotated[Actor, Depends(get_foundation_admin)]
ActiveActor = Annotated[Actor, Depends(get_current_active_user)]
AdminActor = Annotated[Actor, Depends(get_current_active_admin)]


def get_scheduler_task_dispatcher() -> CelerySchedulerTaskDispatcher:
    return CelerySchedulerTaskDispatcher()
