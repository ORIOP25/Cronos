"""Focused contract for the 0004_joint_lesson_groups migration.

Each test returns the schema to ``head`` in a ``finally`` block so a failure
never leaves the shared test database on an intermediate revision.
"""

import pytest
from sqlalchemy import inspect, text

from alembic import command
from scripts import audit_database_integrity, audit_triggers
from tests._support.db_fixtures import _alembic_config, sync_test_engine, test_engine

pytestmark = pytest.mark.postgresql

PREVIOUS_REVISION = "0003_class_availability"
TABLES = ("joint_lesson_group", "joint_lesson_group_member", "joint_lesson_group_module")


def _seed_lesson(
    connection,
    marker: str,
    *,
    room_type_schema: str,
    teaching_unit_key: str | None = None,
    siblings: bool = False,
) -> dict:
    organization_id = connection.execute(
        text(
            "INSERT INTO public.organization(name, clerk_org_id, plan_status) "
            "VALUES (:name, :clerk_org_id, 'active') RETURNING id"
        ),
        {"name": f"Org {marker}", "clerk_org_id": f"org-{marker}"},
    ).scalar_one()
    account_id = connection.execute(
        text(
            'INSERT INTO public."user"(email, name, created_at, updated_at) '
            "VALUES (:email, 'Admin', now(), now()) RETURNING id"
        ),
        {"email": f"{marker}@example.test"},
    ).scalar_one()
    membership_id = connection.execute(
        text(
            "INSERT INTO public.organization_membership("
            "organization_id, account_id, organization_display_name, lifecycle_status, "
            "access_status, teacher_access_mode, can_admin, can_teach, lock_version, "
            "created_at, updated_at"
            ") VALUES (:organization_id, :account_id, 'Admin', 'active', 'active', "
            "'platform', false, true, 0, now(), now()) RETURNING id"
        ),
        {"organization_id": organization_id, "account_id": account_id},
    ).scalar_one()
    teacher_id = connection.execute(
        text(
            "INSERT INTO public.teacher(organization_id, organization_membership_id) "
            "VALUES (:organization_id, :membership_id) RETURNING id"
        ),
        {"organization_id": organization_id, "membership_id": membership_id},
    ).scalar_one()
    course_id = connection.execute(
        text(
            "INSERT INTO public.course(name, abbreviation, organization_id, is_archived) "
            "VALUES ('Course', :abbreviation, :organization_id, false) RETURNING id"
        ),
        {"abbreviation": marker.upper()[:10], "organization_id": organization_id},
    ).scalar_one()
    if room_type_schema == "legacy":
        subject_id = connection.execute(
            text(
                "INSERT INTO public.subject(name, required_room_type, organization_id, is_archived) "
                "VALUES ('Subject', 'normal', :organization_id, false) RETURNING id"
            ),
            {"organization_id": organization_id},
        ).scalar_one()
        room_id = connection.execute(
            text(
                "INSERT INTO public.room(name, capacity, type, organization_id, is_archived) "
                "VALUES ('A1', 25, 'normal', :organization_id, false) RETURNING id"
            ),
            {"organization_id": organization_id},
        ).scalar_one()
    elif room_type_schema == "school":
        room_type_id = connection.execute(
            text(
                "INSERT INTO public.room_type(organization_id, name, is_normal, is_archived) "
                "VALUES (:organization_id, 'Normal', true, false) RETURNING id"
            ),
            {"organization_id": organization_id},
        ).scalar_one()
        subject_id = connection.execute(
            text(
                "INSERT INTO public.subject(name, room_type_id, organization_id, is_archived) "
                "VALUES ('Subject', :room_type_id, :organization_id, false) RETURNING id"
            ),
            {"organization_id": organization_id, "room_type_id": room_type_id},
        ).scalar_one()
        room_id = connection.execute(
            text(
                "INSERT INTO public.room(name, capacity, room_type_id, organization_id, is_archived) "
                "VALUES ('A1', 25, :room_type_id, :organization_id, false) RETURNING id"
            ),
            {"organization_id": organization_id, "room_type_id": room_type_id},
        ).scalar_one()
    else:
        raise ValueError(f"Unsupported room type schema: {room_type_schema}")
    year_id = connection.execute(
        text(
            "INSERT INTO public.scheduler_school_year("
            "organization_id, label, start_date, hard_end_date, timezone, is_active, "
            "created_at, updated_at"
            ") VALUES (:organization_id, '2026/2027', '2026-09-01', '2027-06-30', "
            "'Europe/Lisbon', true, now(), now()) RETURNING id"
        ),
        {"organization_id": organization_id},
    ).scalar_one()
    version_id = connection.execute(
        text(
            "INSERT INTO public.scheduler_version_v1("
            "organization_id, school_year_id, origin, status, snapshot_digest, created_at"
            ") VALUES (:organization_id, :year_id, 'generation:1', 'CANDIDATE', "
            ":digest, now()) RETURNING id"
        ),
        {"organization_id": organization_id, "year_id": year_id, "digest": "a" * 64},
    ).scalar_one()

    def _insert_class(name: str) -> int:
        return connection.execute(
            text(
                "INSERT INTO public.class("
                "name, size, start_year, end_year, grade_level, is_archived, course_id, "
                "organization_id"
                ") VALUES (:name, 20, 2026, 2029, 10, false, :course_id, :organization_id) "
                "RETURNING id"
            ),
            {"name": name, "course_id": course_id, "organization_id": organization_id},
        ).scalar_one()

    def _insert_assignment(class_id: int) -> int:
        return connection.execute(
            text(
                "INSERT INTO public.curricular_assignment("
                "organization_id, school_year_id, class_id, subject_id, teacher_id"
                ") VALUES (:organization_id, :year_id, :class_id, :subject_id, :teacher_id) "
                "RETURNING id"
            ),
            {
                "organization_id": organization_id,
                "year_id": year_id,
                "class_id": class_id,
                "subject_id": subject_id,
                "teacher_id": teacher_id,
            },
        ).scalar_one()

    columns = (
        "organization_id, school_year_id, version_id, assignment_id, stable_key, "
        "school_date, starts_at, ends_at, room_id, physical_minutes, credit_minutes"
    )
    values = (
        ":organization_id, :year_id, :version_id, :assignment_id, 'lesson:1', "
        "'2026-09-21', '2026-09-21 09:00+00', '2026-09-21 09:50+00', :room_id, 50, 50"
    )

    def _insert_lesson(assignment_id: int, key: str | None) -> None:
        params = {
            "organization_id": organization_id,
            "year_id": year_id,
            "version_id": version_id,
            "assignment_id": assignment_id,
            "room_id": room_id,
        }
        if key is None:
            connection.execute(
                text(f"INSERT INTO public.scheduler_lesson_v1({columns}) VALUES ({values})"),
                params,
            )
        else:
            connection.execute(
                text(
                    f"INSERT INTO public.scheduler_lesson_v1({columns}, teaching_unit_key) "
                    f"VALUES ({values}, :teaching_unit_key)"
                ),
                {**params, "teaching_unit_key": key},
            )

    first_class = _insert_class("A")
    assignment_id = _insert_assignment(first_class)
    if teaching_unit_key is None and not siblings:
        first_key = None
    else:
        first_key = teaching_unit_key or f"A:{assignment_id}"
    _insert_lesson(assignment_id, first_key)

    second_assignment_id = None
    if siblings:
        second_class = _insert_class("B")
        second_assignment_id = _insert_assignment(second_class)
        _insert_lesson(second_assignment_id, f"A:{second_assignment_id}")

    return {
        "organization_id": organization_id,
        "assignment_id": assignment_id,
        "second_assignment_id": second_assignment_id,
    }


