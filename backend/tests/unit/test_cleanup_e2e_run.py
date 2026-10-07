import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from scripts import cleanup_e2e_run


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


def test_export_refuses_invalid_key_before_creating_files(tmp_path):
    with pytest.raises(ValueError):
        cleanup_e2e_run.protect_export(tmp_path / "absent.enc", b"private", b"short", "run-1")
    assert list(tmp_path.iterdir()) == []


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
