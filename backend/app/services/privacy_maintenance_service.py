"""Small, idempotent retention worker for technical records."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import cast, delete, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app import models

logger = structlog.get_logger(__name__)
RETENTION_DAYS = 30


class PrivacyMaintenanceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def run(
        self,
        *,
        organization_id: int,
        now: datetime | None = None,
        include_global_webhooks: bool = True,
    ) -> dict[str, int]:
        instant = now or datetime.now(UTC)
        cutoff = instant - timedelta(days=RETENTION_DAYS)

        webhook_result = (
            await self.run_webhook_maintenance(now=instant)
            if include_global_webhooks
            else {"redacted_webhooks": 0, "deleted_webhooks": 0}
        )

        redact_operations = models.MemberAccessOperation.operation_status.in_(
            [
                models.MemberAccessOperationStatus.local_committed,
                models.MemberAccessOperationStatus.compensated,
            ]
        )
        operation_redaction_ids = (
            await self.db.scalars(
                select(models.MemberAccessOperation.id)
                .where(
                    models.MemberAccessOperation.organization_id == organization_id,
                    redact_operations,
                    models.MemberAccessOperation.draft_payload_json.is_not(None),
                )
                .limit(500)
            )
        ).all()
        redacted_operations = len(operation_redaction_ids)
        if redacted_operations:
            await self.db.execute(
                update(models.MemberAccessOperation)
                .where(
                    models.MemberAccessOperation.id.in_(operation_redaction_ids),
                )
                .values(draft_payload_json=None)
            )
        deletable_operations = models.MemberAccessOperation.operation_status.in_(
            [
                models.MemberAccessOperationStatus.local_committed,
                models.MemberAccessOperationStatus.compensated,
            ]
        ) | (
            (
                models.MemberAccessOperation.operation_status
                == models.MemberAccessOperationStatus.failed
            )
            & (
                models.MemberAccessOperation.support_required_at.is_(None)
                | (
                    models.MemberAccessOperation.support_resolved_at.is_not(None)
                    & (models.MemberAccessOperation.support_resolved_at <= cutoff)
                )
            )
        )
        operation_ids = (
            await self.db.scalars(
                select(models.MemberAccessOperation.id)
                .where(
                    models.MemberAccessOperation.organization_id == organization_id,
                    models.MemberAccessOperation.updated_at <= cutoff,
                    deletable_operations,
                )
                .limit(500)
            )
        ).all()
        deleted_operations = 0
        if operation_ids:
            await self.db.execute(
                delete(models.MemberAccessOperation).where(
                    models.MemberAccessOperation.id.in_(operation_ids)
                )
            )
            deleted_operations = len(operation_ids)

        result = {
            **webhook_result,
            "redacted_operations": redacted_operations,
            "deleted_operations": deleted_operations,
        }
        logger.info(
            "privacy_maintenance_completed",
            organization_id=organization_id,
            retention_days=RETENTION_DAYS,
            result=result,
        )
        return result

    async def run_webhook_maintenance(self, *, now: datetime | None = None) -> dict[str, int]:
        """Maintain the global Clerk event inbox under controlled worker authority."""
        instant = now or datetime.now(UTC)
        cutoff = instant - timedelta(days=RETENTION_DAYS)
        terminal_statuses = [
            models.ClerkWebhookProcessingStatus.processed,
            models.ClerkWebhookProcessingStatus.ignored,
        ]
        webhook_redaction_ids = (
            await self.db.scalars(
                select(models.ClerkWebhookEvent.id)
                .where(
                    models.ClerkWebhookEvent.processing_status.in_(terminal_statuses),
                    cast(models.ClerkWebhookEvent.payload_json, JSONB) != cast({}, JSONB),
                )
                .limit(500)
            )
        ).all()
        redacted_webhook_count = len(webhook_redaction_ids)
        if redacted_webhook_count:
            await self.db.execute(
                update(models.ClerkWebhookEvent)
                .where(models.ClerkWebhookEvent.id.in_(webhook_redaction_ids))
                .values(payload_json={})
            )

        terminal_deletion = (
            models.ClerkWebhookEvent.processing_status.in_(terminal_statuses)
            & models.ClerkWebhookEvent.processed_at.is_not(None)
            & (models.ClerkWebhookEvent.processed_at <= cutoff)
        )
        resolved_failure_deletion = (
            models.ClerkWebhookEvent.processing_status.in_(
                [
                    models.ClerkWebhookProcessingStatus.sync_error,
                    models.ClerkWebhookProcessingStatus.dead_letter,
                ]
            )
            & models.ClerkWebhookEvent.support_resolved_at.is_not(None)
            & (models.ClerkWebhookEvent.support_resolved_at <= cutoff)
        )
        webhook_ids = (
            await self.db.scalars(
                select(models.ClerkWebhookEvent.id)
                .where(
                    or_(terminal_deletion, resolved_failure_deletion),
                )
                .limit(500)
            )
        ).all()
        if webhook_ids:
            await self.db.execute(
                delete(models.ClerkWebhookEvent).where(models.ClerkWebhookEvent.id.in_(webhook_ids))
            )
        return {
            "redacted_webhooks": redacted_webhook_count,
            "deleted_webhooks": len(webhook_ids),
        }
