import base64
import hashlib
import hmac
import io
import json
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from clerk_backend_api.models.sdkerror import SDKError
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from scripts import cleanup_e2e_run


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [404, 401, 403, 500])
async def test_missing_provider_requires_prior_ownership_and_current_local_accounts(
    monkeypatch, status
):
    actor = {
        "id": "user_Founder",
        "email": "admincronos100+run-1@gmail.com",
        "created_at": "2026-10-08T09:01:00.000Z",
    }
    ownership = {
        "local_id": 7,
        "clerk_id": "org_School",
        "creator_id": actor["id"],
        "created_at": "2026-10-08T09:02:00.000Z",
        "actors": [actor],
        "active_jobs": [],
    }
    response = httpx.Response(
        status, request=httpx.Request("GET", "https://api.clerk.com/v1/organizations/org_School")
    )
    error = SDKError("provider response", response)
    sdk = SimpleNamespace(organizations=SimpleNamespace(get_async=AsyncMock(side_effect=error)))
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(clerk_org_id="org_School")
    db.scalars.return_value = [SimpleNamespace(clerk_user_id=actor["id"], email=actor["email"])]
    monkeypatch.setattr(cleanup_e2e_run, "_observe_actor", AsyncMock(return_value=actor))
    monkeypatch.setattr(cleanup_e2e_run.privacy, "active_jobs", AsyncMock(return_value=["v1:99"]))
    if status != 404:
        with pytest.raises(SDKError):
            await cleanup_e2e_run._observe(db, sdk, ownership, prior_ownership=ownership)
        return
    observed = await cleanup_e2e_run._observe(db, sdk, ownership, prior_ownership=ownership)
    assert observed == {**ownership, "provider_deleted": True, "active_jobs": ["v1:99"]}
    with pytest.raises(SDKError):
        await cleanup_e2e_run._observe(db, sdk, ownership)
    with pytest.raises(ValueError, match="ownership"):
        await cleanup_e2e_run._observe(
            db, sdk, ownership, prior_ownership={**ownership, "clerk_id": "org_Foreign"}
        )
    db.scalars.return_value = []
    with pytest.raises(ValueError, match="membership"):
        await cleanup_e2e_run._observe(db, sdk, ownership, prior_ownership=ownership)


def test_cleanup_requires_separate_administrative_credentials_before_any_connection():
    for env in [
        {},
        {"DATABASE_URL": "postgresql://runtime/db"},
        {
            "MIGRATION_DATABASE_URL": "postgresql://owner/db",
            "CLERK_SECRET_KEY": "runtime-key",
        },
    ]:
        with pytest.raises(ValueError, match="administrative"):
            cleanup_e2e_run.validate_environment(env)


def test_export_encryption_uses_the_same_authenticated_envelope_as_browser_evidence(tmp_path):
    key = bytes(range(32))
    destination = tmp_path / "export.zip.enc"
    cleanup_e2e_run.protect_export(destination, b"private export", key, "run-1")
    envelope = json.loads(destination.read_bytes())
    aad = json.dumps(
        {"version": 1, "run_id": "run-1", "path": "export.zip"}, separators=(",", ":")
    ).encode()
    plaintext = AESGCM(key).decrypt(
        base64.b64decode(envelope["nonce"]),
        base64.b64decode(envelope["ciphertext"]) + base64.b64decode(envelope["tag"]),
        aad,
    )
    assert plaintext == b"private export"
    with pytest.raises(FileExistsError):
        cleanup_e2e_run.protect_export(destination, b"overwrite", key, "run-1")


@pytest.mark.parametrize("protected", [True, False])
def test_export_refuses_parent_traversal_before_creating_files(tmp_path, protected):
    destination = tmp_path / "nested" / ".." / "outside.zip.enc"
    with pytest.raises(ValueError, match="parent traversal"):
        if protected:
            cleanup_e2e_run.protect_export(destination, b"private", bytes(range(32)), "run-1")
        else:
            cleanup_e2e_run.privacy._write_export(destination, {"organization": [{"id": 7}]})
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("protected", [True, False])
def test_export_refuses_a_symbolic_parent_without_writing_to_its_target(tmp_path, protected):
    target = tmp_path / "foreign"
    target.mkdir()
    link = tmp_path / "exports"
    link.symlink_to(target, target_is_directory=True)
    destination = link / "export.zip"
    with pytest.raises(ValueError, match="symbolic link"):
        if protected:
            cleanup_e2e_run.protect_export(destination, b"private", bytes(range(32)), "run-1")
        else:
            cleanup_e2e_run.privacy._write_export(destination, {"organization": [{"id": 7}]})
    assert list(target.iterdir()) == []