def test_models_match_the_migrated_schema(clean_database):
    """``alembic check`` runs against the isolated test database, not a local one."""
    config = _alembic_config()
    command.upgrade(config, "head")
    command.check(config)


def test_upgrade_backfills_existing_lessons_with_the_assignment_unit(clean_database):
    config = _alembic_config()
    try:
        command.downgrade(config, PREVIOUS_REVISION)
        with sync_test_engine.begin() as connection:
            seed = _seed_lesson(connection, "joint-backfill", room_type_schema="legacy")

        command.upgrade(config, "head")

        with sync_test_engine.connect() as connection:
            key = connection.scalar(
                text(
                    "SELECT teaching_unit_key FROM public.scheduler_lesson_v1 "
                    "WHERE organization_id = :organization_id"
                ),
                {"organization_id": seed["organization_id"]},
            )
        assert key == f"A:{seed['assignment_id']}"
    finally:
        command.upgrade(config, "head")


def test_downgrade_removes_the_three_tables_and_the_unit_column(clean_database):
    config = _alembic_config()
    try:
        with sync_test_engine.connect() as connection:
            inspector = inspect(connection)
            for table in TABLES:
                assert table in inspector.get_table_names()
            assert "teaching_unit_key" in {
                column["name"] for column in inspector.get_columns("scheduler_lesson_v1")
            }

        command.downgrade(config, PREVIOUS_REVISION)

        with sync_test_engine.connect() as connection:
            inspector = inspect(connection)
            for table in TABLES:
                assert table not in inspector.get_table_names()
            assert "teaching_unit_key" not in {
                column["name"] for column in inspector.get_columns("scheduler_lesson_v1")
            }
    finally:
        command.upgrade(config, "head")


def test_downgrade_succeeds_for_a_single_joint_unit_without_siblings(clean_database):
    config = _alembic_config()
    try:
        with sync_test_engine.begin() as connection:
            _seed_lesson(
                connection,
                "joint-single",
                room_type_schema="school",
                teaching_unit_key="J:1:1",
            )

        command.downgrade(config, PREVIOUS_REVISION)

        with sync_test_engine.connect() as connection:
            inspector = inspect(connection)
            for table in TABLES:
                assert table not in inspector.get_table_names()
            assert "teaching_unit_key" not in {
                column["name"] for column in inspector.get_columns("scheduler_lesson_v1")
            }
    finally:
        command.upgrade(config, "head")


