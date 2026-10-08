from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app import schemas
from app.core.auth import Actor
from app.legal import CURRENT_DPA_VERSION, CURRENT_PRIVACY_VERSION, CURRENT_TERMS_VERSION
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


@pytest.mark.asyncio
async def test_privacy_locked_erasure_refuses_active_jobs_before_deleting(monkeypatch):
    db = AsyncMock()
    db.scalar.return_value = SimpleNamespace(clerk_org_id="org_owned")
    monkeypatch.setattr(privacy, "active_jobs", AsyncMock(return_value=["v1:17"]))
    with pytest.raises(ValueError, match="active jobs"):
        await privacy._erase_locked(db, 1, "org_owned", execute=True, provider_deleted=True)
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_privacy_locked_erasure_requires_provider_confirmation(monkeypatch):
    db = AsyncMock()
    with pytest.raises(ValueError, match="provider-deleted"):
        await privacy._erase_locked(db, 1, "org_owned", execute=True, provider_deleted=False)
    db.execute.assert_not_awaited()


def test_occurrence_commands_reject_free_text_reasons():
    with pytest.raises(ValidationError):
        schemas.LessonOccurrenceCreate(active_schedule_block_id=1, reason="texto")
    with pytest.raises(ValidationError):
        schemas.LessonOccurrenceUpdate(status=LessonOccurrenceStatus.GAP, version=1, reason="texto")
    with pytest.raises(ValidationError):
        schemas.LessonOccurrenceCancel(version=1, reason="texto")


def test_legal_acceptance_requires_one_explicit_confirmation_and_versions():
    payload = {
        "acceptance_confirmed": True,
        "terms_version": "2026-01",
        "dpa_version": "2026-01",
        "privacy_version": "2026-01",
    }
    accepted = schemas.LegalAcceptanceCreate(**payload)
    assert accepted.acceptance_confirmed is True

    for field in ("acceptance_confirmed", "terms_version", "dpa_version", "privacy_version"):
        incomplete = {key: value for key, value in payload.items() if key != field}
        with pytest.raises(ValidationError):
            schemas.LegalAcceptanceCreate(**incomplete)

    with pytest.raises(ValidationError):
        schemas.LegalAcceptanceCreate(**payload, legacy_field="not accepted")
    with pytest.raises(ValidationError):
        schemas.LegalAcceptanceCreate(**{**payload, "acceptance_confirmed": False})


def test_legal_acceptance_rejects_legacy_fields():
    with pytest.raises(ValidationError):
        schemas.LegalAcceptanceCreate(
            acceptance_confirmed=True,
            terms_version=CURRENT_TERMS_VERSION,
            dpa_version=CURRENT_DPA_VERSION,
            privacy_version=CURRENT_PRIVACY_VERSION,
            terms_accepted=True,
        )


def _accepted_legal_command(**overrides):
    payload = {
        "acceptance_confirmed": True,
        "terms_version": CURRENT_TERMS_VERSION,
        "dpa_version": CURRENT_DPA_VERSION,
        "privacy_version": CURRENT_PRIVACY_VERSION,
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
