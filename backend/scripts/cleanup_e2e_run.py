"""Administrative cleanup of signed, UI-created disposable campaign schools.

Accept the signed registry on stdin. Never grant the browser database privileges.
"""

import argparse
import asyncio
import base64
import hashlib
import io
import json
import os
import sys
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from clerk_backend_api import Clerk
from clerk_backend_api.models.clerkbaseerror import ClerkBaseError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import models
from scripts import privacy
from scripts.e2e_cleanup_policy import cleanup_actor_targets, cleanup_targets, verify_registry


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
    _write_protected_export(destination, json.dumps(envelope, separators=(",", ":")).encode())


def _write_protected_export(destination, content):
    with privacy.open_private_export(destination) as output:
        output.write(content)
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


async def _observe(db, sdk, organization, *, prior_ownership=None):
    local_id = organization["local_id"]
    local = await db.get(models.Organization, local_id)
    if local is None or local.clerk_org_id != organization["clerk_id"]:
        raise ValueError("Live local organization identity does not match")
    try:
        provider = await sdk.organizations.get_async(
            organization_id=local.clerk_org_id, timeout_ms=30000
        )
    except ClerkBaseError as error:
        if error.status_code != 404 or prior_ownership is None:
            raise
        if (
            prior_ownership.get("local_id") != local_id
            or prior_ownership.get("clerk_id") != local.clerk_org_id
        ):
            raise ValueError("Prior ownership does not match the local organization") from error
        provider = None
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
    if provider is not None and local_users != await _provider_members(sdk, local.clerk_org_id):
        raise ValueError("Local and provider memberships do not match")
    actors = []
    for account in accounts:
        actor = await _observe_actor(sdk, account.clerk_user_id)
        if actor["id"] != account.clerk_user_id or actor["email"] != account.email:
            raise ValueError("Local and provider actor emails do not match")
        actors.append(actor)
    if provider is None:

        def identities(rows):
            return {
                actor["id"]: (actor["email"], datetime.fromisoformat(actor["created_at"]))
                for actor in rows
            }

        previous = prior_ownership.get("actors", [])
        if len(previous) != len(local_users) or identities(previous) != identities(actors):
            raise ValueError("Prior provider membership does not match current local accounts")
        return {
            **prior_ownership,
            "actors": actors,
            "provider_deleted": True,
            "active_jobs": await privacy.active_jobs(db, local_id),
        }
    return {
        "local_id": local_id,
        "clerk_id": provider.id,
        "creator_id": provider.created_by,
        "created_at": datetime.fromtimestamp(provider.created_at / 1000, UTC).isoformat(),
        "actors": actors,
        "active_jobs": await privacy.active_jobs(db, local_id),
    }


async def _observe_actor(sdk, user_id):
    user = await sdk.users.get_async(user_id=user_id, timeout_ms=30000)
    return {
        "id": user.id,
        "email": _primary_email(user),
        "created_at": datetime.fromtimestamp(user.created_at / 1000, UTC).isoformat(),
    }


def _protect_export_data(data, destination, key, run_id):
    # Reuse the classified privacy export. Plaintext stays in a private temporary
    # directory and is removed before any provider deletion.
    with tempfile.TemporaryDirectory(prefix="cronos-private-export-") as directory:
        os.chmod(directory, 0o700)
        output = Path(directory) / "export.zip"
        privacy._write_export(output, data)
        protect_export(destination, output.read_bytes(), key, run_id)


def _verified_archive_tables(plaintext):
    limit = 64 * 1024 * 1024
    if len(plaintext) > limit:
        raise ValueError("Pre-deletion archive exceeds limit")
    with zipfile.ZipFile(io.BytesIO(plaintext)) as archive:
        names = archive.namelist()
        if (
            len(names) != len(set(names))
            or sum(item.file_size for item in archive.infolist()) > limit
        ):
            raise ValueError("Invalid pre-deletion archive inventory")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format") != "cronos-privacy-export-v1" or not isinstance(
            manifest.get("tables"), dict
        ):
            raise ValueError("Invalid pre-deletion archive manifest")
        tables = {}
        expected = {"manifest.json"}
        for name, metadata in manifest["tables"].items():
            filename = f"tables/{name}.json"
            if not isinstance(metadata, dict) or metadata.get("file") != filename:
                raise ValueError("Invalid pre-deletion table identity")
            expected.add(filename)
            payload = archive.read(filename)
            rows = json.loads(payload)
            if (
                hashlib.sha256(payload).hexdigest() != metadata.get("sha256")
                or not isinstance(rows, list)
                or any(not isinstance(row, dict) for row in rows)
                or type(metadata.get("count")) is not int
                or len(rows) != metadata["count"]
            ):
                raise ValueError("Pre-deletion table integrity mismatch")
            tables[name] = rows
        if set(names) != expected:
            raise ValueError("Unexpected pre-deletion archive content")
    return tables


