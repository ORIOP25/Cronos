"""Contract for the additive and final 0006_room_types migration."""

import pytest
from sqlalchemy import inspect, text

from alembic import command
from scripts import audit_database_integrity
from tests._support.db_fixtures import _alembic_config, sync_test_engine

pytestmark = pytest.mark.postgresql

PREVIOUS_REVISION = "0005_teacher_presence"

ENUM_TO_NAME = {
    "normal": "Normal",
    "lab": "Laboratório",
    "gym": "Ginásio",
    "art": "Artes",
}


def _insert_school(connection, marker: str) -> int:
    organization_id = connection.execute(
        text(
            "INSERT INTO public.organization(name, clerk_org_id, plan_status) "
            "VALUES (:name, :clerk_org_id, 'active') RETURNING id"
        ),
        {"name": f"Org {marker}", "clerk_org_id": f"org-{marker}"},
    ).scalar_one()
    for room_type in ENUM_TO_NAME:
        connection.execute(
            text(
                "INSERT INTO public.room(name, capacity, type, organization_id, is_archived) "
                f"VALUES (:name, 30, '{room_type}', :organization_id, false)"
            ),
            {"name": f"Sala {room_type}", "organization_id": organization_id},
        )
        connection.execute(
            text(
                "INSERT INTO public.subject(name, required_room_type, organization_id, is_archived) "
                f"VALUES (:name, '{room_type}', :organization_id, false)"
            ),
            {"name": f"Disc {room_type}", "organization_id": organization_id},
        )
    return organization_id


def _type_names(connection, organization_id: int) -> dict[str, str]:
    rows = connection.execute(
        text(
            "SELECT name, is_normal FROM public.room_type WHERE organization_id = :organization_id"
        ),
        {"organization_id": organization_id},
    ).all()
    return {name: is_normal for name, is_normal in rows}


def _room_type_by_object(connection, table: str, organization_id: int) -> dict:
    rows = connection.execute(
        text(
            f"SELECT o.name, rt.name FROM public.{table} o "
            f"JOIN public.room_type rt ON rt.id = o.room_type_id "
            "WHERE o.organization_id = :organization_id"
        ),
        {"organization_id": organization_id},
    ).all()
    return {name: type_name for name, type_name in rows}


def test_models_match_the_migrated_schema(clean_database):
    config = _alembic_config()
    command.upgrade(config, "head")
    command.check(config)


def test_upgrade_backfills_room_and_subject_types_for_every_school(clean_database):
    config = _alembic_config()
    try:
        command.downgrade(config, PREVIOUS_REVISION)
        with sync_test_engine.begin() as connection:
            first = _insert_school(connection, "room-type-a")
            second = _insert_school(connection, "room-type-b")

        command.upgrade(config, "head")

        with sync_test_engine.connect() as connection:
            for organization_id in (first, second):
                types = _type_names(connection, organization_id)
                assert set(types) == set(ENUM_TO_NAME.values())
                assert [name for name, is_normal in types.items() if is_normal] == ["Normal"]
                assert _room_type_by_object(connection, "room", organization_id) == {
                    f"Sala {code}": name for code, name in ENUM_TO_NAME.items()
                }
                assert _room_type_by_object(connection, "subject", organization_id) == {
                    f"Disc {code}": name for code, name in ENUM_TO_NAME.items()
                }

        command.downgrade(config, PREVIOUS_REVISION)
        with sync_test_engine.connect() as connection:
            for organization_id in (first, second):
                assert dict(
                    connection.execute(
                        text(
                            "SELECT name, type::text FROM public.room "
                            "WHERE organization_id = :organization_id"
                        ),
                        {"organization_id": organization_id},
                    ).all()
                ) == {f"Sala {code}": code for code in ENUM_TO_NAME}
                assert dict(
                    connection.execute(
                        text(
                            "SELECT name, required_room_type::text FROM public.subject "
                            "WHERE organization_id = :organization_id"
                        ),
                        {"organization_id": organization_id},
                    ).all()
                ) == {f"Disc {code}": code for code in ENUM_TO_NAME}

        command.upgrade(config, "head")
        with sync_test_engine.connect() as connection:
            for organization_id in (first, second):
                assert _room_type_by_object(connection, "room", organization_id) == {
                    f"Sala {code}": name for code, name in ENUM_TO_NAME.items()
                }
                assert _room_type_by_object(connection, "subject", organization_id) == {
                    f"Disc {code}": name for code, name in ENUM_TO_NAME.items()
                }
    finally:
        command.upgrade(config, "head")