def test_plain_export_is_private_exclusive_and_preserves_the_complete_archive(tmp_path):
    destination = tmp_path / "export.zip"
    data = {"organization": [{"id": 7, "name": "Private school"}]}
    cleanup_e2e_run.privacy._write_export(destination, data)
    assert destination.stat().st_mode & 0o777 == 0o600
    original = destination.read_bytes()
    with zipfile.ZipFile(destination) as archive:
        assert json.loads(archive.read("tables/organization.json")) == data["organization"]
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["tables"]["organization"]["count"] == 1
    with pytest.raises(FileExistsError):
        cleanup_e2e_run.privacy._write_export(destination, {"organization": []})
    assert destination.read_bytes() == original


def test_export_refuses_invalid_key_before_creating_files(tmp_path):
    with pytest.raises(ValueError):
        cleanup_e2e_run.protect_export(tmp_path / "absent.enc", b"private", b"short", "run-1")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_pre_deletion_export_authenticates_observed_ownership_without_changing_original_records(
    monkeypatch, tmp_path
):
    key = bytes(range(32))
    ownership = {
        "local_id": 7,
        "clerk_id": "org_School",
        "creator_id": "user_Founder",
        "created_at": "2026-10-08T09:02:00.000Z",
        "actors": [],
        "active_jobs": [],
    }
    original = {"organization": [{"id": 7, "name": "School", "clerk_org_id": "org_School"}]}
    monkeypatch.setattr(
        cleanup_e2e_run.privacy, "_load_export_from_session", AsyncMock(return_value=original)
    )
    path = tmp_path / "organization-7.zip.enc"
    await cleanup_e2e_run._export(AsyncMock(), 7, path, key, "run-1", ownership=ownership)
    assert cleanup_e2e_run.recover_export_ownership(path.read_bytes(), key, "run-1", 7) == ownership
    assert original == {"organization": [{"id": 7, "name": "School", "clerk_org_id": "org_School"}]}
    for run_id, local_id in [("foreign", 7), ("run-1", 8)]:
        with pytest.raises(InvalidTag):
            cleanup_e2e_run.recover_export_ownership(path.read_bytes(), key, run_id, local_id)
    envelope = json.loads(path.read_bytes())
    envelope["tag"] = base64.b64encode(bytes(16)).decode()
    with pytest.raises(InvalidTag):
        cleanup_e2e_run.recover_export_ownership(json.dumps(envelope).encode(), key, "run-1", 7)


def test_export_ownership_rejects_authenticated_content_without_an_intact_scope_manifest(tmp_path):
    key = bytes(range(32))
    ownership = {"local_id": 7, "clerk_id": "org_School"}
    valid = {
        "organization": [{"id": 7, "clerk_org_id": "org_School"}],
        "e2e_ownership": [{"run_id": "run-1", "organization": ownership}],
    }
    for index, data in enumerate(
        [
            {},
            {**valid, "organization": [{"id": 8}]},
            {**valid, "e2e_ownership": [{"run_id": "foreign", "organization": ownership}]},
        ]
    ):
        path = tmp_path / str(index) / "organization-7.zip.enc"
        cleanup_e2e_run._protect_export_data(data, path, key, "run-1")
        with pytest.raises(ValueError):
            cleanup_e2e_run.recover_export_ownership(path.read_bytes(), key, "run-1", 7)
    original = tmp_path / "original.zip"
    cleanup_e2e_run.privacy._write_export(original, valid)
    raw = io.BytesIO()
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(raw, "w") as changed:
        for name in source.namelist():
            changed.writestr(
                name, b"[]" if name == "tables/organization.json" else source.read(name)
            )
    path = tmp_path / "changed" / "organization-7.zip.enc"
    cleanup_e2e_run.protect_export(path, raw.getvalue(), key, "run-1")
    with pytest.raises(ValueError, match="integrity"):
        cleanup_e2e_run.recover_export_ownership(path.read_bytes(), key, "run-1", 7)


