"""Administrative cleanup of signed, UI-created disposable campaign schools.

Accept the signed registry on stdin. Never grant the browser database privileges.
"""

import argparse
import asyncio
import base64
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from clerk_backend_api import Clerk
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import models
from scripts import privacy
from scripts.e2e_cleanup_policy import cleanup_targets, verify_registry


def _key(value):
    try:
        key = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as error:
        raise ValueError("Invalid administrative protection key") from error
    if len(key) != 32 or base64.b64encode(key).decode() != value:
        raise ValueError("Invalid administrative protection key")
    return key


def validate_environment(env):
    required = [
        "MIGRATION_DATABASE_URL",
        "E2E_CLEANUP_CLERK_SECRET_KEY",
        "E2E_REGISTRY_HMAC_KEY",
        "E2E_ARTIFACT_KEY",
    ]
    if any(not env.get(name) for name in required):
        raise ValueError("Separate administrative credentials and protection keys are required")
    administrative = make_url(env["MIGRATION_DATABASE_URL"])
    runtime = make_url(env["DATABASE_URL"]) if env.get("DATABASE_URL") else None
    if (
        administrative.get_backend_name() != "postgresql"
        or administrative.username == "cronos_app"
        or not administrative.username
        or (runtime is not None and runtime.username == administrative.username)
    ):
        raise ValueError("Cleanup requires a separate administrative database credential")
    return _key(env["E2E_REGISTRY_HMAC_KEY"]), _key(env["E2E_ARTIFACT_KEY"])


def protect_export(destination, content, key, run_id):
    if len(key) != 32 or not isinstance(run_id, str) or not run_id:
        raise ValueError("Export protection requires a 32-byte key and run identity")
    destination = Path(destination)
    for parent in [destination.parent, *destination.parents]:
        if parent.is_symlink():
            raise ValueError("Export directory must not be a symbolic link")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    original_path = destination.name.removesuffix(".enc")
    aad = json.dumps(
        {"version": 1, "run_id": run_id, "path": original_path}, separators=(",", ":")
    ).encode()
    nonce = os.urandom(12)
    encrypted = AESGCM(key).encrypt(nonce, content, aad)
    envelope = {
        "version": 1,
        "nonce": base64.b64encode(nonce).decode(),
        "tag": base64.b64encode(encrypted[-16:]).decode(),
        "ciphertext": base64.b64encode(encrypted[:-16]).decode(),
    }
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(json.dumps(envelope, separators=(",", ":")).encode())
        output.flush()
        os.fsync(output.fileno())


async def _provider_members(sdk, clerk_id):
    members = []
    offset = 0
    while True:
        page = await sdk.organization_memberships.list_async(
            organization_id=clerk_id, limit=100, offset=offset, timeout_ms=30000
        )
        if page.total_count is None or page.total_count < len(members) + len(page.data):
            raise ValueError("Provider membership inventory is incomplete")
        for membership in page.data:
            user = membership.public_user_data
            if user is None or not user.user_id:
                raise ValueError("Provider membership identity is missing")
            members.append(user.user_id)
        if len(members) == page.total_count:
            if len(set(members)) != len(members):
                raise ValueError("Duplicate provider membership identity")
            return set(members)
        if not page.data or offset >= 10000:
            raise ValueError("Provider membership inventory is incomplete")
        offset += len(page.data)


def _primary_email(user):
    emails = [
        address.email_address
        for address in user.email_addresses
        if address.id == user.primary_email_address_id
    ]
    if len(emails) != 1:
        raise ValueError("Provider actor has no unambiguous primary email")
    return emails[0]


async def _observe(db, sdk, organization):
    local_id = organization["local_id"]
    local = await db.get(models.Organization, local_id)
    if local is None or local.clerk_org_id != organization["clerk_id"]:
        raise ValueError("Live local organization identity does not match")
    provider = await sdk.organizations.get_async(
        organization_id=local.clerk_org_id, timeout_ms=30000
    )
    accounts = list(
        await db.scalars(
            select(models.User)
            .join(
                models.OrganizationMembership,
                models.OrganizationMembership.account_id == models.User.id,
            )
            .where(
                models.OrganizationMembership.organization_id == local_id,
                models.User.clerk_user_id.is_not(None),
            )
        )
    )
    local_users = {account.clerk_user_id for account in accounts}
    if local_users != await _provider_members(sdk, local.clerk_org_id):
        raise ValueError("Local and provider memberships do not match")
    actors = []
    for account in accounts:
        user = await sdk.users.get_async(user_id=account.clerk_user_id, timeout_ms=30000)
        email = _primary_email(user)
        if email != account.email:
            raise ValueError("Local and provider actor emails do not match")
        actors.append({"id": account.clerk_user_id, "email": email})
    return {
        "local_id": local_id,
        "clerk_id": provider.id,
        "creator_id": provider.created_by,
        "created_at": datetime.fromtimestamp(provider.created_at / 1000, UTC).isoformat(),
        "actors": actors,
        "active_jobs": await privacy.active_jobs(db, local_id),
    }


