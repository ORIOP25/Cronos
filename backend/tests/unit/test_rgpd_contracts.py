import pytest
from pydantic import ValidationError

from app import schemas
from app.models import LessonOccurrenceStatus
from scripts import privacy


def test_privacy_registry_classifies_every_tenant_table():
    privacy.validate_privacy_table_registry()


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
