"""Internal tenant export and erasure command.

The operator exports first, confirms provider deletion second, and runs the
local erasure transaction last. The command remains offline from Clerk.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import zipfile
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import models
from app.config import settings
from app.db.database import Base, SessionLocal, async_database_url
from app.db.tenant import set_async_tenant_context
from app.scheduler.infrastructure.models import JOB_ACTIVE_STATUSES, SchedulerJobV1

_admin_engine = None


def _administrative_url() -> str:
    url = os.environ.get("MIGRATION_DATABASE_URL") or str(
        settings.MIGRATION_DATABASE_URL or settings.DATABASE_URL or ""
    )
    if not url:
        raise ValueError("An administrative database URL is required for erasure.")
    return async_database_url(url)


def _administrative_sessions():
    """Table-owner session used only by the explicit erasure command.

    The runtime role keeps its append-only contract. Broad DELETE grants are
    never given to it.
    """
    global _admin_engine
    if _admin_engine is None:
        _admin_engine = create_async_engine(_administrative_url(), poolclass=NullPool)
    return async_sessionmaker(_admin_engine, expire_on_commit=False)


# Every tenant table must be classified here.  This is intentionally explicit:
# adding a model with organization_id without updating the privacy runbook must
# fail the contract check instead of silently changing export/erase semantics.
PRIVACY_TABLES = {
    "course": "delete",
    "grid_version": "delete",
    "organization_grid_settings": "delete",
    "organization_membership": "delete",
    "organization_settings": "delete",
    "room": "delete",
    "scheduler_school_year": "delete",
    "school_calendar_event": "delete",
    "school_calendar_event_class": "delete",
    "subject": "delete",
    "teacher": "delete",
    "timeslot": "delete",
    "availability": "delete",
    "class": "delete",
    "course_subject_link": "delete",
    "member_access_operation": "delete",
    "module": "delete",
    "organization_foundation_draft": "delete",
    "teacher_subject_link": "delete",
    "teacher_weekly_timesheet": "delete",
    "class_subject_link": "delete",
    "constraint": "delete",
    "lesson_occurrence": "delete",
    "progress_ledger_entry": "delete",
    "schedule_drafts": "delete",
    "schedule_draft_blocks": "delete",
    "scheduler_school_year_state": "delete",
    "active_schedule_blocks": "delete",
    "schedule_diff_entries": "delete",
    "scheduler_state_version_events": "delete",
    "operational_schedule_block": "delete",
    "lesson_log": "delete",
    "planned_recovery_links": "delete",
    "curricular_assignment": "delete",
    "curricular_requirement": "delete",
    "curricular_execution": "delete",
    "curricular_execution_credit": "delete",
    "curricular_debt": "delete",
    "curricular_debt_revision": "delete",
    "curricular_debt_settlement": "delete",
    "scheduler_version_v1": "delete",
    "scheduler_lesson_v1": "delete",
    "scheduler_lesson_log_v1": "delete",
    "scheduler_lesson_slice_v1": "delete",
    "scheduler_recovery_reservation_v1": "delete",
    "scheduler_job_v1": "delete",
    "scheduler_proposal_v1": "delete",
    "organization_legal_acceptance": "preserve",
}
PRESERVED_TABLES = {"organization", "organization_legal_acceptance", "alembic_version"}
SECRET_PARTS = ("secret", "token", "password", "api_key")


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {_safe_key(key): _json_value(value_item) for key, value_item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _safe_key(key: Any) -> str:
    return str(key)


def _is_secret(name: str) -> bool:
    lowered = name.lower()
    return any(part in lowered for part in SECRET_PARTS)


def _row_to_json(row, columns) -> dict[str, Any]:
    return {
        column.name: None if _is_secret(column.name) else _json_value(row._mapping[column])
        for column in columns
    }


def validate_privacy_table_registry() -> None:
    tenant_tables = {
        table.name for table in Base.metadata.sorted_tables if "organization_id" in table.c
    }
    registered = set(PRIVACY_TABLES)
    missing = sorted(tenant_tables - registered)
    unknown = sorted(registered - tenant_tables)
    if missing or unknown:
        raise RuntimeError(
            "PRIVACY_TABLES desatualizado; "
            f"sem classificação={missing or []}, tabelas inexistentes={unknown or []}"
        )


def _tenant_tables(policy: str = "delete"):
    validate_privacy_table_registry()
    return [
        table for table in Base.metadata.sorted_tables if PRIVACY_TABLES.get(table.name) == policy
    ]


async def _load_export(organization_id: int) -> dict[str, list[dict[str, Any]]]:
    async with SessionLocal() as db:
        await set_async_tenant_context(db, organization_id)
        return await _load_export_from_session(db, organization_id)


async def _load_export_from_session(db, organization_id: int) -> dict[str, list[dict[str, Any]]]:
    """Export the same classified data within an existing administrative lock."""
    result: dict[str, list[dict[str, Any]]] = {}
    organization = await db.execute(
        select(models.Organization.__table__).where(models.Organization.id == organization_id)
    )
    result["organization"] = [
        _row_to_json(row, models.Organization.__table__.columns) for row in organization
    ]
    for table in _tenant_tables():
        rows = await db.execute(select(table).where(table.c.organization_id == organization_id))
        result[table.name] = [_row_to_json(row, table.columns) for row in rows]

    membership_table = models.OrganizationMembership.__table__
    memberships = await db.execute(
        select(membership_table).where(membership_table.c.organization_id == organization_id)
    )
    membership_rows = [_row_to_json(row, membership_table.columns) for row in memberships]
    result[membership_table.name] = membership_rows
    legal_table = models.OrganizationLegalAcceptance.__table__
    legal_acceptances = await db.execute(
        select(legal_table).where(legal_table.c.organization_id == organization_id)
    )
    result[legal_table.name] = [_row_to_json(row, legal_table.columns) for row in legal_acceptances]
    account_ids = [row["account_id"] for row in membership_rows if row.get("account_id")]
    if account_ids:
        users = await db.execute(
            select(models.User.__table__).where(models.User.id.in_(account_ids))
        )
        result[models.User.__tablename__] = [
            _row_to_json(row, models.User.__table__.columns) for row in users
        ]
    return result


def confined_export_path(destination) -> Path:
    """Reject traversal and symbolic parents, then canonicalize the target."""
    path = Path(destination)
    if ".." in path.parts:
        raise ValueError("Export path must not contain parent traversal")
    if any(parent.is_symlink() for parent in path.parents):
        raise ValueError("Export directory must not be a symbolic link")
    resolved = Path(os.path.realpath(path))
    if not resolved.name or resolved.name in {".", ".."}:
        raise ValueError("Export path must name a file")
    return resolved


def open_private_export(destination: Path):
    path = confined_export_path(destination)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    return os.fdopen(descriptor, "wb")


def _write_export(output: Path, data: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    output = confined_export_path(output)
    if output.exists() and output.is_dir():
        raise ValueError("--output deve indicar um ficheiro ZIP, não uma pasta")
    manifest: dict[str, Any] = {"format": "cronos-privacy-export-v1", "tables": {}}
    created = False
    try:
        with open_private_export(output) as export_file:
            created = True
            with zipfile.ZipFile(export_file, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for table_name, rows in sorted(data.items()):
                    content = json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True).encode(
                        "utf-8"
                    )
                    filename = f"tables/{table_name}.json"
                    archive.writestr(filename, content)
                    manifest["tables"][table_name] = {
                        "file": filename,
                        "count": len(rows),
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                manifest_content = json.dumps(
                    manifest, ensure_ascii=False, indent=2, sort_keys=True
                ).encode("utf-8")
                archive.writestr("manifest.json", manifest_content)
            export_file.flush()
            os.fsync(export_file.fileno())
    except Exception:
        if created:
            output.unlink(missing_ok=True)
        raise
    return {
        "output": str(output),
        "tables": {name: value["count"] for name, value in manifest["tables"].items()},
    }


async def _counts(db, organization_id: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in _tenant_tables():
        total = await db.scalar(
            select(func.count())
            .select_from(table)
            .where(table.c.organization_id == organization_id)
        )
        counts[table.name] = int(total or 0)
    return counts


async def active_jobs(db, organization_id: int) -> list[str]:
    """Return active scheduler job ids; callers hold the organization row lock."""
    active = await db.scalars(
        select(SchedulerJobV1.id).where(
            SchedulerJobV1.organization_id == organization_id,
            SchedulerJobV1.status.in_(JOB_ACTIVE_STATUSES),
        )
    )
    return [f"v1:{value}" for value in active]


async def _erase(
    organization_id: int,
    confirm_clerk_org_id: str,
    execute: bool,
    provider_deleted: bool,
) -> dict[str, Any]:
    if execute and not provider_deleted:
        raise ValueError("--execute exige --provider-deleted após confirmação no fornecedor")
    async with _administrative_sessions().begin() as db:
        await db.execute(text("SET LOCAL row_security = off"))
        return await _erase_locked(
            db, organization_id, confirm_clerk_org_id, execute, provider_deleted
        )


async def _erase_locked(
    db, organization_id: int, confirm_clerk_org_id: str, execute: bool, provider_deleted: bool
) -> dict[str, Any]:
    """Reuse the caller transaction, retaining the parent lock until commit."""
    if execute and not provider_deleted:
        raise ValueError("--execute exige --provider-deleted após confirmação no fornecedor")
    organization = await db.scalar(
        select(models.Organization)
        .where(models.Organization.id == organization_id)
        .with_for_update()
    )
    if organization is None:
        raise ValueError("Organização não encontrada")
    if organization.clerk_org_id != confirm_clerk_org_id:
        raise ValueError("--confirm-clerk-org-id não corresponde à organização")
    if execute and await active_jobs(db, organization_id):
        raise ValueError("Erasure refused while active jobs exist")
    counts = await _counts(db, organization_id)
    if not execute:
        return {"dry_run": True, "organization_id": organization_id, "counts": counts}

    membership_account_ids = list(
        await db.scalars(
            select(models.OrganizationMembership.account_id).where(
                models.OrganizationMembership.organization_id == organization_id
            )
        )
    )
    organization.plan_status = models.OrganizationPlanStatus.inactive
    organization.clerk_org_id = None
    for table in reversed(_tenant_tables()):
        await db.execute(delete(table).where(table.c.organization_id == organization_id))
    if membership_account_ids:
        await db.execute(
            delete(models.User).where(
                models.User.id.in_(membership_account_ids),
                ~models.User.memberships.any(),
            )
        )
    # The monotonic foundation trigger forbids regressing the status, so the
    # erasure leaves a de-identified tombstone instead of resetting it.
    organization.name = "Organização eliminada"
    return {
        "dry_run": False,
        "organization_id": organization_id,
        "counts": counts,
        "tombstone": True,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m scripts.privacy")
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export")
    export.add_argument("--organization-id", required=True, type=int)
    export.add_argument("--output", required=True, type=Path)
    erase = commands.add_parser("erase")
    erase.add_argument("--organization-id", required=True, type=int)
    erase.add_argument("--confirm-clerk-org-id", required=True)
    erase.add_argument("--execute", action="store_true")
    erase.add_argument("--provider-deleted", action="store_true")
    return parser


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    if args.organization_id < 1:
        raise ValueError("--organization-id deve ser positivo")
    if args.command == "export":
        return _write_export(args.output, await _load_export(args.organization_id))
    return await _erase(
        args.organization_id,
        args.confirm_clerk_org_id,
        args.execute,
        args.provider_deleted,
    )


def main() -> None:
    args = _parser().parse_args()
    try:
        print(json.dumps(asyncio.run(_run(args)), ensure_ascii=False, sort_keys=True))
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
