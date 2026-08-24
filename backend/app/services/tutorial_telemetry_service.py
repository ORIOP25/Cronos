"""Tutorial Telemetry Service — Append-only telemetry recording."""

from __future__ import annotations

import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas

logger = structlog.get_logger(__name__)


class TutorialTelemetryService:
    @classmethod
    async def record(
        cls,
        db: AsyncSession,
        *,
        organization_id: int,
        event: schemas.TutorialTelemetryEventCreate,
    ) -> None:
        stmt = (
            pg_insert(models.TutorialTelemetryEvent)
            .values(
                organization_id=organization_id,
                tutorial_run_id=event.tutorial_run_id,
                client_event_id=event.client_event_id,
                tutorial_version=event.tutorial_version,
                event_name=event.event_name,
                chapter=event.chapter,
                step_id=event.step_id,
            )
            .on_conflict_do_nothing(index_elements=["organization_id", "client_event_id"])
        )
        inserted_id = (
            await db.execute(stmt.returning(models.TutorialTelemetryEvent.id))
        ).scalar_one_or_none()
        await db.flush()
        logger.info(
            "tutorial_telemetry_event_inserted"
            if inserted_id is not None
            else "tutorial_telemetry_event_duplicate",
            organization_id=organization_id,
            event_name=event.event_name,
            tutorial_run_id=str(event.tutorial_run_id),
            chapter=event.chapter,
            step_id=event.step_id,
        )
