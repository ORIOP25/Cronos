from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app import schemas
from app.core.auth import Actor
from app.legal import CURRENT_DPA_VERSION, CURRENT_TERMS_VERSION
from app.models import LessonOccurrenceStatus
from app.services.legal_acceptance_service import (
    LegalAcceptanceService,
    LegalAcceptanceTenantError,
    LegalDocumentVersionStaleError,
)
from scripts import privacy


def test_privacy_registry_classifies_every_tenant_table():
    privacy.validate_privacy_table_registry()


@pytest.mark.asyncio
async def test_privacy_erase_requires_provider_confirmation_before_database_access():
    with pytest.raises(ValueError, match="provider-deleted"):
        await privacy._erase(1, "org", execute=True, provider_deleted=False)


def test_occurrence_commands_reject_free_text_reasons():
    with pytest.raises(ValidationError):
        schemas.LessonOccurrenceCreate(active_schedule_block_id=1, reason="texto")
    with pytest.raises(ValidationError):
        schemas.LessonOccurrenceUpdate(status=LessonOccurrenceStatus.GAP, version=1, reason="texto")
    with pytest.raises(ValidationError):
        schemas.LessonOccurrenceCancel(version=1, reason="texto")


def test_legal_acceptance_requires_three_explicit_confirmations():
    payload = {
        "controller_legal_name": "Entidade Teste",
        "controller_registration_number": "999999990",
        "controller_registered_address": "Rua de Teste, 1",
        "controller_contact_email": "legal@test.com",
        "representative_name": "Representante",
        "representative_role": "Administrador",
        "authority_confirmed": True,
        "terms_version": "2026-01",
        "dpa_version": "2026-01",
    }
    with pytest.raises(ValidationError):
        schemas.LegalAcceptanceCreate(**payload)
    accepted = schemas.LegalAcceptanceCreate(
        **payload,
        terms_accepted=True,
        dpa_accepted=True,
    )
    assert accepted.terms_accepted is True
    assert accepted.dpa_accepted is True


def _accepted_legal_command(**overrides):
    payload = {
        "controller_legal_name": "Entidade Teste",
        "controller_registration_number": "999999990",
        "controller_registered_address": "Rua de Teste, 1",
        "controller_contact_email": "legal@test.com",
        "representative_name": "Representante",
        "representative_role": "Administrador",
        "authority_confirmed": True,
        "terms_accepted": True,
        "dpa_accepted": True,
        "terms_version": CURRENT_TERMS_VERSION,
        "dpa_version": CURRENT_DPA_VERSION,
        **overrides,
    }
    return schemas.LegalAcceptanceCreate(**payload)


def _admin_actor(organization_id: int) -> Actor:
    return Actor(
        account_id=1,
        clerk_user_id="user-test",
        organization_id=organization_id,
        membership_id=1,
        can_admin=True,
        can_teach=False,
        teacher_id=None,
    )


@pytest.mark.asyncio
async def test_legal_acceptance_rejects_stale_document_version():
    with pytest.raises(LegalDocumentVersionStaleError) as error:
        await LegalAcceptanceService(AsyncMock()).accept(
            1,
            _admin_actor(1),
            _accepted_legal_command(terms_version="2025-12"),
        )

    assert error.value.code == "LEGAL_DOCUMENT_VERSION_STALE"


@pytest.mark.asyncio
async def test_legal_acceptance_rejects_a_different_tenant_before_database_access():
    with pytest.raises(LegalAcceptanceTenantError) as error:
        await LegalAcceptanceService(AsyncMock()).accept(
            1,
            _admin_actor(2),
            _accepted_legal_command(),
        )

    assert error.value.code == "LEGAL_ACCEPTANCE_TENANT_MISMATCH"