def recover_export_ownership(content, key, run_id, local_id):
    """Authenticate the complete classified archive before trusting its ownership receipt."""
    envelope = json.loads(content)
    if (
        not isinstance(envelope, dict)
        or type(envelope.get("version")) is not int
        or envelope["version"] != 1
    ):
        raise ValueError("Invalid pre-deletion export envelope")
    aad = json.dumps(
        {"version": 1, "run_id": run_id, "path": f"organization-{local_id}.zip"},
        separators=(",", ":"),
    ).encode()
    plaintext = AESGCM(key).decrypt(
        base64.b64decode(envelope["nonce"], validate=True),
        base64.b64decode(envelope["ciphertext"], validate=True)
        + base64.b64decode(envelope["tag"], validate=True),
        aad,
    )
    tables = _verified_archive_tables(plaintext)
    organizations = tables.get("organization", [])
    receipts = tables.get("e2e_ownership", [])
    if len(organizations) != 1 or organizations[0].get("id") != local_id or len(receipts) != 1:
        raise ValueError("Pre-deletion organization identity mismatch")
    receipt = receipts[0]
    ownership = receipt.get("organization")
    if (
        receipt.get("run_id") != run_id
        or not isinstance(ownership, dict)
        or ownership.get("local_id") != local_id
        or ownership.get("clerk_id") != organizations[0].get("clerk_org_id")
    ):
        raise ValueError("Pre-deletion ownership scope mismatch")
    return ownership


async def _export(db, local_id, destination, key, run_id, *, ownership=None):
    data = await privacy._load_export_from_session(db, local_id)
    if ownership is not None:
        if "e2e_ownership" in data:
            raise ValueError("Pre-deletion ownership receipt already exists")
        data = {**data, "e2e_ownership": [{"run_id": run_id, "organization": ownership}]}
    _protect_export_data(data, destination, key, run_id)
    if ownership is not None:
        recover_export_ownership(Path(destination).read_bytes(), key, run_id, local_id)


async def _remove_unshared_actor(db, sdk, actor, registry, before_delete=None):
    current = await _observe_actor(sdk, actor["id"])
    created = datetime.fromisoformat(current["created_at"])
    started = datetime.fromisoformat(registry["started_at"])
    finished = datetime.fromisoformat(registry["finished_at"])
    memberships = await sdk.users.get_organization_memberships_async(
        user_id=actor["id"], limit=1, timeout_ms=30000
    )
    local_membership = await db.scalar(
        select(models.OrganizationMembership.id)
        .join(models.User, models.User.id == models.OrganizationMembership.account_id)
        .where(models.User.clerk_user_id == actor["id"])
        .limit(1)
    )
    if (
        current["id"] != actor["id"]
        or current["email"] != actor["email"]
        or not started <= created <= finished
        or (actor.get("created_at") and created != datetime.fromisoformat(actor["created_at"]))
    ):
        raise ValueError("Actor creation does not belong to this run")
    if memberships.total_count is None:
        raise ValueError("Actor membership inventory is incomplete")
    if memberships.total_count or memberships.data or local_membership is not None:
        return False
    local_actor = await db.scalar(
        select(models.User.id).where(models.User.clerk_user_id == actor["id"]).limit(1)
    )
    if local_actor is not None:
        raise ValueError("Local actor data must be exported and erased before provider deletion")
    if before_delete is not None:
        before_delete(current)
    deleted = await sdk.users.delete_async(user_id=actor["id"], timeout_ms=30000)
    if deleted.id != actor["id"] or deleted.deleted is not True:
        raise ValueError("Provider actor deletion is unconfirmed")
    return True


