import base64
import hashlib
import hmac
import io
import json
import os
import zipfile
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select, text

from app import models
from app.scheduler.domain.demand import ExecutionEntry, ModuleCredit
from app.scheduler.infrastructure.models import CurricularExecution, SchedulerJobV1
from app.scheduler.infrastructure.progress import record_execution
from scripts import cleanup_e2e_run, privacy
from tests._support.db_fixtures import (
    TestingSessionLocal,
    create_completed_organization,
    create_teacher_profile,
    runtime_sync_test_engine,
)
from tests._support.scheduler_v1 import seed_v1_assignment

pytestmark = pytest.mark.postgresql


@pytest.mark.asyncio
async def test_administrative_erasure_removes_append_only_evidence(db_session):
    seed = await seed_v1_assignment(
        db_session, clerk_user_id="w02_rgpd_a", clerk_org_id="w02_rgpd_org_a"
    )
    await record_execution(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        ExecutionEntry(
            "lesson:1",
            1,
            seed.membership.id,
            "Confirmed",
            (ModuleCredit(seed.module.id, 50),),
            recorded_at=datetime(2026, 9, 23, 12, tzinfo=UTC),
        ),
        planning_relevant=False,
    )
    await db_session.commit()

    with runtime_sync_test_engine.connect() as connection:
        can_delete = connection.scalar(
            text(
                "SELECT has_table_privilege('cronos_app', 'public.curricular_execution', 'DELETE')"
            )
        )
    assert can_delete is False

    result = await privacy._erase(
        seed.organization.id,
        seed.organization.clerk_org_id,
        execute=True,
        provider_deleted=True,
    )

    assert result["dry_run"] is False
    async with TestingSessionLocal() as session:
        remaining = (
            await session.scalars(
                select(CurricularExecution).where(
                    CurricularExecution.organization_id == seed.organization.id
                )
            )
        ).all()
    assert remaining == []


@pytest.mark.asyncio
async def test_dry_run_reports_counts_without_deleting(db_session):
    seed = await seed_v1_assignment(
        db_session, clerk_user_id="w02_rgpd_b", clerk_org_id="w02_rgpd_org_b"
    )
    await record_execution(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        ExecutionEntry(
            "lesson:1",
            1,
            seed.membership.id,
            "Confirmed",
            (ModuleCredit(seed.module.id, 50),),
            recorded_at=datetime(2026, 9, 23, 12, tzinfo=UTC),
        ),
        planning_relevant=False,
    )
    await db_session.commit()

    result = await privacy._erase(
        seed.organization.id,
        seed.organization.clerk_org_id,
        execute=False,
        provider_deleted=False,
    )

    assert result["dry_run"] is True
    assert result["counts"]["curricular_execution"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "generation,status",
    [
        ("v1", "QUEUED"),
        ("v1", "RUNNING"),
        ("v1", "VALIDATING"),
        ("legacy", "QUEUED"),
        ("legacy", "RUNNING"),
        ("legacy", "CANCEL_REQUESTED"),
    ],
)
async def test_erasure_refuses_each_active_job_state_without_changing_the_tenant(
    db_session, generation, status
):
    seed = await seed_v1_assignment(
        db_session, clerk_org_id=f"privacy_active_{generation}_{status}"
    )
    if generation == "v1":
        job = SchedulerJobV1(
            organization_id=seed.organization.id,
            school_year_id=seed.year.id,
            strategy="COMPLETE_GENERATION",
            status=status,
            origin="privacy-active",
            revision=1,
            queued_at=datetime.now(UTC),
        )
    else:
        job = models.ScheduleGenerationJob(
            organization_id=seed.organization.id,
            school_year_id=seed.year.id,
            strategy=models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
            trigger_type=models.ScheduleGenerationTrigger.FIRST_GENERATION,
            idempotency_key="privacy-active",
            job_status=models.ScheduleGenerationJobStatus(status),
        )
    db_session.add(job)
    await db_session.commit()
    with pytest.raises(ValueError, match="active jobs"):
        await privacy._erase(seed.organization.id, seed.organization.clerk_org_id, True, True)
    async with TestingSessionLocal() as db:
        organization = await db.get(models.Organization, seed.organization.id)
        assert organization.clerk_org_id == seed.organization.clerk_org_id
        assert await db.get(type(job), job.id) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["dry_run", "completed", "unconfirmed"])