@pytest.mark.asyncio
@pytest.mark.parametrize("local_membership,provider_count", [(17, 0), (None, 1), (None, None)])
async def test_cleanup_preserves_shared_accounts_and_refuses_unknown_memberships(
    local_membership, provider_count
):
    db = AsyncMock()
    db.scalar.return_value = local_membership
    actor = {"id": "user_owned", "email": "admincronos100+run-1@gmail.com"}
    sdk = SimpleNamespace(
        users=SimpleNamespace(
            get_async=AsyncMock(
                return_value=SimpleNamespace(
                    id=actor["id"],
                    created_at=1791360600000,
                    primary_email_address_id="email_1",
                    email_addresses=[SimpleNamespace(id="email_1", email_address=actor["email"])],
                )
            ),
            get_organization_memberships_async=AsyncMock(
                return_value=SimpleNamespace(total_count=provider_count, data=[])
            ),
            delete_async=AsyncMock(),
        )
    )
    registry = {"started_at": "2026-10-07T08:00:00Z", "finished_at": "2026-10-07T09:00:00Z"}
    if provider_count is None:
        with pytest.raises(ValueError, match="incomplete"):
            await cleanup_e2e_run._remove_unshared_actor(db, sdk, actor, registry)
    else:
        assert await cleanup_e2e_run._remove_unshared_actor(db, sdk, actor, registry) is False
    sdk.users.delete_async.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_root_actor_is_rejected_before_database_connection(monkeypatch, tmp_path):
    key = bytes(range(32))
    registry = {
        "schema_version": 1,
        "run_id": "run-1",
        "started_at": "2026-10-07T08:00:00Z",
        "finished_at": "2026-10-07T09:00:00Z",
        "organizations": [],
        "actors": [
            {
                "id": "user_customer",
                "email": "customer@example.com",
                "created_at": "2026-10-07T08:05:00Z",
                "creation_run_id": "run-1",
                "provenance": "ui",
                "type": "disposable",
            }
        ],
    }
    payload = json.dumps(registry).encode()
    envelope = {
        "version": 1,
        "payload": base64.b64encode(payload).decode(),
        "signature": hmac.new(key, payload, hashlib.sha256).hexdigest(),
    }
    environment = {
        "MIGRATION_DATABASE_URL": "postgresql://owner:test@localhost/test",
        "E2E_CLEANUP_CLERK_SECRET_KEY": "test-administrative-key",
        "E2E_REGISTRY_HMAC_KEY": base64.b64encode(key).decode(),
        "E2E_ARTIFACT_KEY": base64.b64encode(key).decode(),
    }

    def forbidden_connection(*args, **kwargs):
        raise AssertionError("An invalid actor reached the database")

    monkeypatch.setattr(cleanup_e2e_run, "create_async_engine", forbidden_connection)
    with pytest.raises(ValueError, match="aliases"):
        await cleanup_e2e_run.cleanup(
            envelope, "run-1", tmp_path, execute=True, env=environment, sdk=SimpleNamespace()
        )


@pytest.mark.asyncio
async def test_unexported_local_actor_data_prevents_provider_account_deletion():
    actor = {"id": "user_orphan", "email": "admincronos100+run-1@gmail.com"}
    db = AsyncMock()
    db.scalar.side_effect = [None, 42]
    sdk = SimpleNamespace(
        users=SimpleNamespace(
            get_async=AsyncMock(
                return_value=SimpleNamespace(
                    id=actor["id"],
                    created_at=1791360600000,
                    primary_email_address_id="email_1",
                    email_addresses=[SimpleNamespace(id="email_1", email_address=actor["email"])],
                )
            ),
            get_organization_memberships_async=AsyncMock(
                return_value=SimpleNamespace(total_count=0, data=[])
            ),
            delete_async=AsyncMock(return_value=SimpleNamespace(id=actor["id"], deleted=True)),
        )
    )
    registry = {"started_at": "2026-10-07T08:00:00Z", "finished_at": "2026-10-07T09:00:00Z"}
    with pytest.raises(ValueError, match="Local actor"):
        await cleanup_e2e_run._remove_unshared_actor(db, sdk, actor, registry)
    sdk.users.delete_async.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("export_fails", [False, True])
