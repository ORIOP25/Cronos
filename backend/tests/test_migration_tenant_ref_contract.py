import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, MetaData, Table


pytestmark = pytest.mark.unit

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260705_beta_baseline.py"
)
spec = importlib.util.spec_from_file_location("beta_baseline_migration", MIGRATION_PATH)
assert spec is not None
assert spec.loader is not None
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def test_same_tenant_refs_match_model_metadata():
    assert migration._tenant_ref_contract_errors() == []


def test_same_tenant_ref_contract_reports_all_errors():
    metadata = MetaData()
    Table(
        "source",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("organization_id", Integer),
        Column("valid_ref_id", Integer),
        Column("missing_ref_id", Integer),
        Column("missing_id_ref", Integer),
        Column("missing_org_ref", Integer),
    )
    Table(
        "target",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("organization_id", Integer),
    )
    Table("target_without_id", metadata, Column("organization_id", Integer))
    Table("target_without_org", metadata, Column("id", Integer, primary_key=True))

    errors = migration._tenant_ref_contract_errors(
        refs={
            "missing_source": {"valid_ref_id": "target"},
            "source": {
                "valid_ref_id": "target",
                "stale_local_id": "target",
                "missing_ref_id": "missing_target",
                "missing_id_ref": "target_without_id",
                "missing_org_ref": "target_without_org",
            },
        },
        metadata=metadata,
    )

    assert errors == [
        "SAME_TENANT_REFS references missing local table public.missing_source",
        "SAME_TENANT_REFS[source].stale_local_id is not a column on public.source",
        "SAME_TENANT_REFS[source].missing_ref_id references missing table public.missing_target",
        "SAME_TENANT_REFS[source].missing_id_ref references public.target_without_id without an id column",
        "SAME_TENANT_REFS[source].missing_org_ref references public.target_without_org without an organization_id column",
    ]
