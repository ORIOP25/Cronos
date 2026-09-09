from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app import models
from app.services.privacy_maintenance_service import PrivacyMaintenanceService

pytestmark = pytest.mark.postgresql


def _event(
    svix_id: str,
    status: models.ClerkWebhookProcessingStatus,
    *,
    processed_at: datetime | None = None,
    support_resolved_at: datetime | None = None,
    payload: dict | None = None,
) -> models.ClerkWebhookEvent:
    return models.ClerkWebhookEvent(
        svix_id=svix_id,
        event_type="user.updated",
        clerk_object_id=svix_id,
        payload_json=payload if payload is not None else {"personal": "data"},
        processing_status=status,
        processed_at=processed_at,
        support_resolved_at=support_resolved_at,
    )


async def test_webhook_retention_covers_terminal_and_resolved_failure_boundaries(db_session):
    now = datetime(2026, 9, 8, 12, tzinfo=UTC)
    cutoff = now - timedelta(days=30)
    old = now - timedelta(days=31)
    recent = now - timedelta(days=29)

    events = [
        _event("processed-old", models.ClerkWebhookProcessingStatus.processed, processed_at=old),
        _event(
            "ignored-boundary", models.ClerkWebhookProcessingStatus.ignored, processed_at=cutoff
        ),
        _event(
            "processed-recent", models.ClerkWebhookProcessingStatus.processed, processed_at=recent
        ),
        _event(
            "sync-error-resolved",
            models.ClerkWebhookProcessingStatus.sync_error,
            support_resolved_at=old,
        ),
        _event(
            "dead-letter-boundary",
            models.ClerkWebhookProcessingStatus.dead_letter,
            support_resolved_at=cutoff,
        ),
        _event("sync-error-open", models.ClerkWebhookProcessingStatus.sync_error),
        _event(
            "dead-letter-recent",
            models.ClerkWebhookProcessingStatus.dead_letter,
            support_resolved_at=recent,
        ),
        _event("retryable-old", models.ClerkWebhookProcessingStatus.retryable_failed),
        _event("processing-old", models.ClerkWebhookProcessingStatus.processing),
        _event("received-old", models.ClerkWebhookProcessingStatus.received),
    ]
    db_session.add_all(events)
    await db_session.flush()

    result = await PrivacyMaintenanceService(db_session).run_webhook_maintenance(now=now)

    assert result == {"redacted_webhooks": 3, "deleted_webhooks": 4}
    remaining = (
        await db_session.scalars(
            select(models.ClerkWebhookEvent).order_by(models.ClerkWebhookEvent.svix_id)
        )
    ).all()
    remaining_by_id = {event.svix_id: event for event in remaining}
    assert set(remaining_by_id) == {
        "dead-letter-recent",
        "processing-old",
        "processed-recent",
        "received-old",
        "retryable-old",
        "sync-error-open",
    }
    assert remaining_by_id["processed-recent"].payload_json == {}
    assert remaining_by_id["dead-letter-recent"].payload_json == {"personal": "data"}
    assert remaining_by_id["sync-error-open"].payload_json == {"personal": "data"}

    assert await PrivacyMaintenanceService(db_session).run_webhook_maintenance(now=now) == {
        "redacted_webhooks": 0,
        "deleted_webhooks": 0,
    }


async def test_webhook_retention_is_bounded_to_500_rows(db_session):
    now = datetime(2026, 9, 8, 12, tzinfo=UTC)
    old = now - timedelta(days=31)
    db_session.add_all(
        _event(
            f"processed-{index:03d}",
            models.ClerkWebhookProcessingStatus.processed,
            processed_at=old,
        )
        for index in range(501)
    )
    await db_session.flush()

    result = await PrivacyMaintenanceService(db_session).run_webhook_maintenance(now=now)

    assert result == {"redacted_webhooks": 500, "deleted_webhooks": 500}
    assert await db_session.scalar(select(models.ClerkWebhookEvent.id)) is not None