def test_migration_creates_types_for_a_school_without_foundation(clean_database):
    config = _alembic_config()
    try:
        command.downgrade(config, PREVIOUS_REVISION)
        with sync_test_engine.begin() as connection:
            organization_id = connection.execute(
                text(
                    "INSERT INTO public.organization(name, clerk_org_id, plan_status, foundation_status) "
                    "VALUES ('Sem Fundação', 'org-no-foundation', 'active', 'NOT_STARTED') RETURNING id"
                )
            ).scalar_one()

        command.upgrade(config, "head")

        with sync_test_engine.connect() as connection:
            assert set(_type_names(connection, organization_id)) == set(ENUM_TO_NAME.values())
    finally:
        command.upgrade(config, "head")


def test_downgrade_restores_the_legacy_columns(clean_database):
    config = _alembic_config()
    try:
        with sync_test_engine.connect() as connection:
            inspector = inspect(connection)
            assert "room_type" in inspector.get_table_names()
            assert {column["name"] for column in inspector.get_columns("room")} >= {"room_type_id"}
            assert {column["name"] for column in inspector.get_columns("subject")} >= {
                "room_type_id"
            }

        command.downgrade(config, PREVIOUS_REVISION)

        with sync_test_engine.connect() as connection:
            inspector = inspect(connection)
            assert "room_type" not in inspector.get_table_names()
            assert "room_type_id" not in {
                column["name"] for column in inspector.get_columns("room")
            }
            assert "room_type_id" not in {
                column["name"] for column in inspector.get_columns("subject")
            }
            assert "type" in {column["name"] for column in inspector.get_columns("room")}
            assert "required_room_type" in {
                column["name"] for column in inspector.get_columns("subject")
            }
    finally:
        command.upgrade(config, "head")


def test_room_type_matches_the_tenant_contract(clean_database):
    with sync_test_engine.connect() as connection:
        inspector = inspect(connection)

        assert inspector.get_pk_constraint("room_type")["constrained_columns"] == ["id"]
        unique_columns = {
            constraint["name"]: tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("room_type")
        }
        assert unique_columns["uq_room_type_org_id"] == ("organization_id", "id")

        index_names = {index["name"] for index in inspector.get_indexes("room_type")}
        assert {"uq_room_type_org_name", "uq_room_type_org_normal"} <= index_names

        room_fks = {
            (tuple(fk["constrained_columns"]), fk["referred_table"], tuple(fk["referred_columns"]))
            for fk in inspector.get_foreign_keys("room")
        }
        assert (
            ("organization_id", "room_type_id"),
            "room_type",
            ("organization_id", "id"),
        ) in room_fks
        subject_fks = {
            (tuple(fk["constrained_columns"]), fk["referred_table"], tuple(fk["referred_columns"]))
            for fk in inspector.get_foreign_keys("subject")
        }
        assert (
            ("organization_id", "room_type_id"),
            "room_type",
            ("organization_id", "id"),
        ) in subject_fks

        room_columns = {column["name"]: column for column in inspector.get_columns("room")}
        subject_columns = {column["name"]: column for column in inspector.get_columns("subject")}
        assert room_columns["room_type_id"]["nullable"] is False
        assert subject_columns["room_type_id"]["nullable"] is False
        assert "type" not in room_columns
        assert "required_room_type" not in subject_columns

        rowsecurity = connection.execute(
            text(
                "SELECT c.relrowsecurity, c.relforcerowsecurity FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relname = 'room_type'"
            )
        ).one()
        assert rowsecurity == (True, True)
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM pg_policies WHERE schemaname = 'public' "
                    "AND tablename = 'room_type' AND policyname = 'tenant_isolation'"
                )
            )
            == 1
        )
        grants = connection.execute(
            text(
                "SELECT has_table_privilege('cronos_app', 'public.room_type', 'SELECT'), "
                "has_table_privilege('cronos_app', 'public.room_type', 'INSERT'), "
                "has_table_privilege('cronos_app', 'public.room_type', 'DELETE'), "
                "has_table_privilege('cronos_app', 'public.room_type', 'UPDATE')"
            )
        ).one()
        assert grants == (True, True, True, True)
        assert (
            connection.scalar(
                text(
                    "SELECT has_sequence_privilege('cronos_app', "
                    "'public.room_type_id_seq', 'USAGE')"
                )
            )
            is True
        )


def test_integrity_audit_accepts_the_migrated_test_database(clean_database):
    with sync_test_engine.connect() as connection:
        errors = audit_database_integrity._audit_connection(connection)
    assert errors == []
