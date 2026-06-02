import uuid

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import create_engine, text

from app.db.database import SYNC_DB_URL


pytestmark = pytest.mark.postgresql


def _has_rls_objects(conn) -> bool:
    return bool(
        conn.execute(text("SELECT to_regproc('app_security.current_organization_id')")).scalar()
        and conn.execute(text("SELECT to_regclass('public.organization')")).scalar()
    )


def _set_role_cronos_app_or_skip(conn) -> None:
    savepoint = conn.begin_nested()
    try:
        conn.execute(text("SET ROLE cronos_app"))
    except SQLAlchemyError as exc:
        savepoint.rollback()
        pytest.skip(f"current database user cannot SET ROLE cronos_app: {exc}")
    else:
        savepoint.commit()


def test_current_organization_id_helper_fails_closed_and_parses_valid_values():
    engine = create_engine(SYNC_DB_URL)
    with engine.begin() as conn:
        if not _has_rls_objects(conn):
            pytest.skip("RLS helper function is available only on Alembic-created PostgreSQL schemas")

        invalid_values = ["", "abc", "-1", "0", "2147483648", "99999999999999999999"]
        for raw in invalid_values:
            conn.execute(text("SELECT set_config('app.current_organization_id', :raw, true)"), {"raw": raw})
            assert conn.execute(text("SELECT app_security.current_organization_id()")).scalar() is None

        for raw, expected in [("1", 1), ("2147483647", 2147483647)]:
            conn.execute(text("SELECT set_config('app.current_organization_id', :raw, true)"), {"raw": raw})
            assert conn.execute(text("SELECT app_security.current_organization_id()")).scalar() == expected


def test_rls_denies_missing_context_and_blocks_cross_tenant_writes():
    engine = create_engine(SYNC_DB_URL)
    marker = uuid.uuid4().hex[:12]
    with engine.begin() as conn:
        if not _has_rls_objects(conn):
            pytest.skip("RLS policies are available only on Alembic-created PostgreSQL schemas")

        org_a = conn.execute(
            text("INSERT INTO organization (name, plan_status) VALUES (:name, 'active') RETURNING id"),
            {"name": f"RLS Org A {marker}"},
        ).scalar_one()
        org_b = conn.execute(
            text("INSERT INTO organization (name, plan_status) VALUES (:name, 'active') RETURNING id"),
            {"name": f"RLS Org B {marker}"},
        ).scalar_one()
        teacher_a = conn.execute(
            text("INSERT INTO teacher (name, organization_id) VALUES ('Teacher A', :org) RETURNING id"),
            {"org": org_a},
        ).scalar_one()
        slot_a = conn.execute(
            text(
                """
                INSERT INTO timeslot (day_of_week, start_time, end_time, organization_id)
                VALUES (1, '08:00', '09:00', :org)
                RETURNING id
                """
            ),
            {"org": org_a},
        ).scalar_one()

        _set_role_cronos_app_or_skip(conn)
        conn.execute(text("SELECT set_config('app.current_organization_id', '', true)"))
        assert conn.execute(text("SELECT count(*) FROM teacher")).scalar_one() == 0

        conn.execute(text("SELECT set_config('app.current_organization_id', :org, true)"), {"org": str(org_a)})
        assert conn.execute(text("SELECT count(*) FROM teacher")).scalar_one() == 1

        savepoint = conn.begin_nested()
        with pytest.raises(Exception):
            conn.execute(
                text(
                    """
                    INSERT INTO availability (organization_id, teacher_id, timeslot_id, score)
                    VALUES (:org_b, :teacher_a, :slot_a, 1)
                    """
                ),
                {"org_b": org_b, "teacher_a": teacher_a, "slot_a": slot_a},
            )
        savepoint.rollback()

        conn.execute(text("RESET ROLE"))


