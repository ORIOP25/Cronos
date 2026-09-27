import os
import re
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import text

from alembic import command
from tests._support.db_fixtures import runtime_sync_test_engine

pytestmark = pytest.mark.postgresql

BASELINE = Path(__file__).parents[2] / "alembic" / "versions" / "0001_scheduler_v1_baseline.py"


def _alembic_config() -> Config:
    backend_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return Config(os.path.join(backend_root, "alembic.ini"))


def test_baseline_does_not_install_legacy_bootstrap_wrapper():
    source = BASELINE.read_text(encoding="utf-8").lower()

    assert "backfill" not in source
    assert "function app_security.bootstrap_founder" not in source
    assert "function app_security.bootstrap_organization_admin" in source


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


def test_baseline_owns_bootstrap_membership_audit():
    source = BASELINE.read_text(encoding="utf-8").lower()
    normalized_source = re.sub(r"\s+", " ", source)

    assert "requested_membership_id, null, null" in normalized_source
    assert (
        "set created_by_membership_id = v_member, updated_by_membership_id = v_member"
        in normalized_source
    )
