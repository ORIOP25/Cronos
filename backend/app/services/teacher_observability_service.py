"""Observabilidade operacional para endpoints self-service do professor (Passo 9)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import ceil
from time import perf_counter

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app import models
from app.core.exceptions import AppError, status_code_for_kind
from app.core.logging import safe_exception_frames

logger = structlog.get_logger(__name__)

ENDPOINT_TEACHERS_ME_AVAILABILITY_READ = "TEACHERS_ME_AVAILABILITY_READ"
ENDPOINT_TEACHERS_ME_PROGRESS_READ = "TEACHERS_ME_PROGRESS_READ"
ENDPOINT_SCHEDULE_ME_HORIZON_READ = "SCHEDULE_ME_HORIZON_READ"
ENDPOINT_SCHEDULE_WEEK_TEACHER_READ = "SCHEDULE_WEEK_TEACHER_READ"

ALERT_403_MIN_COUNT = 10
ALERT_403_MIN_RATE_PERCENT = 20.0
ALERT_5XX_RATE_PERCENT = 2.0


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    rank = int(ceil((percentile / 100.0) * len(ordered))) - 1
    rank = max(0, min(rank, len(ordered) - 1))
    return int(ordered[rank])


def log_teacher_endpoint_event_safe_sync(
    db: Session,
    *,
    organization_id: int,
    actor_membership_id: int | None,
    actor_role: str | None,
    endpoint_key: str,
    http_status: int,
    latency_ms: int,
    active_generation_id: str | None = None,
) -> None:
    """Regista evento sem bloquear o fluxo principal em caso de falha de observabilidade."""
    try:
        event = models.TeacherEndpointOperationalEvent(
            organization_id=organization_id,
            actor_membership_id=actor_membership_id,
            actor_role=actor_role,
            endpoint_key=endpoint_key,
            http_status=http_status,
            latency_ms=max(0, int(latency_ms)),
            active_generation_id=active_generation_id,
            created_at=datetime.now(UTC),
        )
        db.add(event)
        db.flush()
    except Exception as exc:
        logger.warning(
            "teacher_endpoint_observability_emit_failed",
            organization_id=organization_id,
            endpoint_key=endpoint_key,
            http_status=http_status,
            error_type=type(exc).__name__,
            exception_frames=safe_exception_frames(exc),
        )


@dataclass
class EndpointOutcome:
    """Mutable outcome of a tracked endpoint call; callers may set the generation id."""

    http_status: int = 200
    active_generation_id: str | None = None


@asynccontextmanager
async def track_teacher_endpoint(
    db: AsyncSession,
    *,
    organization_id: int,
    actor_membership_id: int | None,
    actor_role: str | None,
    endpoint_key: str,
    enabled: bool = True,
) -> AsyncIterator[EndpointOutcome]:
    """Time the wrapped endpoint body and record its HTTP outcome and latency."""
    started = perf_counter()
    outcome = EndpointOutcome()
    try:
        yield outcome
    except AppError as exc:
        outcome.http_status = status_code_for_kind(exc.kind, exc.code)
        raise
    except Exception:
        outcome.http_status = 500
        raise
    finally:
        if enabled:
            latency_ms = max(1, int((perf_counter() - started) * 1000))
            await db.run_sync(
                lambda sync_db: log_teacher_endpoint_event_safe_sync(
                    sync_db,
                    organization_id=organization_id,
                    actor_membership_id=actor_membership_id,
                    actor_role=actor_role,
                    endpoint_key=endpoint_key,
                    http_status=outcome.http_status,
                    latency_ms=latency_ms,
                    active_generation_id=outcome.active_generation_id,
                )
            )


def get_teacher_endpoint_observability_summary_sync(
    db: Session,
    *,
    organization_id: int,
    window_minutes: int,
) -> dict:
    """Agrega eventos por endpoint com taxas de erro e alertas operacionais."""
    normalized_window_minutes = max(5, int(window_minutes))
    start_at = datetime.now(UTC) - timedelta(minutes=normalized_window_minutes)

    events = (
        db.execute(
            select(models.TeacherEndpointOperationalEvent)
            .where(
                and_(
                    models.TeacherEndpointOperationalEvent.organization_id == organization_id,
                    models.TeacherEndpointOperationalEvent.created_at >= start_at,
                )
            )
            .order_by(models.TeacherEndpointOperationalEvent.created_at.asc())
        )
        .scalars()
        .all()
    )

    grouped = defaultdict(
        lambda: {
            "total_requests": 0,
            "status_2xx": 0,
            "status_403": 0,
            "status_5xx": 0,
            "latencies": [],
        }
    )

    for event in events:
        bucket = grouped[event.endpoint_key]
        status_code = int(event.http_status)

        bucket["total_requests"] += 1
        if 200 <= status_code < 300:
            bucket["status_2xx"] += 1
        if status_code == 403:
            bucket["status_403"] += 1
        if status_code >= 500:
            bucket["status_5xx"] += 1
        bucket["latencies"].append(max(0, int(event.latency_ms)))

    endpoints_payload: list[dict] = []
    alerts_payload: list[dict] = []

    for endpoint_key in sorted(grouped.keys()):
        bucket = grouped[endpoint_key]
        total_requests = int(bucket["total_requests"])
        status_403 = int(bucket["status_403"])
        status_5xx = int(bucket["status_5xx"])

        error_rate_percent = 0.0
        if total_requests > 0:
            error_rate_percent = round(((status_403 + status_5xx) / total_requests) * 100, 2)

        endpoint_payload = {
            "endpoint_key": endpoint_key,
            "total_requests": total_requests,
            "status_2xx": int(bucket["status_2xx"]),
            "status_403": status_403,
            "status_5xx": status_5xx,
            "error_rate_percent": error_rate_percent,
            "p95_latency_ms": _percentile(bucket["latencies"], 95.0),
        }
        endpoints_payload.append(endpoint_payload)

        rate_403 = (status_403 / total_requests) * 100 if total_requests else 0.0
        rate_5xx = (status_5xx / total_requests) * 100 if total_requests else 0.0

        if status_403 >= ALERT_403_MIN_COUNT and rate_403 >= ALERT_403_MIN_RATE_PERCENT:
            alerts_payload.append(
                {
                    "endpoint_key": endpoint_key,
                    "alert_code": "ABNORMAL_403_RATE",
                    "severity": "medium",
                    "threshold": (
                        f">= {ALERT_403_MIN_COUNT} e >= {ALERT_403_MIN_RATE_PERCENT:.0f}% "
                        f"em {normalized_window_minutes}m"
                    ),
                    "observed_value": f"{rate_403:.2f}% ({status_403}/{total_requests})",
                }
            )

        if rate_5xx > ALERT_5XX_RATE_PERCENT:
            alerts_payload.append(
                {
                    "endpoint_key": endpoint_key,
                    "alert_code": "HIGH_5XX_RATE",
                    "severity": "high",
                    "threshold": f"> {ALERT_5XX_RATE_PERCENT:.0f}% em {normalized_window_minutes}m",
                    "observed_value": f"{rate_5xx:.2f}% ({status_5xx}/{total_requests})",
                }
            )

    return {
        "window_minutes": normalized_window_minutes,
        "total_events": len(events),
        "endpoints": endpoints_payload,
        "alerts": alerts_payload,
    }
