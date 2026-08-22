import os
import re
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import text

from alembic import command
from tests.conftest import runtime_sync_test_engine

pytestmark = pytest.mark.postgresql


def _alembic_config() -> Config:
    backend_root = os.path.dirname(os.path.dirname(__file__))
    return Config(os.path.join(backend_root, "alembic.ini"))


def test_foundation_migration_does_not_backfill_or_publish_legacy_wrapper():
    source = (
        (Path(__file__).parents[1] / "alembic" / "versions" / "0004_foundation_telemetry.py")
        .read_text(encoding="utf-8")
        .lower()
    )

    assert "backfill" not in source
    assert (
        "create or replace function app_security.bootstrap_founder"
        not in source.split("def downgrade", 1)[0]
    )
    assert "create or replace function app_security.bootstrap_organization_admin" in source


def test_head_exposes_only_the_canonical_bootstrap_function(clean_database):
    command.upgrade(_alembic_config(), "head")
    marker = uuid.uuid4().hex[:8]
    with runtime_sync_test_engine.connect() as conn:
        old_function = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'app_security' AND p.proname = 'bootstrap_founder'
                """
            )
        ).scalar_one()
        canonical_function = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'app_security' AND p.proname = 'bootstrap_organization_admin'
                """
            )
        ).scalar_one()

        assert old_function == 0
        assert canonical_function == 1
        assert marker


def test_bootstrap_membership_audit_uses_membership_ids(clean_database):
    source = (
        (
            Path(__file__).parents[1]
            / "alembic"
            / "versions"
            / "0006_fix_bootstrap_membership_audit.py"
        )
        .read_text(encoding="utf-8")
        .lower()
    )
    normalized_source = re.sub(r"\s+", " ", source)

    assert "requested_membership_id, null, null" in normalized_source
    assert (
        "set created_by_membership_id = v_member, updated_by_membership_id = v_member"
        in normalized_source
    )