async def cleanup(
    envelope,
    run_id,
    output_dir,
    *,
    execute=False,
    export_only=False,
    prior_exports=None,
    env=None,
    sdk=None,
):
    if execute and export_only:
        raise ValueError("Export-only and deletion are mutually exclusive")
    env = os.environ if env is None else env
    signing_key, artifact_key = validate_environment(env)
    registry = verify_registry(envelope, signing_key)
    # Validate the registry shape before IDs can reach either infrastructure.
    candidates = cleanup_targets(
        registry,
        run_id,
        {
            # This first pass validates signed input only. Every timestamp is
            # replaced with the provider observation before any deletion.
            organization["local_id"]: {
                **organization,
                "actors": [
                    {**actor, "created_at": organization.get("created_at")}
                    for actor in organization.get("actors", [])
                ],
                "active_jobs": [],
            }
            for organization in registry.get("organizations", [])
        },
    )
    root_actors = {actor["id"]: actor for actor in registry.get("actors", [])}
    cleanup_actor_targets(registry, run_id, root_actors)
    prior_exports = {} if prior_exports is None else prior_exports
    candidate_ids = {local_id for local_id, _ in candidates}
    if not isinstance(prior_exports, dict) or any(
        type(local_id) is not int or local_id not in candidate_ids or not isinstance(content, bytes)
        for local_id, content in prior_exports.items()
    ):
        raise ValueError("Prior exports must belong to this disposable run")
    prior_ownership = {
        local_id: recover_export_ownership(content, artifact_key, run_id, local_id)
        for local_id, content in prior_exports.items()
    }
    if prior_ownership:
        cleanup_targets(
            {
                **registry,
                "organizations": [
                    school
                    for school in registry["organizations"]
                    if school["local_id"] in prior_ownership
                ],
            },
            run_id,
            prior_ownership,
        )
    sdk = sdk or Clerk(bearer_auth=env["E2E_CLEANUP_CLERK_SECRET_KEY"])
    records = {organization["local_id"]: organization for organization in registry["organizations"]}
    completed = []
    removed_actors = []
    actors = {
        actor["id"]: actor for local_id, _ in candidates for actor in records[local_id]["actors"]
    }
    orphan_actors = set(root_actors) - set(actors)
    for actor_id, actor in root_actors.items():
        if actor_id in actors and actors[actor_id]["email"] != actor["email"]:
            raise ValueError("Conflicting actor identities in registry")
        actors[actor_id] = actor
    result = {
        "run_id": run_id,
        "status": "dry_run",
        "completed": completed,
        "removed_actors": removed_actors,
        "pending": [local_id for local_id, _ in candidates],
        "pending_actors": list(actors),
    }
    if export_only:
        result["exported"] = []
    engine = create_async_engine(
        make_url(env["MIGRATION_DATABASE_URL"]).set(drivername="postgresql+asyncpg"),
        poolclass=NullPool,
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions.begin() as db:
            await db.execute(text("SET LOCAL row_security = off"))
            observed = {
                local_id: await _observe(
                    db, sdk, records[local_id], prior_ownership=prior_ownership.get(local_id)
                )
                for local_id, _ in candidates
            }
            targets = cleanup_targets(registry, run_id, observed)
            cleanup_actor_targets(
                registry,
                run_id,
                {actor_id: await _observe_actor(sdk, actor_id) for actor_id in root_actors},
            )
        if not execute and not export_only:
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
                ownership = await _observe(
                    db, sdk, records[local_id], prior_ownership=prior_ownership.get(local_id)
                )
                cleanup_targets(single, run_id, {local_id: ownership})
                destination = Path(output_dir) / f"organization-{local_id}.zip.enc"
                if ownership.get("provider_deleted") is True:
                    if local_id not in prior_exports:
                        raise ValueError("Missing authenticated pre-deletion backup")
                    _write_protected_export(destination, prior_exports[local_id])
                else:
                    await _export(
                        db, local_id, destination, artifact_key, run_id, ownership=ownership
                    )
                if export_only:
                    result["exported"].append(local_id)
                    continue
                if ownership.get("provider_deleted") is not True:
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
        if export_only:
            result["status"] = "exported"
            return result
        async with sessions.begin() as db:
            await db.execute(text("SET LOCAL row_security = off"))
            for actor in actors.values():

                def export_actor(current):
                    _protect_export_data(
                        {"clerk_actor": [current]},
                        Path(output_dir) / f"actor-{current['id']}.zip.enc",
                        artifact_key,
                        run_id,
                    )

                if await _remove_unshared_actor(
                    db,
                    sdk,
                    actor,
                    registry,
                    before_delete=export_actor if actor["id"] in orphan_actors else None,
                ):
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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--export-only", action="store_true")
    args = parser.parse_args()
    try:
        result = asyncio.run(
            cleanup(
                json.load(sys.stdin),
                args.run_id,
                args.output_dir,
                execute=args.execute,
                export_only=args.export_only,
            )
        )
    except Exception as error:
        result = {"status": "failed", "failure_type": type(error).__name__}
    print(json.dumps(result, separators=(",", ":")))
    raise SystemExit(0 if result["status"] in {"completed", "dry_run", "exported"} else 1)


if __name__ == "__main__":
    main()
