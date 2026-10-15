"""Focused contract for the 0002_class_subject_modules migration.

Each test returns the schema to ``head`` in a ``finally`` block so a failure
never leaves the shared test database on an intermediate revision.
"""

import pytest
from sqlalchemy import inspect, text

from alembic import command
from tests._support.db_fixtures import _alembic_config, sync_test_engine

pytestmark = pytest.mark.postgresql

BASELINE_REVISION = "0001_scheduler_v1_baseline"
SELECTION_TABLE = "class_subject_module"


def _seed_link_with_two_modules(connection, marker: str) -> tuple[int, int, list[int]]:
    organization_id = connection.execute(
        text(
            "INSERT INTO public.organization(name, clerk_org_id, plan_status) "
            "VALUES (:name, :clerk_org_id, 'active') RETURNING id"
        ),
        {"name": f"Org {marker}", "clerk_org_id": f"org-{marker}"},
    ).scalar_one()
    course_id = connection.execute(
        text(
            "INSERT INTO public.course(name, abbreviation, organization_id, is_archived) "
            "VALUES ('Course', :abbreviation, :organization_id, false) RETURNING id"
        ),
        {"abbreviation": marker.upper()[:10], "organization_id": organization_id},
    ).scalar_one()
    subject_id = connection.execute(
        text(
            "INSERT INTO public.subject(name, required_room_type, organization_id, is_archived) "
            "VALUES ('Subject', 'normal', :organization_id, false) RETURNING id"
        ),
        {"organization_id": organization_id},
    ).scalar_one()
    class_id = connection.execute(
        text(
            "INSERT INTO public.class("
            "name, size, start_year, end_year, grade_level, is_archived, course_id, organization_id"
            ") VALUES ('A', 20, 2026, 2029, 10, false, :course_id, :organization_id) RETURNING id"
        ),
        {"course_id": course_id, "organization_id": organization_id},
    ).scalar_one()
    module_ids = [
        connection.execute(
            text(
                "INSERT INTO public.module("
                'organization_id, name, required_minutes, "order", subject_id'
                ") VALUES (:organization_id, :name, 50, :order, :subject_id) RETURNING id"
            ),
            {
                "organization_id": organization_id,
                "name": f"Module {order}",
                "order": order,
                "subject_id": subject_id,
            },
        ).scalar_one()
        for order in (0, 1)
    ]
    link_id = connection.execute(
        text(
            "INSERT INTO public.class_subject_link("
            "organization_id, class_id, subject_id, grade_level"
            ") VALUES (:organization_id, :class_id, :subject_id, 10) RETURNING id"
        ),
        {"organization_id": organization_id, "class_id": class_id, "subject_id": subject_id},
    ).scalar_one()
    return organization_id, link_id, module_ids


def test_upgrade_backfills_every_module_for_existing_links(clean_database):
    config = _alembic_config()
    try:
        command.downgrade(config, BASELINE_REVISION)
        with sync_test_engine.begin() as connection:
            organization_id, link_id, module_ids = _seed_link_with_two_modules(connection, "d04")

        command.upgrade(config, "head")

        with sync_test_engine.connect() as connection:
            selected = (
                connection.execute(
                    text(
                        "SELECT module_id FROM public.class_subject_module "
                        "WHERE organization_id = :organization_id "
                        "AND class_subject_link_id = :link_id ORDER BY module_id"
                    ),
                    {"organization_id": organization_id, "link_id": link_id},
                )
                .scalars()
                .all()
            )
        assert selected == module_ids
    finally:
        command.upgrade(config, "head")


def test_downgrade_removes_the_selection_table_and_planned_column(clean_database):
    config = _alembic_config()
    try:
        with sync_test_engine.connect() as connection:
            inspector = inspect(connection)
            assert SELECTION_TABLE in inspector.get_table_names()
            assert "planned" in {
                column["name"] for column in inspector.get_columns("curricular_requirement")
            }

        command.downgrade(config, BASELINE_REVISION)

        with sync_test_engine.connect() as connection:
            inspector = inspect(connection)
            assert SELECTION_TABLE not in inspector.get_table_names()
            assert "planned" not in {
                column["name"] for column in inspector.get_columns("curricular_requirement")
            }
    finally:
        command.upgrade(config, "head")


def test_selection_table_matches_the_tenant_contract(clean_database):
    with sync_test_engine.connect() as connection:
        inspector = inspect(connection)

        assert inspector.get_pk_constraint(SELECTION_TABLE)["constrained_columns"] == [
            "organization_id",
            "class_subject_link_id",
            "module_id",
        ]
        foreign_keys = {
            (
                tuple(foreign_key["constrained_columns"]),
                foreign_key["referred_table"],
                tuple(foreign_key["referred_columns"]),
            )
            for foreign_key in inspector.get_foreign_keys(SELECTION_TABLE)
        }
        assert foreign_keys == {
            (("organization_id",), "organization", ("id",)),
            (
                ("organization_id", "class_subject_link_id"),
                "class_subject_link",
                ("organization_id", "id"),
            ),
            (("organization_id", "module_id"), "module", ("organization_id", "id")),
        }
        assert {
            tuple(index["column_names"]) for index in inspector.get_indexes(SELECTION_TABLE)
        } == {("organization_id",), ("organization_id", "module_id")}

        rowsecurity = connection.execute(
            text(
                "SELECT c.relrowsecurity, c.relforcerowsecurity FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relname = :table"
            ),
            {"table": SELECTION_TABLE},
        ).one()
        assert rowsecurity == (True, True)
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM pg_policies WHERE schemaname = 'public' "
                    "AND tablename = :table AND policyname = 'tenant_isolation'"
                ),
                {"table": SELECTION_TABLE},
            )
            == 1
        )
        grants = connection.execute(
            text(
                "SELECT has_table_privilege('cronos_app', 'public.class_subject_module', 'SELECT'), "
                "has_table_privilege('cronos_app', 'public.class_subject_module', 'INSERT'), "
                "has_table_privilege('cronos_app', 'public.class_subject_module', 'DELETE'), "
                "has_table_privilege('cronos_app', 'public.class_subject_module', 'UPDATE')"
            )
        ).one()
        assert grants == (True, True, True, False)

        planned = {
            column["name"]: column for column in inspector.get_columns("curricular_requirement")
        }["planned"]
        assert planned["nullable"] is False
        assert (planned["default"] or "").lower() == "true"
