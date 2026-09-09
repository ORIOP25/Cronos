"""Application service for organization legal acceptance."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.core.auth import Actor
from app.legal import CURRENT_DPA_VERSION, CURRENT_PRIVACY_VERSION, CURRENT_TERMS_VERSION


class LegalAcceptanceError(Exception):
    status_code = 409
    code = "LEGAL_ACCEPTANCE_ERROR"


class LegalDocumentVersionStaleError(LegalAcceptanceError):
    code = "LEGAL_DOCUMENT_VERSION_STALE"


class LegalAcceptanceAuthorityError(LegalAcceptanceError):
    status_code = 403
    code = "LEGAL_ACCEPTANCE_ADMIN_REQUIRED"


class LegalAcceptanceTenantError(LegalAcceptanceError):
    status_code = 403
    code = "LEGAL_ACCEPTANCE_TENANT_MISMATCH"


class LegalAcceptanceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def status(self, organization_id: int) -> schemas.LegalStatusResponse:
        acceptance = await self.db.scalar(
            select(models.OrganizationLegalAcceptance)
            .where(
                models.OrganizationLegalAcceptance.organization_id == organization_id,
                models.OrganizationLegalAcceptance.terms_version == CURRENT_TERMS_VERSION,
                models.OrganizationLegalAcceptance.dpa_version == CURRENT_DPA_VERSION,
                models.OrganizationLegalAcceptance.privacy_version == CURRENT_PRIVACY_VERSION,
            )
            .order_by(models.OrganizationLegalAcceptance.id.desc())
        )
        return schemas.LegalStatusResponse(
            accepted=acceptance is not None,
            requires_acceptance=acceptance is None,
            terms_version=CURRENT_TERMS_VERSION,
            dpa_version=CURRENT_DPA_VERSION,
            privacy_version=CURRENT_PRIVACY_VERSION,
            accepted_at=acceptance.accepted_at if acceptance else None,
        )

    async def accept(
        self,
        organization_id: int,
        actor: Actor,
        command: schemas.LegalAcceptanceCreate,
    ) -> schemas.LegalAcceptanceRead:
        if actor.organization_id != organization_id:
            raise LegalAcceptanceTenantError(
                "O ator autenticado não pertence à organização indicada."
            )
        if not actor.can_admin:
            raise LegalAcceptanceAuthorityError("A aceitação exige capacidade de administrador.")
        if (
            command.terms_version != CURRENT_TERMS_VERSION
            or command.dpa_version != CURRENT_DPA_VERSION
            or command.privacy_version != CURRENT_PRIVACY_VERSION
        ):
            raise LegalDocumentVersionStaleError(
                "As versões dos documentos já não são atuais. Atualize a página e tente novamente."
            )

        # Lock the organization to make the idempotent check safe under concurrent submissions.
        organization = await self.db.scalar(
            select(models.Organization)
            .where(models.Organization.id == organization_id)
            .with_for_update()
        )
        if organization is None:
            raise LegalAcceptanceError("Organização não encontrada.")

        existing = await self.db.scalar(
            select(models.OrganizationLegalAcceptance).where(
                models.OrganizationLegalAcceptance.organization_id == organization_id,
                models.OrganizationLegalAcceptance.terms_version == CURRENT_TERMS_VERSION,
                models.OrganizationLegalAcceptance.dpa_version == CURRENT_DPA_VERSION,
                models.OrganizationLegalAcceptance.privacy_version == CURRENT_PRIVACY_VERSION,
            )
        )
        if existing is not None:
            return schemas.LegalAcceptanceRead.model_validate(existing)

        acceptance = models.OrganizationLegalAcceptance(
            organization_id=organization_id,
            accepted_by_membership_id_snapshot=actor.membership_id,
            authority_confirmed=True,
            terms_version=CURRENT_TERMS_VERSION,
            dpa_version=CURRENT_DPA_VERSION,
            privacy_version=CURRENT_PRIVACY_VERSION,
        )
        self.db.add(acceptance)
        await self.db.flush()
        await self.db.refresh(acceptance)
        return schemas.LegalAcceptanceRead.model_validate(acceptance)