async def test_export_only_never_deletes_provider_or_local_data(
    monkeypatch, tmp_path, export_fails
):
    key = bytes(range(32))
    school = {"local_id": 7, "clerk_id": "org_School", "actors": []}
    registry = {"organizations": [school], "actors": []}
    db = AsyncMock()
    transaction = AsyncMock()
    transaction.__aenter__.return_value = db
    sessions = SimpleNamespace(begin=Mock(return_value=transaction))
    engine = SimpleNamespace(dispose=AsyncMock())
    sdk = SimpleNamespace(organizations=SimpleNamespace(delete_async=AsyncMock()))
    monkeypatch.setattr(cleanup_e2e_run, "validate_environment", lambda env: (key, key))
    monkeypatch.setattr(cleanup_e2e_run, "verify_registry", lambda envelope, key: registry)
    targets = Mock(return_value=[(7, "org_School")])
    monkeypatch.setattr(cleanup_e2e_run, "cleanup_targets", targets)
    monkeypatch.setattr(cleanup_e2e_run, "cleanup_actor_targets", Mock(return_value=[]))
    monkeypatch.setattr(cleanup_e2e_run, "create_async_engine", Mock(return_value=engine))
    monkeypatch.setattr(cleanup_e2e_run, "async_sessionmaker", Mock(return_value=sessions))
    monkeypatch.setattr(cleanup_e2e_run, "_observe", AsyncMock(return_value=school))
    export = AsyncMock(side_effect=OSError("private export failure") if export_fails else None)
    erase = AsyncMock()
    actors = AsyncMock()
    monkeypatch.setattr(cleanup_e2e_run, "_export", export)
    monkeypatch.setattr(cleanup_e2e_run.privacy, "_erase_locked", erase)
    monkeypatch.setattr(cleanup_e2e_run, "_remove_unshared_actor", actors)
    result = await cleanup_e2e_run.cleanup(
        {},
        "run-1",
        tmp_path,
        export_only=True,
        env={"MIGRATION_DATABASE_URL": "postgresql://owner:test@localhost/test"},
        sdk=sdk,
    )
    assert result["status"] == ("failed" if export_fails else "exported")
    assert result["completed"] == []
    assert result["removed_actors"] == []
    assert result["pending"] == [7]
    if not export_fails:
        assert result["exported"] == [7]
    assert targets.call_count == 3
    export.assert_awaited_once_with(
        db, 7, tmp_path / "organization-7.zip.enc", key, "run-1", ownership=school
    )
    sdk.organizations.delete_async.assert_not_awaited()
    erase.assert_not_awaited()
    actors.assert_not_awaited()
    engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_export_only_and_execute_are_mutually_exclusive_before_any_connection():
    with pytest.raises(ValueError, match="exclusive"):
        await cleanup_e2e_run.cleanup({}, "run-1", ".", execute=True, export_only=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("prior_exports", [{7: b"tampered"}, {8: b"foreign"}, "invalid"])
async def test_prior_exports_are_authenticated_and_scoped_before_database_connection(
    monkeypatch, tmp_path, prior_exports
):
    key = bytes(range(32))
    school = {"local_id": 7, "clerk_id": "org_School", "actors": []}
    registry = {"organizations": [school], "actors": []}
    monkeypatch.setattr(cleanup_e2e_run, "validate_environment", lambda env: (key, key))
    monkeypatch.setattr(cleanup_e2e_run, "verify_registry", lambda envelope, key: registry)
    monkeypatch.setattr(cleanup_e2e_run, "cleanup_targets", Mock(return_value=[(7, "org_School")]))
    monkeypatch.setattr(cleanup_e2e_run, "cleanup_actor_targets", Mock(return_value=[]))
    connection = Mock(side_effect=AssertionError("An invalid export reached the database"))
    monkeypatch.setattr(cleanup_e2e_run, "create_async_engine", connection)
    with pytest.raises(ValueError):
        await cleanup_e2e_run.cleanup(
            {},
            "run-1",
            tmp_path,
            execute=True,
            prior_exports=prior_exports,
            env={},
            sdk=SimpleNamespace(),
        )
    connection.assert_not_called()


@pytest.mark.asyncio
async def test_reconciliation_preserves_prior_backup_and_erases_only_after_confirmed_provider_404(
    monkeypatch, tmp_path
):
    key = bytes(range(32))
    actor = {
        "id": "user_Founder",
        "email": "admincronos100+run-1@gmail.com",
        "created_at": "2026-10-08T09:01:00.000Z",
    }
    ownership = {
        "local_id": 7,
        "clerk_id": "org_School",
        "creator_id": actor["id"],
        "created_at": "2026-10-08T09:02:00.000Z",
        "actors": [actor],
        "active_jobs": [],
    }
    school = {**ownership, "type": "disposable", "provenance": "ui", "creation_run_id": "run-1"}
    registry = {
        "schema_version": 1,
        "run_id": "run-1",
        "started_at": "2026-10-08T09:00:00.000Z",
        "finished_at": "2026-10-08T09:03:00.000Z",
        "organizations": [school],
        "actors": [],
    }
    path = tmp_path / "before" / "organization-7.zip.enc"
    cleanup_e2e_run._protect_export_data(
        {
            "organization": [{"id": 7, "clerk_org_id": "org_School"}],
            "e2e_ownership": [{"run_id": "run-1", "organization": ownership}],
        },
        path,
        key,
        "run-1",
    )
    backup = path.read_bytes()
    monkeypatch.setattr(cleanup_e2e_run, "validate_environment", lambda env: (key, key))
    monkeypatch.setattr(cleanup_e2e_run, "verify_registry", lambda envelope, key: registry)
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(clerk_org_id="org_School")
    db.scalars.return_value = [SimpleNamespace(clerk_user_id=actor["id"], email=actor["email"])]
    transaction = AsyncMock()
    transaction.__aenter__.return_value = db
    engine = SimpleNamespace(dispose=AsyncMock())
    monkeypatch.setattr(cleanup_e2e_run, "create_async_engine", Mock(return_value=engine))
    monkeypatch.setattr(
        cleanup_e2e_run,
        "async_sessionmaker",
        Mock(return_value=SimpleNamespace(begin=Mock(return_value=transaction))),
    )
    response = httpx.Response(
        404, request=httpx.Request("GET", "https://api.clerk.com/v1/organizations/org_School")
    )
    sdk = SimpleNamespace(
        organizations=SimpleNamespace(
            get_async=AsyncMock(side_effect=SDKError("missing", response)), delete_async=AsyncMock()
        )
    )
    monkeypatch.setattr(cleanup_e2e_run, "_observe_actor", AsyncMock(return_value=actor))
    monkeypatch.setattr(cleanup_e2e_run.privacy, "active_jobs", AsyncMock(return_value=[]))
    erase = AsyncMock()
    monkeypatch.setattr(cleanup_e2e_run.privacy, "_erase_locked", erase)
    monkeypatch.setattr(cleanup_e2e_run, "_remove_unshared_actor", AsyncMock(return_value=False))
    result = await cleanup_e2e_run.cleanup(
        {},
        "run-1",
        tmp_path / "after",
        execute=True,
        prior_exports={7: backup},
        env={"MIGRATION_DATABASE_URL": "postgresql://owner:test@localhost/test"},
        sdk=sdk,
    )
    assert result["status"] == "completed"
    assert result["completed"] == [7]
    assert result["pending"] == []
    assert (tmp_path / "after" / "organization-7.zip.enc").read_bytes() == backup
    sdk.organizations.delete_async.assert_not_awaited()
    erase.assert_awaited_once_with(db, 7, "org_School", execute=True, provider_deleted=True)
