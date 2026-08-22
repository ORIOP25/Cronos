import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app import models
from tests.conftest import runtime_sync_test_engine, sync_test_engine

pytestmark = pytest.mark.postgresql


def test_organization_model_foundation_fields(clean_database):
    with runtime_sync_test_engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.current_organization_id', '1', true)"))
        assert hasattr(models.Organization, "foundation_status")
        assert hasattr(models.Organization, "foundation_completed_at")
        assert hasattr(models.Organization, "first_real_schedule_approved_at")


def test_organization_foundation_draft_model(clean_database):
    with runtime_sync_test_engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.current_organization_id', '1', true)"))
        assert hasattr(models, "OrganizationFoundationDraft")
        assert hasattr(models.OrganizationFoundationDraft, "organization_id")
        assert hasattr(models.OrganizationFoundationDraft, "version")
        assert hasattr(models.OrganizationFoundationDraft, "current_step")
        assert hasattr(models.OrganizationFoundationDraft, "payload_json")
        assert hasattr(models.OrganizationFoundationDraft, "updated_by_membership_id")


def test_tutorial_telemetry_event_model(clean_database):
    with runtime_sync_test_engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.current_organization_id', '1', true)"))
        assert hasattr(models, "TutorialTelemetryEvent")
        assert hasattr(models.TutorialTelemetryEvent, "tutorial_run_id")
        assert hasattr(models.TutorialTelemetryEvent, "client_event_id")
        assert hasattr(models.TutorialTelemetryEvent, "event_name")
        assert hasattr(models.TutorialTelemetryEvent, "tutorial_version")


def test_monotonic_foundation_trigger_prevents_reopening(clean_database):
    with sync_test_engine.connect() as conn:
        res = conn.execute(
            text(
                "INSERT INTO organization(name, clerk_org_id, plan_status, foundation_status, foundation_completed_at) "
                "VALUES ('Test Monotonic Org', 'org_mono_1', 'active', 'COMPLETED', CURRENT_TIMESTAMP) RETURNING id"
            )
        ).scalar_one()
        conn.commit()

        # Cannot revert to IN_PROGRESS
        with pytest.raises(DBAPIError) as exc_info:
            conn.execute(
                text("UPDATE organization SET foundation_status = 'IN_PROGRESS' WHERE id = :id"),
                {"id": res},
            )
            conn.commit()
        assert (
            "monotonic" in str(exc_info.value).lower()
            or "foundation" in str(exc_info.value).lower()
        )
        conn.rollback()

        # Cannot revert to NOT_STARTED
        with pytest.raises(DBAPIError):
            conn.execute(
                text("UPDATE organization SET foundation_status = 'NOT_STARTED' WHERE id = :id"),
                {"id": res},
            )
            conn.commit()
        conn.rollback()


def test_monotonic_foundation_trigger_prevents_altering_timestamps(clean_database):
    with sync_test_engine.connect() as conn:
        org_id = conn.execute(
            text(
                "INSERT INTO organization(name, clerk_org_id, plan_status, foundation_status, foundation_completed_at, first_real_schedule_approved_at) "
                "VALUES ('Test Timestamps Org', 'org_mono_2', 'active', 'COMPLETED', '2026-08-20 10:00:00+00', '2026-08-20 11:00:00+00') RETURNING id"
            )
        ).scalar_one()
        conn.commit()

        # Cannot delete foundation_completed_at
        with pytest.raises(DBAPIError):
            conn.execute(
                text("UPDATE organization SET foundation_completed_at = NULL WHERE id = :id"),
                {"id": org_id},
            )
            conn.commit()
        conn.rollback()

        # Cannot alter foundation_completed_at
        with pytest.raises(DBAPIError):
            conn.execute(
                text(
                    "UPDATE organization SET foundation_completed_at = '2026-08-21 10:00:00+00' WHERE id = :id"
                ),
                {"id": org_id},
            )
            conn.commit()
        conn.rollback()

        # Cannot delete first_real_schedule_approved_at
        with pytest.raises(DBAPIError):
            conn.execute(
                text(
                    "UPDATE organization SET first_real_schedule_approved_at = NULL WHERE id = :id"
                ),
                {"id": org_id},
            )
            conn.commit()
        conn.rollback()

        # Cannot alter first_real_schedule_approved_at
        with pytest.raises(DBAPIError):
            conn.execute(
                text(
                    "UPDATE organization SET first_real_schedule_approved_at = '2026-08-21 11:00:00+00' WHERE id = :id"
                ),
                {"id": org_id},
            )
            conn.commit()
        conn.rollback()


