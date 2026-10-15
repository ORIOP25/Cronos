"""Move a published joint lesson into the past for the joint-lesson E2E.

This is test-only fixture construction, not a product feature. It exists because
the engine publishes lessons only into periods that have not started, so an
acceptance journey that logs a joint lesson and decides its gap needs an
already-ended lesson. The script shifts the two sister rows of one generated
joint lesson into an earlier week: same weekday, same time-of-day, same
duration, same stable key, teaching-unit key, slices and credit.

Only the canonical published schedule of the active school year is read, so a
superseded version with the same stable key can never be picked. The target is
always an ended period: if the block already ended the metadata is returned
unchanged, and the shift grows by whole weeks only as far as needed. Deep past
weeks carry no published lessons, but the target date is still validated for
free space, identical sibling metadata and the active school year window before
any write.

The guards run before any write. Only a reserved test database and the single
`E2E Joint` fixture organization are accepted.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import models
from app.config import settings
from app.db.database import async_database_url
from app.scheduler.infrastructure.models import (
    CurricularAssignment,
    SchedulerLessonV1,
    SchedulerVersionV1,
)

RESERVED_TEST_DATABASES = ("cronos_test_db", "cronos_ci_db")
_GENERATED_DATABASE = re.compile(r"^cronos_(?:test|ci)_gw\d+$")
HISTORY_SHIFT = timedelta(days=14)
HISTORY_STEP = timedelta(weeks=1)

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


async def _joint_lessons(
    db, organization_id: int, school_year_id: int, version_id: int
) -> list[tuple[SchedulerLessonV1, int]]:
    """Lessons of the E2E Joint classes in one published version, oldest first."""
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
            SchedulerLessonV1.school_year_id == school_year_id,
            SchedulerLessonV1.version_id == version_id,
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


def history_shift_until_ended(ends_at: datetime, *, now: datetime) -> timedelta:
    """Smallest whole-week shift of at least ``HISTORY_SHIFT`` that ends the block.

    Whole weeks keep the weekday, time-of-day and duration of the original
    lesson, so the pair stays a valid published block.
    """
    shift = HISTORY_SHIFT
    while ends_at - shift > now:
        shift += HISTORY_STEP
    return shift


async def active_version_id(db, organization_id: int) -> tuple[int, models.SchedulerSchoolYear]:
    """Canonical ACTIVE published version of the active school year, or fail."""
    year = await db.scalar(
        select(models.SchedulerSchoolYear).where(
            models.SchedulerSchoolYear.organization_id == organization_id,
            models.SchedulerSchoolYear.is_active.is_(True),
        )
    )
    if year is None:
        raise ValueError("The organization has no active school year")
    state = await db.scalar(
        select(models.SchedulerSchoolYearState).where(
            models.SchedulerSchoolYearState.organization_id == organization_id,
            models.SchedulerSchoolYearState.school_year_id == year.id,
        )
    )
    pointer = state.active_schedule_version_id if state is not None else None
    if not pointer:
        raise ValueError("The active school year has no published schedule")
    try:
        version_id = int(pointer)
    except ValueError as exc:
        raise ValueError("The active schedule version pointer is invalid") from exc
    version = await db.scalar(
        select(SchedulerVersionV1.id).where(
            SchedulerVersionV1.organization_id == organization_id,
            SchedulerVersionV1.school_year_id == year.id,
            SchedulerVersionV1.id == version_id,
            SchedulerVersionV1.status == "ACTIVE",
        )
    )
    if version is None:
        raise ValueError("The active schedule version pointer does not name a published version")
    return version, year


def require_identical_siblings(sisters: list[SchedulerLessonV1]) -> None:
    """The pair shares a stable key and every physical fact before any write."""
    first = sisters[0]
    identical = all(
        sister.stable_key == first.stable_key
        and sister.school_date == first.school_date
        and sister.starts_at == first.starts_at
        and sister.ends_at == first.ends_at
        and sister.room_id == first.room_id
        for sister in sisters[1:]
    )
    if not identical:
        raise ValueError("The joint lesson pair shares a stable key but not identical metadata")


async def _require_free_target(
    db,
    organization_id: int,
    school_year_id: int,
    version_id: int,
    target_date,
    sibling_ids: list[int],
) -> None:
    """Refuse a target date already used by a fixture-class lesson in the version."""
    conflict = await db.scalar(
        select(SchedulerLessonV1.id)
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
            SchedulerLessonV1.school_year_id == school_year_id,
            SchedulerLessonV1.version_id == version_id,
            SchedulerLessonV1.school_date == target_date,
            SchedulerLessonV1.id.not_in(sibling_ids),
            models.Class.name.in_(FIXTURE_CLASS_NAMES),
        )
        .limit(1)
    )
    if conflict is not None:
        raise ValueError(
            f"Refusing to seed joint history into an occupied date: {target_date.isoformat()}"
        )


async def move_first_joint_lesson(
    db,
    organization_id: int,
    expected_clerk_org_id: str,
    *,
    now_utc: datetime | None = None,
) -> dict:
    """Shift the oldest published joint block of the active version into the past.

    The block is already ended on a repeated call, so its metadata is returned
    unchanged instead of shifting it again. The caller owns the transaction.
    """
    moment = now_utc or datetime.now(UTC)
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
        raise ValueError("The E2E Joint fixture classes were not found in this organization")
    version_id, year = await active_version_id(db, organization_id)
    sisters = first_joint_block(await _joint_lessons(db, organization_id, year.id, version_id))
    require_identical_siblings(sisters)
    lesson_ids = sorted(sister.id for sister in sisters)
    ends_at = max(sister.ends_at for sister in sisters)
    if ends_at <= moment:
        return {
            "organization_id": organization_id,
            "school_date": sisters[0].school_date.isoformat(),
            "lesson_ids": lesson_ids,
        }
    shift = history_shift_until_ended(ends_at, now=moment)
    target_date = sisters[0].school_date - shift
    if target_date < year.start_date:
        raise ValueError("The joint history shift leaves the active school year")
    await _require_free_target(db, organization_id, year.id, version_id, target_date, lesson_ids)
    for sister in sisters:
        sister.school_date = sister.school_date - shift
        sister.starts_at = sister.starts_at - shift
        sister.ends_at = sister.ends_at - shift
    return {
        "organization_id": organization_id,
        "school_date": target_date.isoformat(),
        "lesson_ids": lesson_ids,
    }


async def _seed(
    organization_id: int, expected_clerk_org_id: str, *, now_utc: datetime | None = None
) -> dict:
    engine = create_async_engine(administrative_url(), poolclass=NullPool)
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory.begin() as db:
            return await move_first_joint_lesson(
                db, organization_id, expected_clerk_org_id, now_utc=now_utc
            )
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
