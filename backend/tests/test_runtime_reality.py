import re
from datetime import date, time

import pytest
from alembic import command
from sqlalchemy import text

from app import models
from app.services.scheduler_state_service import SchedulerStateService
from scripts.repair_migrations import main as repair_migrations_main
from tests.conftest import _alembic_config, create_org_and_user, sync_test_engine


pytestmark = pytest.mark.postgresql


def test_alembic_repair_removes_stale_revision_and_can_be_restamped():
    """Regression for persistent volumes stamped with deleted migration IDs."""
    with sync_test_engine.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num = 'e7b8c9d0a1f2'"))

    try:
        repair_migrations_main()
        with sync_test_engine.begin() as conn:
            exists = conn.execute(
                text("SELECT to_regclass('public.alembic_version')")
            ).scalar_one()
        assert exists is None
    finally:
        with sync_test_engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
        command.stamp(_alembic_config(), "head")


def test_tenant_ref_trigger_functions_only_reference_existing_columns():
    """PL/pgSQL trigger bodies are validated only when executed, so audit them."""
    column_refs = re.compile(r'NEW\."?([A-Za-z_][A-Za-z0-9_]*)"?')
    with sync_test_engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT c.relname AS table_name, p.proname, p.prosrc
                FROM pg_trigger t
                JOIN pg_class c ON c.oid = t.tgrelid
                JOIN pg_proc p ON p.oid = t.tgfoid
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'app_security'
                  AND p.proname LIKE 'validate_%_tenant_refs'
                  AND NOT t.tgisinternal
                ORDER BY c.relname
                """
            )
        ).mappings().all()

        assert rows, "Alembic-created tenant-ref triggers are missing."
        for row in rows:
            table_name = row["table_name"]
            actual_columns = set(
                conn.execute(
                    text(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = :table_name
                        """
                    ),
                    {"table_name": table_name},
                ).scalars()
            )
            refs = set(column_refs.findall(row["prosrc"])) - {"organization_id"}
            missing = refs - actual_columns
            assert not missing, f"{row['proname']} references missing columns: {sorted(missing)}"


@pytest.mark.asyncio
async def test_scheduler_state_event_trigger_executes_after_alembic_migration(db_session):
    org, user = await create_org_and_user(
        db_session,
        clerk_user_id="user_trigger_reality",
        email="trigger.reality@example.com",
        role="admin",
        clerk_org_id="org_trigger_reality",
    )

    service = SchedulerStateService(db_session)
    await service.get_or_create_active_state(
        org.id,
        start_date=date(2025, 9, 1),
        hard_end_date=date(2026, 7, 31),
    )
    event = await service.record_change(
        org.id,
        entity_type="ONBOARDING_CONFIG",
        entity_id="initial",
        operation=models.SchedulerStateChangeOperation.UPDATE,
        before={"configured": False},
        after={"configured": True},
        changed_by_user_id=user.id,
    )

    assert event is not None
    assert event.changed_by_user_id == user.id


@pytest.mark.asyncio
async def test_fresh_session_requests_cover_core_beta_surfaces(
    db_session,
    real_async_client,
    monkeypatch,
):
    """Regression for async lazy-load bugs hidden by shared-session fixtures."""
    org, user = await create_org_and_user(
        db_session,
        clerk_user_id="user_fresh_session_admin",
        email="fresh.session.admin@example.com",
        role="admin",
        clerk_org_id="org_fresh_session",
    )
    teacher = models.Teacher(name="Fresh Session Teacher", organization_id=org.id)
    timeslot = models.Timeslot(
        organization_id=org.id,
        day_of_week=0,
        start_time=time(9, 0),
        end_time=time(10, 0),
    )
    db_session.add_all([teacher, timeslot])
    await db_session.commit()

    payload = {"sub": user.clerk_user_id, "o": {"id": org.clerk_org_id, "rol": "admin"}}

    async def _mock_payload(_request):
        return payload

    monkeypatch.setattr("app.api.deps.get_clerk_payload", _mock_payload)
    headers = {"Authorization": "Bearer fresh-session-admin"}

    async def request(method: str, path: str, *, json: dict | list | None = None, ok=(200,)):
        response = await real_async_client.request(method, path, headers=headers, json=json)
        assert response.status_code in ok, f"{method} {path}: {response.status_code} {response.text}"
        return response

    await request(
        "POST",
        "/api/v1/school/settings/",
        json={
            "school_start_date": "2025-09-15",
            "school_hard_end_date": "2026-07-31",
            "repair_stability_window_days": 0,
        },
    )
    await request(
        "POST",
        "/api/v1/school/grid-settings/",
        json={
            "lunch_window_start": "12:30",
            "lunch_window_end": "14:00",
            "lunch_min_duration_minutes": 60,
        },
    )
    await request("POST", "/api/v1/rooms/", json={"name": "Sala Fresh", "type": "normal", "capacity": 30})
    await request(
        "POST",
        "/api/v1/subjects/",
        json={
            "name": "Disciplina Fresh",
            "required_room_type": "normal",
            "modules": [{"name": "Modulo 1", "code": "M1", "hours_total": 10, "order": 0}],
        },
    )
    await request("POST", "/api/v1/courses/", json={"name": "Curso Fresh", "abbreviation": "CF"})

    for path in (
        "/api/v1/members/me",
        "/api/v1/members",
        "/api/v1/dashboard",
        "/api/v1/school/settings/",
        "/api/v1/school/grid-settings/",
        "/api/v1/rooms/",
        "/api/v1/subjects/",
        "/api/v1/courses/",
        "/api/v1/classes/",
        "/api/v1/schedule/latest",
        "/api/v1/scheduler/status",
        "/api/v1/occurrences/",
        "/api/v1/occurrences/debts",
        "/api/v1/teachers/",
    ):
        await request("GET", path)

    await request(
        "POST",
        f"/api/v1/teachers/{teacher.id}/availability",
        json=[{"timeslot_id": timeslot.id, "score": 1}],
    )
