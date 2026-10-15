"""Move a published joint lesson into the past for the joint-lesson E2E.

This is test-only fixture construction, not a product feature. It exists because
the engine publishes lessons only into periods that have not started, so an
acceptance journey that logs a joint lesson and decides its gap needs an
already-ended lesson. The script shifts the two sister rows of one generated
joint lesson two weeks earlier: same weekday, same time-of-day, same duration,
same stable key, teaching-unit key, slices and credit. Past weeks carry no
published lessons, so the move cannot collide.

The guards run before any write. Only a reserved test database and the single
`E2E Joint` fixture organization are accepted.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from datetime import timedelta

from sqlalchemy import and_, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import models
from app.config import settings
from app.db.database import async_database_url
from app.scheduler.infrastructure.models import CurricularAssignment, SchedulerLessonV1

RESERVED_TEST_DATABASES = ("cronos_test_db", "cronos_ci_db")
_GENERATED_DATABASE = re.compile(r"^cronos_(?:test|ci)_gw\d+$")
HISTORY_SHIFT = timedelta(days=14)

FIXTURE_COURSE_NAME = "E2E Joint Course"
FIXTURE_SUBJECT_NAME = "E2E Joint Subject"
FIXTURE_CLASS_NAMES = ("E2E Joint A", "E2E Joint B")


def reserved_test_database(url: str) -> str:
    """Return the database name, or refuse a target this fixture must not touch."""
    if not url:
        raise ValueError("An administrative database URL is required for the joint seed.")
    name = make_url(url).database or ""
    if name in RESERVED_TEST_DATABASES or _GENERATED_DATABASE.match(name):
        return name
    raise ValueError(f"Refusing to seed joint history outside a reserved test database: {name!r}")


def administrative_url() -> str:
    url = os.environ.get("MIGRATION_DATABASE_URL") or str(
        settings.MIGRATION_DATABASE_URL or settings.DATABASE_URL or ""
    )
    reserved_test_database(url)
    return async_database_url(url)


def validate_target(
    *, organization_id: int, expected_clerk_org_id: str, clerk_org_id: str | None
) -> None:
    """Refuse any organization that is not the one the caller prepared."""
    if organization_id < 1:
        raise ValueError("--organization-id must be positive")
    if not expected_clerk_org_id:
        raise ValueError("--expected-clerk-org-id is required")
    if clerk_org_id != expected_clerk_org_id:
        raise ValueError("The organization does not match --expected-clerk-org-id")


async def _joint_lessons(db, organization_id: int) -> list[tuple[SchedulerLessonV1, int]]:
    """Lessons of the E2E Joint classes, with their class, oldest first."""
    result = await db.execute(
        select(SchedulerLessonV1, CurricularAssignment.class_id)
        .join(
            CurricularAssignment,
            and_(
                CurricularAssignment.organization_id == SchedulerLessonV1.organization_id,
                CurricularAssignment.school_year_id == SchedulerLessonV1.school_year_id,
                CurricularAssignment.id == SchedulerLessonV1.assignment_id,
            ),
        )
        .join(
            models.Class,
            and_(
                models.Class.organization_id == SchedulerLessonV1.organization_id,
                models.Class.id == CurricularAssignment.class_id,
            ),
        )
        .where(
            SchedulerLessonV1.organization_id == organization_id,
            models.Class.name.in_(FIXTURE_CLASS_NAMES),
        )
        .order_by(SchedulerLessonV1.starts_at, SchedulerLessonV1.id)
    )
    return [(lesson, class_id) for lesson, class_id in result.all()]


def first_joint_block(rows: list[tuple[SchedulerLessonV1, int]]) -> list[SchedulerLessonV1]:
    """The oldest lesson whose stable key carries both member classes."""
    by_key: dict[str, list[tuple[SchedulerLessonV1, int]]] = {}
    for lesson, class_id in rows:
        by_key.setdefault(lesson.stable_key, []).append((lesson, class_id))
    for lesson, _ in rows:
        members = by_key[lesson.stable_key]
        if len({class_id for _, class_id in members}) < 2:
            continue
        if (lesson.teaching_unit_key or "").startswith("D:"):
            continue
        return [member for member, _ in sorted(members, key=lambda item: item[0].id)]
    raise ValueError("No published joint lesson was found for the E2E Joint fixture classes")


async def _seed(organization_id: int, expected_clerk_org_id: str) -> dict:
    engine = create_async_engine(administrative_url(), poolclass=NullPool)
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory.begin() as db:
            organization = await db.scalar(
                select(models.Organization)
                .where(models.Organization.id == organization_id)
                .with_for_update()
            )
            if organization is None:
                raise ValueError(f"Organization {organization_id} was not found")
            validate_target(
                organization_id=organization_id,
                expected_clerk_org_id=expected_clerk_org_id,
                clerk_org_id=organization.clerk_org_id,
            )
            classes = list(
                await db.scalars(
                    select(models.Class.name).where(
                        models.Class.organization_id == organization_id,
                        models.Class.name.in_(FIXTURE_CLASS_NAMES),
                    )
                )
            )
            if sorted(classes) != sorted(FIXTURE_CLASS_NAMES):
                raise ValueError(
                    "The E2E Joint fixture classes were not found in this organization"
                )
            sisters = first_joint_block(await _joint_lessons(db, organization_id))
            target_date = sisters[0].school_date - HISTORY_SHIFT
            for sister in sisters:
                sister.school_date = sister.school_date - HISTORY_SHIFT
                sister.starts_at = sister.starts_at - HISTORY_SHIFT
                sister.ends_at = sister.ends_at - HISTORY_SHIFT
            return {
                "organization_id": organization_id,
                "school_date": target_date.isoformat(),
                "lesson_ids": sorted(sister.id for sister in sisters),
            }
    finally:
        await engine.dispose()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python scripts/seed_e2e_joint_history.py")
    parser.add_argument("--organization-id", required=True, type=int)
    parser.add_argument("--expected-clerk-org-id", required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    try:
        result = asyncio.run(_seed(args.organization_id, args.expected_clerk_org_id))
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