async def _export(db, local_id, destination, key, run_id):
    # Reuse the classified privacy export. Plaintext stays in a private temporary
    # directory and is removed before any provider deletion.
    with tempfile.TemporaryDirectory(prefix="cronos-private-export-") as directory:
        os.chmod(directory, 0o700)
        output = Path(directory) / "export.zip"
        privacy._write_export(output, await privacy._load_export_from_session(db, local_id))
        protect_export(destination, output.read_bytes(), key, run_id)


async def _remove_unshared_actor(db, sdk, actor, registry):
    user = await sdk.users.get_async(user_id=actor["id"], timeout_ms=30000)
    created = datetime.fromtimestamp(user.created_at / 1000, UTC)
    started = datetime.fromisoformat(registry["started_at"].replace("Z", "+00:00"))
    finished = datetime.fromisoformat(registry["finished_at"].replace("Z", "+00:00"))
    memberships = await sdk.users.get_organization_memberships_async(
        user_id=actor["id"], limit=1, timeout_ms=30000
    )
    local_membership = await db.scalar(
        select(models.OrganizationMembership.id)
        .join(models.User, models.User.id == models.OrganizationMembership.account_id)
        .where(models.User.clerk_user_id == actor["id"])
        .limit(1)
    )
    if _primary_email(user) != actor["email"] or not started <= created <= finished:
        raise ValueError("Actor creation does not belong to this run")
    if memberships.total_count is None:
        raise ValueError("Actor membership inventory is incomplete")
    if memberships.total_count or memberships.data or local_membership is not None:
        return False
    deleted = await sdk.users.delete_async(user_id=actor["id"], timeout_ms=30000)
    if deleted.id != actor["id"] or deleted.deleted is not True:
        raise ValueError("Provider actor deletion is unconfirmed")
    return True


async def cleanup(envelope, run_id, output_dir, *, execute=False, env=None, sdk=None):
    env = os.environ if env is None else env
    signing_key, artifact_key = validate_environment(env)
    registry = verify_registry(envelope, signing_key)
    # Validate the registry shape before IDs can reach either infrastructure.
    candidates = cleanup_targets(
        registry,
        run_id,
        {
            organization["local_id"]: {**organization, "active_jobs": []}
            for organization in registry.get("organizations", [])
        },
    )
    sdk = sdk or Clerk(bearer_auth=env["E2E_CLEANUP_CLERK_SECRET_KEY"])
    records = {organization["local_id"]: organization for organization in registry["organizations"]}
    completed = []
    removed_actors = []
    actors = {
        actor["id"]: actor for local_id, _ in candidates for actor in records[local_id]["actors"]
    }
    result = {
        "run_id": run_id,
        "status": "dry_run",
        "completed": completed,
        "removed_actors": removed_actors,
        "pending": [local_id for local_id, _ in candidates],
        "pending_actors": list(actors),
    }
    engine = create_async_engine(
        make_url(env["MIGRATION_DATABASE_URL"]).set(drivername="postgresql+asyncpg"),
        poolclass=NullPool,
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions.begin() as db:
            await db.execute(text("SET LOCAL row_security = off"))
            observed = {
                local_id: await _observe(db, sdk, records[local_id]) for local_id, _ in candidates
            }
            targets = cleanup_targets(registry, run_id, observed)
        if not execute:
            return result
        for local_id, clerk_id in targets:
            async with sessions.begin() as db:
                await db.execute(text("SET LOCAL row_security = off"))
                # FK checks for new jobs cannot cross this parent lock. Recheck
                # ownership and active jobs under it before external effects.
                await db.scalar(
                    select(models.Organization)
                    .where(models.Organization.id == local_id)
                    .with_for_update()
                )
                single = {**registry, "organizations": [records[local_id]]}
                cleanup_targets(
                    single, run_id, {local_id: await _observe(db, sdk, records[local_id])}
                )
                await _export(
                    db,
                    local_id,
                    Path(output_dir) / f"organization-{local_id}.zip.enc",
                    artifact_key,
                    run_id,
                )
                deleted = await sdk.organizations.delete_async(
                    organization_id=clerk_id, timeout_ms=30000
                )
                if deleted.id != clerk_id or deleted.deleted is not True:
                    raise ValueError("Provider organization deletion is unconfirmed")
                await privacy._erase_locked(
                    db, local_id, clerk_id, execute=True, provider_deleted=True
                )
            completed.append(local_id)
            result["pending"].remove(local_id)
        async with sessions.begin() as db:
            await db.execute(text("SET LOCAL row_security = off"))
            for actor in actors.values():
                if await _remove_unshared_actor(db, sdk, actor, registry):
                    removed_actors.append(actor["id"])
                result["pending_actors"].remove(actor["id"])
        result["status"] = "completed"
    except Exception as error:
        # Provider responses can contain secrets. Persist identities needing
        # reconciliation, never exception text or credentials.
        result.update(status="failed", failure_type=type(error).__name__)
    finally:
        await engine.dispose()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        result = asyncio.run(
            cleanup(json.load(sys.stdin), args.run_id, args.output_dir, execute=args.execute)
        )
    except Exception as error:
        result = {"status": "failed", "failure_type": type(error).__name__}
    print(json.dumps(result, separators=(",", ":")))
    raise SystemExit(0 if result["status"] in {"completed", "dry_run"} else 1)


if __name__ == "__main__":
    main()