def test_downgrade_refuses_when_siblings_share_a_stable_key(clean_database):
    config = _alembic_config()
    try:
        with sync_test_engine.begin() as connection:
            _seed_lesson(connection, "joint-siblings", room_type_schema="school", siblings=True)

        with pytest.raises(RuntimeError, match="refused"):
            command.downgrade(config, PREVIOUS_REVISION)
    finally:
        command.upgrade(config, "head")


def test_joint_tables_match_the_tenant_contract(clean_database):
    with sync_test_engine.connect() as connection:
        inspector = inspect(connection)

        assert inspector.get_pk_constraint("joint_lesson_group")["constrained_columns"] == ["id"]
        assert inspector.get_pk_constraint("joint_lesson_group_member")["constrained_columns"] == [
            "organization_id",
            "class_subject_link_id",
        ]
        assert inspector.get_pk_constraint("joint_lesson_group_module")["constrained_columns"] == [
            "organization_id",
            "group_id",
            "module_id",
        ]

        group_fks = {
            (
                tuple(fk["constrained_columns"]),
                fk["referred_table"],
                tuple(fk["referred_columns"]),
            )
            for fk in inspector.get_foreign_keys("joint_lesson_group")
        }
        assert group_fks == {
            (("organization_id",), "organization", ("id",)),
            (("organization_id", "subject_id"), "subject", ("organization_id", "id")),
        }

        member_fks = {
            (
                tuple(fk["constrained_columns"]),
                fk["referred_table"],
                tuple(fk["referred_columns"]),
            )
            for fk in inspector.get_foreign_keys("joint_lesson_group_member")
        }
        assert member_fks == {
            (("organization_id",), "organization", ("id",)),
            (
                ("organization_id", "group_id"),
                "joint_lesson_group",
                ("organization_id", "id"),
            ),
            (
                ("organization_id", "class_subject_link_id"),
                "class_subject_link",
                ("organization_id", "id"),
            ),
        }

        module_fks = {
            (
                tuple(fk["constrained_columns"]),
                fk["referred_table"],
                tuple(fk["referred_columns"]),
            )
            for fk in inspector.get_foreign_keys("joint_lesson_group_module")
        }
        assert module_fks == {
            (("organization_id",), "organization", ("id",)),
            (
                ("organization_id", "group_id"),
                "joint_lesson_group",
                ("organization_id", "id"),
            ),
            (("organization_id", "module_id"), "module", ("organization_id", "id")),
        }

        for table in TABLES:
            rowsecurity = connection.execute(
                text(
                    "SELECT c.relrowsecurity, c.relforcerowsecurity FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relname = :table"
                ),
                {"table": table},
            ).one()
            assert rowsecurity == (True, True)
            policy = connection.scalar(
                text(
                    "SELECT count(*) FROM pg_policies "
                    "WHERE schemaname = 'public' AND tablename = :table "
                    "AND policyname = 'tenant_isolation'"
                ),
                {"table": table},
            )
            assert policy == 1
            grants = connection.execute(
                text(
                    f"SELECT has_table_privilege('cronos_app', 'public.{table}', 'SELECT'), "
                    f"has_table_privilege('cronos_app', 'public.{table}', 'INSERT'), "
                    f"has_table_privilege('cronos_app', 'public.{table}', 'DELETE'), "
                    f"has_table_privilege('cronos_app', 'public.{table}', 'UPDATE')"
                )
            ).one()
            assert grants == (True, True, True, True)

        sequence_usage = connection.scalar(
            text(
                "SELECT has_sequence_privilege('cronos_app', "
                "'public.joint_lesson_group_id_seq', 'USAGE')"
            )
        )
        assert sequence_usage is True

        unique_columns = [
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("scheduler_lesson_v1")
            if constraint["name"] == "uq_scheduler_lesson_v1_stable_key"
        ]
        assert unique_columns == [("version_id", "stable_key", "assignment_id")]

        unit_column = {
            column["name"]: column for column in inspector.get_columns("scheduler_lesson_v1")
        }["teaching_unit_key"]
        assert unit_column["nullable"] is False
        assert unit_column["type"].length == 80


def test_integrity_audit_accepts_the_migrated_test_database(clean_database):
    """The real read-only integrity audit passes on the migrated test schema.

    ``_audit_connection`` checks the metadata table set, unique keys, foreign
    keys, required check constraints and forced row-level security, so it covers
    the three joint tables and their composite foreign keys.
    """
    with sync_test_engine.connect() as connection:
        errors = audit_database_integrity._audit_connection(connection)
    assert errors == []


async def test_trigger_audit_accepts_the_migrated_test_database(clean_database, monkeypatch):
    """The real trigger audit passes against the isolated migrated test database."""
    monkeypatch.setattr(audit_triggers, "engine_async", test_engine)
    errors = await audit_triggers._check_triggers()
    assert errors == []
