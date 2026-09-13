from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import select

from app import models
from app.api.deps import Actor
from app.api.v1.endpoints import classes as classes_endpoint
from app.config import settings
from app.core.ratelimit import limiter
from app.main import app

APP = Path(__file__).parents[2] / "app"
BACKEND = APP.parent


def _python_files(folder: str) -> list[Path]:
    return sorted((APP / folder).rglob("*.py"))


def test_actor_is_immutable_and_membership_derived() -> None:
    actor = Actor(
        account_id=1,
        clerk_user_id="user_1",
        organization_id=2,
        membership_id=3,
        can_admin=True,
        can_teach=False,
        teacher_id=None,
    )

    with pytest.raises(FrozenInstanceError):
        actor.can_admin = False  # type: ignore[misc]

    assert not hasattr(actor, "role")
    assert not hasattr(actor, "is_superuser")
    assert not hasattr(actor, "id")


def test_rate_limiter_has_explicit_enabled_setting() -> None:
    assert isinstance(settings.RATELIMIT_ENABLED, bool)


def test_every_route_is_default_limited_or_intentionally_exempt() -> None:
    expected_exemptions = {"/health/live", "/health/ready", "/api/v1/health"}

    def iter_routes(route_list, prefix=""):
        for route in route_list:
            if isinstance(route, APIRoute):
                yield route, f"{prefix}{route.path}"
            elif hasattr(route, "original_router"):
                include_prefix = route.include_context.prefix
                yield from iter_routes(
                    route.original_router.routes,
                    f"{prefix}{include_prefix}",
                )
            elif hasattr(route, "routes"):
                yield from iter_routes(route.routes, prefix)

    exempt_paths = {
        path
        for route, path in iter_routes(app.routes)
        if f"{route.endpoint.__module__}.{route.endpoint.__name__}" in limiter._exempt_routes
    }
    assert exempt_paths == expected_exemptions
    assert limiter._default_limits
    assert all(
        path in expected_exemptions
        or f"{route.endpoint.__module__}.{route.endpoint.__name__}" not in limiter._exempt_routes
        for route, path in iter_routes(app.routes)
    )


def test_flat_class_routes_are_read_only() -> None:
    routes = {
        (route.path, method)
        for route in classes_endpoint.router.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }

    assert ("/", "GET") in routes
    assert ("/{class_id}", "GET") in routes
    assert not any(
        path in {"/", "/{class_id}"}
        and method in {"POST", "PATCH", "DELETE"}
        for path, method in routes
    )


def test_production_lock_avoids_platform_conditional_uvicorn_extra() -> None:
    direct_requirements = (BACKEND / "requirements.in").read_text(encoding="utf-8")

    assert "uvicorn==0.52.4" in direct_requirements.splitlines()
    assert "uvicorn[standard]" not in direct_requirements


def test_development_lock_pins_unsafe_build_requirements() -> None:
    direct_requirements = (BACKEND / "requirements-dev.in").read_text(encoding="utf-8")
    lock = (BACKEND / "requirements-dev.txt").read_text(encoding="utf-8")

    assert "pip==26.2.1" in direct_requirements.splitlines()
    assert "# WARNING:" not in lock
    assert "\npip==26.2.1 " in lock
    assert "\nsetuptools==" in lock


def test_every_teacher_requires_one_membership() -> None:
    assert models.Teacher.__table__.c.organization_membership_id.nullable is False
    assert "name" not in models.Teacher.__table__.c


def test_teacher_name_is_derived_from_membership() -> None:
    membership = models.OrganizationMembership(organization_display_name="Canonical Teacher")
    teacher = models.Teacher(organization_membership=membership)

    assert teacher.name == "Canonical Teacher"


def test_teacher_name_expression_survives_explicit_membership_join() -> None:
    statement = (
        select(models.Teacher)
        .join(models.Teacher.organization_membership)
        .order_by(models.Teacher.name)
    )

    assert "organization_display_name" in str(statement)


