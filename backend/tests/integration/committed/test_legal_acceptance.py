import pytest
from sqlalchemy import func, select

from app import models
from app.legal import CURRENT_DPA_VERSION, CURRENT_TERMS_VERSION
from tests._support.db_fixtures import create_org_and_user

pytestmark = pytest.mark.postgresql


def _acceptance_payload() -> dict[str, object]:
    return {
        "controller_legal_name": "Entidade Teste, ENI",
        "controller_registration_number": "999999990",
        "controller_registered_address": "Rua de Teste, 1, 1000-000 Lisboa",
        "controller_contact_email": "legal@test.com",
        "representative_name": "Representante Teste",
        "representative_role": "Administrador",
        "authority_confirmed": True,
        "terms_accepted": True,
        "dpa_accepted": True,
        "terms_version": CURRENT_TERMS_VERSION,
        "dpa_version": CURRENT_DPA_VERSION,
    }


async def test_legal_gate_requires_admin_acceptance_and_is_idempotent(async_client, db_session):
    _org, user = await create_org_and_user(
        db_session,
        clerk_user_id="legal_gate_admin",
        clerk_org_id="org_legal_gate_admin",
        legal_accepted=False,
    )
    await db_session.commit()
    headers = {"Authorization": f"Bearer test_{user.clerk_user_id}"}

    status_response = await async_client.get("/api/v1/legal/status", headers=headers)
    assert status_response.status_code == 200
    assert status_response.json()["requires_acceptance"] is True

    blocked_response = await async_client.get("/api/v1/classes/", headers=headers)
    assert blocked_response.status_code == 409
    assert blocked_response.json()["detail"]["code"] == "LEGAL_ACCEPTANCE_REQUIRED"

    accepted_response = await async_client.post(
        "/api/v1/legal/acceptance",
        headers=headers,
        json=_acceptance_payload(),
    )
    assert accepted_response.status_code == 200

    repeated_response = await async_client.post(
        "/api/v1/legal/acceptance",
        headers=headers,
        json=_acceptance_payload(),
    )
    assert repeated_response.status_code == 200
    assert repeated_response.json()["id"] == accepted_response.json()["id"]

    accepted_status = await async_client.get("/api/v1/legal/status", headers=headers)
    assert accepted_status.status_code == 200
    assert accepted_status.json()["accepted"] is True
    assert accepted_status.json()["requires_acceptance"] is False
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(models.OrganizationLegalAcceptance)
            .where(models.OrganizationLegalAcceptance.organization_id == _org.id)
        )
        == 1
    )


async def test_legal_acceptance_is_admin_only(async_client, db_session):
    _org, user = await create_org_and_user(
        db_session,
        clerk_user_id="legal_gate_teacher",
        clerk_org_id="org_legal_gate_teacher",
        role="teacher",
        legal_accepted=False,
    )
    await db_session.commit()

    response = await async_client.post(
        "/api/v1/legal/acceptance",
        headers={"Authorization": f"Bearer test_{user.clerk_user_id}"},
        json=_acceptance_payload(),
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "LEGAL_ACCEPTANCE_ADMIN_REQUIRED"
