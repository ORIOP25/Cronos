import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.legal import CURRENT_DPA_VERSION, CURRENT_TERMS_VERSION
from tests._support.db_fixtures import sync_test_engine

pytestmark = pytest.mark.postgresql


def _insert_acceptance(connection, organization_id: int, membership_id: int) -> int:
    return connection.execute(
        text(
            """
            INSERT INTO organization_legal_acceptance (
                organization_id, accepted_by_membership_id_snapshot,
                controller_legal_name, controller_registration_number,
                controller_registered_address, controller_contact_email,
                representative_name, representative_role, authority_confirmed,
                terms_version, dpa_version
            ) VALUES (
                :organization_id, :membership_id, 'Entidade Teste', '999999990',
                'Rua de Teste, 1', 'legal@test.com', 'Representante',
                'Administrador', true, :terms_version, :dpa_version
            ) RETURNING id
            """
        ),
        {
            "organization_id": organization_id,
            "membership_id": membership_id,
            "terms_version": CURRENT_TERMS_VERSION,
            "dpa_version": CURRENT_DPA_VERSION,
        },
    ).scalar_one()


def test_legal_acceptance_is_append_only_and_unique(clean_database):
    marker = uuid.uuid4().hex
    with sync_test_engine.begin() as connection:
        organization_id = connection.execute(
            text(
                "INSERT INTO organization(name, clerk_org_id, plan_status) "
                "VALUES (:name, :clerk_org_id, 'active') RETURNING id"
            ),
            {"name": "Legal Contract", "clerk_org_id": f"legal-{marker}"},
        ).scalar_one()
        acceptance_id = _insert_acceptance(connection, organization_id, 101)

    with sync_test_engine.connect() as connection:
        with pytest.raises(DBAPIError, match="append-only"):
            connection.execute(
                text(
                    "UPDATE organization_legal_acceptance SET representative_role = 'Outro' WHERE id = :id"
                ),
                {"id": acceptance_id},
            )
        connection.rollback()
        with pytest.raises(DBAPIError, match="append-only"):
            connection.execute(
                text("DELETE FROM organization_legal_acceptance WHERE id = :id"),
                {"id": acceptance_id},
            )
        connection.rollback()

        with pytest.raises(IntegrityError):
            _insert_acceptance(connection, organization_id, 102)
        connection.rollback()