async def test_privacy_campaign_cleanup_exports_before_provider_deletion_and_commits_last(
    db_session, tmp_path, mode
):
    organization, user = await create_completed_organization(
        db_session, clerk_org_id="org_campaign", clerk_user_id="user_campaign"
    )
    user.email = "admincronos100+run-1@gmail.com"
    await create_teacher_profile(db_session, organization_id=organization.id)
    year = models.SchedulerSchoolYear(
        organization_id=organization.id,
        label="2026/27",
        start_date=date(2026, 9, 1),
        hard_end_date=date(2027, 7, 31),
    )
    db_session.add(year)
    await db_session.commit()
    key = bytes(range(32))
    created = datetime(2026, 10, 7, 8, 10, tzinfo=UTC)
    actor = {"id": user.clerk_user_id, "email": user.email}
    registry = {
        "schema_version": 1,
        "run_id": "run-1",
        "started_at": "2026-10-07T08:00:00Z",
        "finished_at": "2026-10-07T09:00:00Z",
        "organizations": [
            {
                "local_id": organization.id,
                "clerk_id": organization.clerk_org_id,
                "type": "disposable",
                "creation_run_id": "run-1",
                "created_at": created.isoformat(),
                "provenance": "ui",
                "creator_id": user.clerk_user_id,
                "actors": [actor],
            }
        ],
    }
    payload = json.dumps(registry).encode()
    envelope = {
        "version": 1,
        "payload": base64.b64encode(payload).decode(),
        "signature": hmac.new(key, payload, hashlib.sha256).hexdigest(),
    }
    provider_user = SimpleNamespace(
        id=user.clerk_user_id,
        created_at=int(created.timestamp() * 1000),
        primary_email_address_id="email_1",
        email_addresses=[SimpleNamespace(id="email_1", email_address=user.email)],
    )

    async def delete_provider(**kwargs):
        encrypted_path = tmp_path / f"organization-{organization.id}.zip.enc"
        assert encrypted_path.is_file()
        assert not list(tmp_path.glob("*.zip"))
        protected = json.loads(encrypted_path.read_bytes())
        aad = json.dumps(
            {"version": 1, "run_id": "run-1", "path": encrypted_path.name.removesuffix(".enc")},
            separators=(",", ":"),
        ).encode()
        exported = AESGCM(key).decrypt(
            base64.b64decode(protected["nonce"]),
            base64.b64decode(protected["ciphertext"]) + base64.b64decode(protected["tag"]),
            aad,
        )
        with zipfile.ZipFile(io.BytesIO(exported)) as archive:
            assert json.loads(archive.read("manifest.json"))["tables"]["organization"]["count"] == 1
        # A competing job cannot enter while provider deletion is in progress.
        async with TestingSessionLocal() as competing:
            await competing.execute(text("SET LOCAL lock_timeout = '100ms'"))
            competing.add(
                SchedulerJobV1(
                    organization_id=organization.id,
                    school_year_id=year.id,
                    strategy="COMPLETE_GENERATION",
                    status="QUEUED",
                    origin="cleanup-race",
                    revision=1,
                    queued_at=created,
                )
            )
            from sqlalchemy.exc import DBAPIError

            with pytest.raises(DBAPIError) as blocked:
                await competing.flush()
            assert blocked.value.orig.sqlstate == "55P03"
            await competing.rollback()
        return SimpleNamespace(id=kwargs["organization_id"], deleted=mode != "unconfirmed")

    sdk = SimpleNamespace(
        organizations=SimpleNamespace(
            get_async=AsyncMock(
                return_value=SimpleNamespace(
                    id=organization.clerk_org_id,
                    created_at=int(created.timestamp() * 1000),
                    created_by=user.clerk_user_id,
                )
            ),
            delete_async=AsyncMock(side_effect=delete_provider),
        ),
        organization_memberships=SimpleNamespace(
            list_async=AsyncMock(
                return_value=SimpleNamespace(
                    total_count=1,
                    data=[
                        SimpleNamespace(
                            public_user_data=SimpleNamespace(user_id=user.clerk_user_id)
                        )
                    ],
                )
            )
        ),
        users=SimpleNamespace(
            get_async=AsyncMock(return_value=provider_user),
            get_organization_memberships_async=AsyncMock(
                return_value=SimpleNamespace(total_count=0, data=[])
            ),
            delete_async=AsyncMock(
                return_value=SimpleNamespace(id=user.clerk_user_id, deleted=True)
            ),
        ),
    )
    environment = {
        **os.environ,
        "E2E_CLEANUP_CLERK_SECRET_KEY": "test-administrative-key",
        "E2E_REGISTRY_HMAC_KEY": base64.b64encode(key).decode(),
        "E2E_ARTIFACT_KEY": base64.b64encode(key).decode(),
    }
    result = await cleanup_e2e_run.cleanup(
        envelope, "run-1", tmp_path, execute=mode != "dry_run", env=environment, sdk=sdk
    )
    assert result["status"] == ("failed" if mode == "unconfirmed" else mode)
    async with TestingSessionLocal() as session:
        current = await session.get(models.Organization, organization.id)
        if mode == "completed":
            assert current.clerk_org_id is None
            assert result["pending"] == []
            sdk.users.delete_async.assert_awaited_once()
        else:
            assert current.clerk_org_id == organization.clerk_org_id
            sdk.users.delete_async.assert_not_awaited()
    if mode == "dry_run":
        sdk.organizations.delete_async.assert_not_awaited()
        assert list(tmp_path.iterdir()) == []
    else:
        sdk.organizations.delete_async.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["dry_run", "completed", "unconfirmed", "local_data"])