def test_auth_definer_helpers_work_without_tenant_context_and_preserve_alembic_table():
    engine = create_engine(SYNC_DB_URL)
    marker = uuid.uuid4().hex[:12]
    with engine.begin() as conn:
        if not _has_rls_objects(conn):
            pytest.skip("RLS policies are available only on Alembic-created PostgreSQL schemas")

        _set_role_cronos_app_or_skip(conn)
        org_id = conn.execute(
            text("SELECT id FROM app_security.ensure_organization(:clerk_org_id, :name)"),
            {"clerk_org_id": f"org_{marker}", "name": "Webhook Helper Org"},
        ).scalar_one()
        user_row = conn.execute(
            text(
                """
                SELECT id, organization_id
                FROM app_security.ensure_user(
                    :clerk_user_id,
                    :email,
                    :display_name,
                    :role,
                    :organization_id,
                    NULL
                )
                """
            ),
            {
                "clerk_user_id": f"user_{marker}",
                "email": "first@example.com",
                "display_name": "First Name",
                "role": "member",
                "organization_id": org_id,
            },
        ).mappings().one()

        assert user_row["organization_id"] == org_id
        assert conn.execute(text('SELECT count(*) FROM public."user"')).scalar_one() == 0
        assert conn.execute(
            text("SELECT has_table_privilege('cronos_app', 'public.alembic_version', 'INSERT')")
        ).scalar_one() is False

        conn.execute(
            text(
                """
                SELECT app_security.update_user_profile(
                    :clerk_user_id,
                    :email,
                    :display_name,
                    :role,
                    :teacher_id
                )
                """
            ),
            {
                "clerk_user_id": f"user_{marker}",
                "email": "second@example.com",
                "display_name": "Second Name",
                "role": "org:member",
                "teacher_id": None,
            },
        )
        assert conn.execute(
            text("SELECT app_security.deactivate_user(:clerk_user_id)"),
            {"clerk_user_id": f"user_{marker}"},
        ).scalar_one() is True

        assert conn.execute(
            text("SELECT app_security.deactivate_organization(:clerk_org_id)"),
            {"clerk_org_id": f"missing_org_{marker}"},
        ).scalar_one() is False
        assert conn.execute(
            text("SELECT app_security.deactivate_organization(:clerk_org_id)"),
            {"clerk_org_id": f"org_{marker}"},
        ).scalar_one() is True
        conn.execute(text("RESET ROLE"))

        profile = conn.execute(
            text('SELECT email, name, role::text AS role, is_active FROM public."user" WHERE id = :id'),
            {"id": user_row["id"]},
        ).mappings().one()
        assert dict(profile) == {
            "email": "second@example.com",
            "name": "Second Name",
            "role": "teacher",
            "is_active": False,
        }


def test_deactivate_user_preserves_last_active_admin():
    engine = create_engine(SYNC_DB_URL)
    marker = uuid.uuid4().hex[:12]
    with engine.begin() as conn:
        if not _has_rls_objects(conn):
            pytest.skip("RLS policies are available only on Alembic-created PostgreSQL schemas")

        _set_role_cronos_app_or_skip(conn)
        org_id = conn.execute(
            text("SELECT id FROM app_security.ensure_organization(:clerk_org_id, :name)"),
            {"clerk_org_id": f"org_admin_{marker}", "name": "Admin Guard Org"},
        ).scalar_one()
        conn.execute(
            text(
                """
                SELECT id
                FROM app_security.ensure_user(
                    :clerk_user_id,
                    :email,
                    :display_name,
                    'admin',
                    :organization_id,
                    NULL
                )
                """
            ),
            {
                "clerk_user_id": f"admin_{marker}",
                "email": "admin@example.com",
                "display_name": "Only Admin",
                "organization_id": org_id,
            },
        ).scalar_one()

        assert conn.execute(
            text("SELECT app_security.deactivate_user(:clerk_user_id)"),
            {"clerk_user_id": f"admin_{marker}"},
        ).scalar_one() is False
        conn.execute(text("RESET ROLE"))