def test_organization_foundation_invariants_and_deletion(clean_database):
    with sync_test_engine.connect() as conn:
        # INSERT COMPLETED without foundation_completed_at fails
        with pytest.raises(DBAPIError):
            conn.execute(
                text(
                    "INSERT INTO organization(name, clerk_org_id, plan_status, foundation_status, foundation_completed_at) "
                    "VALUES ('Invalid Completed Org', 'org_inv_1', 'active', 'COMPLETED', NULL)"
                )
            )
            conn.commit()
        conn.rollback()

        # INSERT with first_real_schedule_approved_at and incomplete foundation fails
        with pytest.raises(DBAPIError):
            conn.execute(
                text(
                    "INSERT INTO organization(name, clerk_org_id, plan_status, foundation_status, first_real_schedule_approved_at) "
                    "VALUES ('Invalid Approved Org', 'org_inv_2', 'active', 'IN_PROGRESS', CURRENT_TIMESTAMP)"
                )
            )
            conn.commit()
        conn.rollback()

        # DELETE of NOT_STARTED org removes row
        not_started_id = conn.execute(
            text(
                "INSERT INTO organization(name, clerk_org_id, plan_status, foundation_status) "
                "VALUES ('Delete Me Org', 'org_del_1', 'active', 'NOT_STARTED') RETURNING id"
            )
        ).scalar_one()
        conn.commit()

        conn.execute(text("DELETE FROM organization WHERE id = :id"), {"id": not_started_id})
        conn.commit()
        assert (
            conn.execute(
                text("SELECT COUNT(*) FROM organization WHERE id = :id"), {"id": not_started_id}
            ).scalar_one()
            == 0
        )

        # DELETE of COMPLETED org fails
        completed_id = conn.execute(
            text(
                "INSERT INTO organization(name, clerk_org_id, plan_status, foundation_status, foundation_completed_at) "
                "VALUES ('Completed Org', 'org_del_2', 'active', 'COMPLETED', CURRENT_TIMESTAMP) RETURNING id"
            )
        ).scalar_one()
        conn.commit()

        with pytest.raises(DBAPIError):
            conn.execute(text("DELETE FROM organization WHERE id = :id"), {"id": completed_id})
            conn.commit()
        conn.rollback()


def test_organization_foundation_draft_constraints_and_composite_fk(clean_database):
    org_marker1 = uuid.uuid4().hex[:8]
    org_marker2 = uuid.uuid4().hex[:8]
    with sync_test_engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO public."user" (
                    name, email, clerk_user_id, created_at, updated_at
                ) VALUES (
                    'Existing account', :email, :clerk_user_id,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "email": f"existing-{org_marker1}@example.test",
                "clerk_user_id": f"user-existing-{org_marker1}",
            },
        )
        conn.commit()
        p1 = (
            conn.execute(
                text(
                    """
                SELECT account_id, organization_id, membership_id FROM app_security.bootstrap_organization_admin(
                    :user_id, :org_id, :org_name, :email, :profile, :membership_id
                )
                """
                ),
                {
                    "user_id": f"user-{org_marker1}",
                    "org_id": f"org-{org_marker1}",
                    "org_name": f"Org Draft 1 {org_marker1}",
                    "email": f"draft1-{org_marker1}@example.test",
                    "profile": "Draft Admin 1",
                    "membership_id": f"mem-{org_marker1}",
                },
            )
            .mappings()
            .one()
        )
        p2 = (
            conn.execute(
                text(
                    """
                SELECT account_id, organization_id, membership_id FROM app_security.bootstrap_organization_admin(
                    :user_id, :org_id, :org_name, :email, :profile, :membership_id
                )
                """
                ),
                {
                    "user_id": f"user-{org_marker2}",
                    "org_id": f"org-{org_marker2}",
                    "org_name": f"Org Draft 2 {org_marker2}",
                    "email": f"draft2-{org_marker2}@example.test",
                    "profile": "Draft Admin 2",
                    "membership_id": f"mem-{org_marker2}",
                },
            )
            .mappings()
            .one()
        )
        conn.commit()

        audit = (
            conn.execute(
                text(
                    """
                SELECT id, account_id, created_by_membership_id, updated_by_membership_id
                FROM organization_membership
                WHERE id = :membership_id
                """
                ),
                {"membership_id": p1["membership_id"]},
            )
            .mappings()
            .one()
        )
        assert audit["account_id"] != audit["id"]
        assert audit["created_by_membership_id"] == audit["id"]
        assert audit["updated_by_membership_id"] == audit["id"]

        # 1. version = 0 fails
        with pytest.raises(DBAPIError):
            conn.execute(
                text(
                    """
                    INSERT INTO organization_foundation_draft (
                        organization_id, version, current_step, payload_json, updated_by_membership_id
                    ) VALUES (:org_id, 0, 1, '{}'::jsonb, :mem_id)
                    """
                ),
                {"org_id": p1["organization_id"], "mem_id": p1["membership_id"]},
            )
            conn.commit()
        conn.rollback()

        # 2. current_step = 0 fails
        with pytest.raises(DBAPIError):
            conn.execute(
                text(
                    """
                    INSERT INTO organization_foundation_draft (
                        organization_id, version, current_step, payload_json, updated_by_membership_id
                    ) VALUES (:org_id, 1, 0, '{}'::jsonb, :mem_id)
                    """
                ),
                {"org_id": p1["organization_id"], "mem_id": p1["membership_id"]},
            )
            conn.commit()
        conn.rollback()

        # 3. current_step = 10 fails
        with pytest.raises(DBAPIError):
            conn.execute(
                text(
                    """
                    INSERT INTO organization_foundation_draft (
                        organization_id, version, current_step, payload_json, updated_by_membership_id
                    ) VALUES (:org_id, 1, 10, '{}'::jsonb, :mem_id)
                    """
                ),
                {"org_id": p1["organization_id"], "mem_id": p1["membership_id"]},
            )
            conn.commit()
        conn.rollback()

        # 4. Membership of OTHER organization fails composite FK
        with pytest.raises(DBAPIError):
            conn.execute(
                text(
                    """
                    INSERT INTO organization_foundation_draft (
                        organization_id, version, current_step, payload_json, updated_by_membership_id
                    ) VALUES (:org_id, 1, 1, '{}'::jsonb, :mem_id)
                    """
                ),
                {"org_id": p1["organization_id"], "mem_id": p2["membership_id"]},
            )
            conn.commit()
        conn.rollback()

        # 5. Valid draft with own membership succeeds
        conn.execute(
            text(
                """
                INSERT INTO organization_foundation_draft (
                    organization_id, version, current_step, payload_json, updated_by_membership_id
                ) VALUES (:org_id, 1, 1, '{"school_start_date": "2025-09-15"}'::jsonb, :mem_id)
                """
            ),
            {"org_id": p1["organization_id"], "mem_id": p1["membership_id"]},
        )
        conn.commit()