async def test_privacy_root_actor_cleanup_is_protected_before_any_school_exists(
    db_session, tmp_path, mode
):
    key = bytes(range(32))
    created = datetime(2026, 10, 7, 8, 10, tzinfo=UTC)
    actor = {
        "id": "user_orphan",
        "email": "admincronos100+run-1@gmail.com",
        "created_at": created.isoformat(),
        "creation_run_id": "run-1",
        "provenance": "ui",
        "type": "disposable",
    }
    if mode == "local_data":
        db_session.add(models.User(email=actor["email"], clerk_user_id=actor["id"]))
        await db_session.commit()
    registry = {
        "schema_version": 1,
        "run_id": "run-1",
        "started_at": "2026-10-07T08:00:00Z",
        "finished_at": "2026-10-07T09:00:00Z",
        "organizations": [],
        "actors": [actor],
    }
    payload = json.dumps(registry).encode()
    envelope = {
        "version": 1,
        "payload": base64.b64encode(payload).decode(),
        "signature": hmac.new(key, payload, hashlib.sha256).hexdigest(),
    }

    async def delete_actor(**kwargs):
        encrypted_path = tmp_path / "actor-user_orphan.zip.enc"
        assert encrypted_path.is_file()
        assert not list(tmp_path.glob("*.zip"))
        protected = json.loads(encrypted_path.read_bytes())
        aad = json.dumps(
            {"version": 1, "run_id": "run-1", "path": "actor-user_orphan.zip"},
            separators=(",", ":"),
        ).encode()
        exported = AESGCM(key).decrypt(
            base64.b64decode(protected["nonce"]),
            base64.b64decode(protected["ciphertext"]) + base64.b64decode(protected["tag"]),
            aad,
        )
        with zipfile.ZipFile(io.BytesIO(exported)) as archive:
            assert json.loads(archive.read("tables/clerk_actor.json"))[0]["id"] == actor["id"]
        return SimpleNamespace(id=kwargs["user_id"], deleted=mode != "unconfirmed")

    sdk = SimpleNamespace(
        users=SimpleNamespace(
            get_async=AsyncMock(
                return_value=SimpleNamespace(
                    id=actor["id"],
                    created_at=int(created.timestamp() * 1000),
                    primary_email_address_id="email_1",
                    email_addresses=[SimpleNamespace(id="email_1", email_address=actor["email"])],
                )
            ),
            get_organization_memberships_async=AsyncMock(
                return_value=SimpleNamespace(total_count=0, data=[])
            ),
            delete_async=AsyncMock(side_effect=delete_actor),
        )
    )
    environment = {
        **os.environ,
        "E2E_CLEANUP_CLERK_SECRET_KEY": "test-administrative-key",
        "E2E_REGISTRY_HMAC_KEY": base64.b64encode(key).decode(),
        "E2E_ARTIFACT_KEY": base64.b64encode(key).decode(),
    }
    result = await cleanup_e2e_run.cleanup(
        envelope, "run-1", tmp_path, execute=mode != "dry_run", env=environment, sdk=sdk
    )
    assert result["status"] == ("failed" if mode in {"unconfirmed", "local_data"} else mode)
    assert result["pending"] == []
    assert result["pending_actors"] == ([] if mode == "completed" else [actor["id"]])
    assert result["removed_actors"] == ([actor["id"]] if mode == "completed" else [])
    if mode in {"dry_run", "local_data"}:
        sdk.users.delete_async.assert_not_awaited()
        assert list(tmp_path.iterdir()) == []
    else:
        sdk.users.delete_async.assert_awaited_once()
    if mode == "local_data":
        async with TestingSessionLocal() as session:
            assert (
                await session.scalar(
                    select(models.User.id).where(models.User.clerk_user_id == actor["id"])
                )
                is not None
            )
