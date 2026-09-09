import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.legal import CURRENT_DPA_VERSION, CURRENT_PRIVACY_VERSION, CURRENT_TERMS_VERSION
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
                terms_version, dpa_version, privacy_version
            ) VALUES (
                :organization_id, :membership_id, 'Entidade Teste', '999999990',
                'Rua de Teste, 1', 'legal@test.com', 'Representante',
                'Administrador', true, :terms_version, :dpa_version, :privacy_version
            ) RETURNING id
            """
        ),
        {
            "organization_id": organization_id,
            "membership_id": membership_id,
            "terms_version": CURRENT_TERMS_VERSION,
            "dpa_version": CURRENT_DPA_VERSION,
            "privacy_version": CURRENT_PRIVACY_VERSION,
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


def test_historical_acceptance_fields_remain_nullable_and_privacy_requires_new_evidence(clean_database):
    marker = uuid.uuid4().hex
    with sync_test_engine.begin() as connection:
        organization_id = connection.execute(
            text(
                "INSERT INTO organization(name, clerk_org_id, plan_status) "
                "VALUES ('Historical Legal Contract', :clerk_org_id, 'active') RETURNING id"
            ),
            {"clerk_org_id": f"legal-historical-{marker}"},
        ).scalar_one()
        historical_id = connection.execute(
            text(
                """
                INSERT INTO organization_legal_acceptance (
                    organization_id, accepted_by_membership_id_snapshot,
                    authority_confirmed, terms_version, dpa_version, privacy_version
                ) VALUES (:organization_id, 101, true, :terms_version, :dpa_version, NULL)
                RETURNING id
                """
            ),
            {
                "organization_id": organization_id,
                "terms_version": CURRENT_TERMS_VERSION,
                "dpa_version": CURRENT_DPA_VERSION,
            },
        ).scalar_one()
        historical = connection.execute(
            text(
                "SELECT controller_legal_name, privacy_version "
                "FROM organization_legal_acceptance WHERE id = :id"
            ),
            {"id": historical_id},
        ).one()
        assert historical == (None, None)

        current_id = connection.execute(
            text(
                """
                INSERT INTO organization_legal_acceptance (
                    organization_id, accepted_by_membership_id_snapshot,
                    authority_confirmed, terms_version, dpa_version, privacy_version
                ) VALUES (:organization_id, 102, true, :terms_version, :dpa_version, :privacy_version)
                RETURNING id
                """
            ),
            {
                "organization_id": organization_id,
                "terms_version": CURRENT_TERMS_VERSION,
                "dpa_version": CURRENT_DPA_VERSION,
                "privacy_version": CURRENT_PRIVACY_VERSION,
            },
        ).scalar_one()
        assert current_id != historical_id