def test_tenant_audit_columns_reference_memberships() -> None:
    audit_columns = {
        "organization_membership": {
            "created_by_membership_id",
            "updated_by_membership_id",
        },
        "member_access_operation": {"created_by_membership_id"},
        "scheduler_school_year_state": {"reset_by_membership_id"},
        "schedule_generation_job": {"requested_by_membership_id"},
        "schedule_drafts": {
            "created_by_membership_id",
            "decided_by_membership_id",
        },
        "scheduler_state_version_events": {"changed_by_membership_id"},
        "lesson_occurrence": {
            "created_by_membership_id",
            "revoked_by_membership_id",
            "decided_by_membership_id",
        },
        "occurrence_operational_event": {"actor_membership_id"},
        "operational_schedule_block": {"created_by_membership_id"},
        "teacher_endpoint_operational_event": {"actor_membership_id"},
        "lesson_log": {"logged_by_membership_id"},
        "teacher_weekly_timesheet": {"approved_by_membership_id"},
        "progress_ledger_entry": {"created_by_membership_id"},
    }

    for table_name, column_names in audit_columns.items():
        table = models.Base.metadata.tables[table_name]
        for column_name in column_names:
            foreign_keys = table.c[column_name].foreign_keys
            assert {foreign_key.column.table.name for foreign_key in foreign_keys} == {
                "organization_membership"
            }


def test_migration_scopes_tenant_audit_keys_to_the_same_organization() -> None:
    migration = (BACKEND / "alembic" / "versions" / "0001_initial.py").read_text(encoding="utf-8")
    expected_constraints = {
        "fk_organization_membership_created_by_membership_id_org",
        "fk_organization_membership_updated_by_membership_id_org",
        "fk_member_access_operation_created_by_membership_id_org",
        "fk_scheduler_school_year_state_reset_by_membership_id_org",
        "fk_schedule_generation_job_requested_by_membership_id_org",
        "fk_schedule_drafts_created_by_membership_id_org",
        "fk_schedule_drafts_decided_by_membership_id_org",
        "fk_scheduler_state_version_events_changed_by_membership_id_org",
        "fk_lesson_occurrence_created_by_membership_id_org",
        "fk_lesson_occurrence_revoked_by_membership_id_org",
        "fk_lesson_occurrence_decided_by_membership_id_org",
        "fk_occurrence_operational_event_actor_membership_id_org",
        "fk_operational_schedule_block_created_by_membership_id_org",
        "fk_teacher_endpoint_operational_event_actor_membership_id_org",
        "fk_lesson_log_logged_by_membership_id_org",
        "fk_teacher_weekly_timesheet_approved_by_membership_id_org",
        "fk_progress_ledger_entry_created_by_membership_id_org",
    }

    assert all(name in migration for name in expected_constraints)


def test_tenant_routes_do_not_use_weak_authentication_dependency() -> None:
    offenders = {
        path.relative_to(APP): line
        for path in _python_files("api/v1/endpoints")
        for line in path.read_text(encoding="utf-8").splitlines()
        if "Depends(deps.get_current_user)" in line
    }
    assert offenders == {}


def test_api_database_dependencies_are_function_scoped() -> None:
    offenders = []
    paths = [APP / "api" / "deps.py", *_python_files("api/v1/endpoints")]
    for path in paths:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "Depends(" in line and "get_db" in line and 'scope="function"' not in line:
                offenders.append(f"{path.relative_to(APP)}:{line_number}")
    assert offenders == []


def test_ordinary_api_and_services_do_not_control_transactions() -> None:
    allowed = {
        Path("api/deps.py"),
        Path("services/member_service.py"),
        Path("services/member_access_operation_service.py"),
        Path("services/operational_seed_service.py"),
        Path("services/scheduler_job_runtime.py"),
        Path("services/scheduler_request_service.py"),
    }
    offenders: list[str] = []
    for scope in ("api", "services"):
        for path in _python_files(scope):
            relative = path.relative_to(APP)
            if relative in allowed:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in {"commit", "rollback"}
                ):
                    offenders.append(f"{relative}:{node.lineno}")
    assert offenders == []


def test_clean_architecture_import_boundaries() -> None:
    forbidden_domain = {"fastapi", "sqlalchemy", "celery", "redis", "app.api", "app.services"}
    offenders: list[str] = []
    for path in _python_files("scheduler/domain"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in (
                node.names if isinstance(node, ast.Import) else [ast.alias(node.module or "")]
            )
        ]
        for name in imports:
            if any(name == root or name.startswith(f"{root}.") for root in forbidden_domain):
                offenders.append(f"{path.relative_to(APP)} imports {name}")

    for path in _python_files("services"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            module = node.module if isinstance(node, ast.ImportFrom) else None
            names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else []
            imported = [module] if module else names
            for name in imported:
                if name and (name == "fastapi" or name.startswith("fastapi.")):
                    offenders.append(f"{path.relative_to(APP)} imports {name}")
                if name and (name.endswith("_worker") or ".celery_worker" in name):
                    offenders.append(f"{path.relative_to(APP)} imports {name}")
    assert offenders == []