def test_tutorial_telemetry_event_append_only_and_idempotency(clean_database):
    org_marker = uuid.uuid4().hex[:8]
    with runtime_sync_test_engine.connect() as conn:
        org_id = conn.execute(
            text(
                """
                SELECT organization_id FROM app_security.bootstrap_organization_admin(
                    :user_id, :org_id, :org_name, :email, :profile, :membership_id
                )
                """
            ),
            {
                "user_id": f"user-{org_marker}",
                "org_id": f"org-{org_marker}",
                "org_name": f"Org Telemetry {org_marker}",
                "email": f"telemetry-{org_marker}@example.test",
                "profile": "Telemetry Admin",
                "membership_id": f"mem-{org_marker}",
            },
        ).scalar_one()
        conn.commit()

        conn.execute(
            text("SELECT set_config('app.current_organization_id', :org, true)"),
            {"org": str(org_id)},
        )

        run_id = str(uuid.uuid4())
        client_event_id = str(uuid.uuid4())

        # Insert telemetry event
        conn.execute(
            text(
                """
                INSERT INTO tutorial_telemetry_event (
                    organization_id, tutorial_run_id, client_event_id, tutorial_version, event_name, chapter, step_id
                ) VALUES (
                    :org_id, :run_id, :client_event_id, 1, 'tutorial_opened', 1, 'structure_overview'
                )
                """
            ),
            {
                "org_id": org_id,
                "run_id": run_id,
                "client_event_id": client_event_id,
            },
        )
        conn.commit()

        # Duplicate (organization_id, client_event_id) violates uniqueness
        with pytest.raises(DBAPIError):
            conn.execute(
                text(
                    """
                    INSERT INTO tutorial_telemetry_event (
                        organization_id, tutorial_run_id, client_event_id, tutorial_version, event_name, chapter, step_id
                    ) VALUES (
                        :org_id, :run_id, :client_event_id, 1, 'tutorial_opened', 1, 'structure_overview'
                    )
                    """
                ),
                {
                    "org_id": org_id,
                    "run_id": run_id,
                    "client_event_id": client_event_id,
                },
            )
            conn.commit()
        conn.rollback()

        conn.execute(
            text("SELECT set_config('app.current_organization_id', :org, true)"),
            {"org": str(org_id)},
        )

        # UPDATE is prohibited for cronos_app
        with pytest.raises(DBAPIError):
            conn.execute(
                text(
                    "UPDATE tutorial_telemetry_event SET event_name = 'tutorial_completed' WHERE client_event_id = :ceid"
                ),
                {"ceid": client_event_id},
            )
            conn.commit()
        conn.rollback()

        conn.execute(
            text("SELECT set_config('app.current_organization_id', :org, true)"),
            {"org": str(org_id)},
        )

        # DELETE is prohibited for cronos_app
        with pytest.raises(DBAPIError):
            conn.execute(
                text("DELETE FROM tutorial_telemetry_event WHERE client_event_id = :ceid"),
                {"ceid": client_event_id},
            )
            conn.commit()
        conn.rollback()
