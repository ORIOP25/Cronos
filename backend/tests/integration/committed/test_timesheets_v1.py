"""R12.1: weekly timesheet must follow the published v1 ledger."""

import asyncio
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app import models
from app.core.exceptions import AppError
from app.scheduler.infrastructure.models import SchedulerLessonLogV1
from app.services import timesheet_service
from tests._support.db_fixtures import TestingSessionLocal, get_school_room_type_id
from tests._support.scheduler_v1 import (
    add_lesson,
    add_version,
    lesson_interval,
    seed_generatable_school,
)

WEEK_START = date(2026, 9, 21)
PAST_DAY = date(2026, 9, 21)


async def _seed_v1_week(db_session, *, suffix: str):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id=f"timesheet_v1_{suffix}",
        clerk_org_id=f"org_timesheet_v1_{suffix}",
    )
    version = await add_version(db_session, seed)
    return seed, version


async def _add_past_lesson(db_session, seed, version, *, key: str, day=PAST_DAY, hour: int = 9):
    start, end = lesson_interval(day, hour)
    return await add_lesson(
        db_session,
        seed,
        version,
        stable_key=key,
        school_date=day,
        start=start,
        end=end,
    )


def _log_lesson(db_session, seed, lesson, status: str):
    now = datetime(2026, 9, 21, 18, tzinfo=UTC)
    db_session.add(
        SchedulerLessonLogV1(
            organization_id=seed.organization.id,
            school_year_id=seed.year.id,
            lesson_id=lesson.id,
            status=status,
            logged_by_membership_id=seed.membership.id,
            logged_at=now,
            created_at=now,
            updated_at=now,
        )
    )


def _submit(sync_db, seed, week_start=WEEK_START):
    return timesheet_service.submit_timesheet_sync(
        sync_db,
        organization_id=seed.organization.id,
        teacher_id=seed.assignment.teacher_id,
        week_start_date=week_start,
    )


async def test_a_v1_week_blocks_submission_until_every_lesson_is_resolved(db_session):
    seed, version = await _seed_v1_week(db_session, suffix="submit")
    first = await _add_past_lesson(db_session, seed, version, key="l1")
    second = await _add_past_lesson(db_session, seed, version, key="l2", day=date(2026, 9, 22))
    await db_session.commit()

    with pytest.raises(AppError) as unregistered:
        await db_session.run_sync(lambda sync_db: _submit(sync_db, seed))
    assert "Sem aulas planeadas" not in unregistered.value.detail

    _log_lesson(db_session, seed, first, "COMPLETED")
    await db_session.commit()
    with pytest.raises(AppError) as pending:
        await db_session.run_sync(lambda sync_db: _submit(sync_db, seed))
    assert "Sem aulas planeadas" not in pending.value.detail

    _log_lesson(db_session, seed, second, "OCCURRENCE")
    await db_session.commit()
    timesheet = await db_session.run_sync(lambda sync_db: _submit(sync_db, seed))

    assert timesheet.status == models.TimesheetStatus.SUBMITTED
    assert timesheet.submitted_at is not None


async def test_a_v1_week_with_a_future_lesson_cannot_be_submitted(db_session, monkeypatch):
    seed, version = await _seed_v1_week(db_session, suffix="future")
    past = await _add_past_lesson(db_session, seed, version, key="l1")
    await _add_past_lesson(db_session, seed, version, key="l2", day=date(2026, 9, 24))
    _log_lesson(db_session, seed, past, "COMPLETED")
    await db_session.commit()

    frozen = datetime(2026, 9, 23, 8, 0, tzinfo=UTC)

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen

    monkeypatch.setattr(timesheet_service, "datetime", _FrozenDatetime)

    with pytest.raises(AppError) as future:
        await db_session.run_sync(lambda sync_db: _submit(sync_db, seed))

    assert "futuro" in future.value.detail


async def test_admin_counts_follow_v1_and_ignore_superseded_versions(db_session):
    seed, version = await _seed_v1_week(db_session, suffix="counts")
    first = await _add_past_lesson(db_session, seed, version, key="l1")
    second = await _add_past_lesson(db_session, seed, version, key="l2", day=date(2026, 9, 22))
    _log_lesson(db_session, seed, first, "COMPLETED")
    _log_lesson(db_session, seed, second, "OCCURRENCE")
    superseded = await add_version(db_session, seed, status="SUPERSEDED")
    await _add_past_lesson(db_session, seed, superseded, key="historical-duplicate")
    await db_session.commit()

    rows = await db_session.run_sync(
        lambda sync_db: timesheet_service.list_timesheets_sync(
            sync_db, seed.organization.id, week_start_date=WEEK_START
        )
    )
    row = next(item for item in rows if item["teacher_id"] == seed.assignment.teacher_id)

    assert row["total_slots"] == 2
    assert row["registered_slots"] == 2
    assert row["completed_slots"] == 1
    assert row["occurrence_slots"] == 1


async def test_v1_timesheet_counts_stay_inside_the_organization(db_session):
    org_a, version_a = await _seed_v1_week(db_session, suffix="iso_a")
    org_b, version_b = await _seed_v1_week(db_session, suffix="iso_b")
    await _add_past_lesson(db_session, org_a, version_a, key="a1")
    await _add_past_lesson(db_session, org_b, version_b, key="b1")
    await db_session.commit()

    rows = await db_session.run_sync(
        lambda sync_db: timesheet_service.list_timesheets_sync(
            sync_db, org_a.organization.id, week_start_date=WEEK_START
        )
    )
    by_teacher = {row["teacher_id"]: row for row in rows}
    assert by_teacher[org_a.assignment.teacher_id]["total_slots"] == 1
    assert org_b.assignment.teacher_id not in by_teacher


async def test_concurrent_first_reads_create_one_timesheet(db_session):
    seed, _ = await _seed_v1_week(db_session, suffix="race")
    await db_session.commit()
    organization_id = seed.organization.id
    teacher_id = seed.assignment.teacher_id

    def _create(sync_db):
        return timesheet_service.get_or_create_timesheet_sync(
            sync_db, organization_id, teacher_id, WEEK_START
        ).id

    first = TestingSessionLocal()
    second = TestingSessionLocal()
    try:
        first_id = await first.run_sync(_create)
        blocked = asyncio.create_task(second.run_sync(_create))
        await asyncio.sleep(0.2)
        await first.commit()
        second_id = await blocked
        await second.commit()
    finally:
        await first.close()
        await second.close()

    assert first_id == second_id


async def _add_substitute(db_session, seed):
    from app.scheduler.infrastructure.models import CurricularAssignment, CurricularRequirement
    from tests._support.db_fixtures import create_teacher_profile

    subject = models.Subject(
        name="Matemática",
        organization_id=seed.organization.id,
        room_type_id=await get_school_room_type_id(db_session, seed.organization.id, "Normal"),
    )
    db_session.add(subject)
    await db_session.flush()
    module = models.Module(
        organization_id=seed.organization.id,
        subject_id=subject.id,
        name="Módulo M",
        required_minutes=100,
        order=1,
    )
    teacher = await create_teacher_profile(
        db_session, organization_id=seed.organization.id, name="Prof. Matemática"
    )
    db_session.add(module)
    await db_session.flush()
    assignment = CurricularAssignment(
        organization_id=seed.organization.id,
        school_year_id=seed.year.id,
        class_id=seed.class_.id,
        subject_id=subject.id,
        teacher_id=teacher.id,
    )
    db_session.add(assignment)
    await db_session.flush()
    db_session.add(
        CurricularRequirement(
            organization_id=seed.organization.id,
            assignment_id=assignment.id,
            module_id=module.id,
            sequence=1,
            required_minutes=100,
        )
    )
    await db_session.commit()
    return subject, module, teacher, assignment


async def test_a_v1_timesheet_follows_the_planned_substitution(db_session, monkeypatch):
    from app import schemas
    from app.scheduler.infrastructure import occurrences as occurrences_v1
    from app.scheduler.infrastructure import operations
    from app.scheduler.infrastructure.models import SchedulerLessonV1
    from tests._support.scheduler_v1 import publish_schedule

    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="timesheet_opblock",
        clerk_org_id="org_timesheet_opblock",
        module_minutes=500,
    )
    await db_session.commit()
    await publish_schedule(db_session, monkeypatch, seed)
    lesson = await db_session.scalar(
        select(SchedulerLessonV1)
        .where(
            SchedulerLessonV1.organization_id == seed.organization.id,
            SchedulerLessonV1.school_date.between(WEEK_START, WEEK_START + timedelta(days=6)),
        )
        .order_by(SchedulerLessonV1.school_date)
        .limit(1)
    )
    assert lesson is not None
    subject, _module, teacher, _assignment = await _add_substitute(db_session, seed)
    await db_session.commit()

    await operations.record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson.id,
        status="OCCURRENCE",
        summary="Falta.",
        notes=None,
        now_utc=lesson.ends_at,
        planning_relevant=True,
    )
    await db_session.commit()
    item = (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]
    decided = await occurrences_v1.update_occurrence(
        db_session,
        seed.organization.id,
        item["id"],
        schemas.LessonOccurrenceUpdate(
            status=models.LessonOccurrenceStatus.SUBSTITUTED,
            version=item["version"],
            substitute_teacher_id=teacher.id,
            substitute_subject_id=subject.id,
        ),
        decided_by_membership_id=seed.membership.id,
        now_utc=lesson.ends_at,
    )
    await db_session.commit()

    counts = await db_session.run_sync(
        lambda sync_db: timesheet_service.week_slot_counts_sync(
            sync_db, seed.organization.id, teacher.id, WEEK_START
        )
    )
    assert counts["total_slots"] == 1
    assert counts["completed_slots"] == 0

    with pytest.raises(AppError):
        await db_session.run_sync(
            lambda sync_db: timesheet_service.submit_timesheet_sync(
                sync_db,
                organization_id=seed.organization.id,
                teacher_id=teacher.id,
                week_start_date=WEEK_START,
            )
        )

    await operations.record_operational_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        operational_block_id=decided["substitute_block_id"],
        payload=schemas.LessonLogCreate(
            status=models.LessonLogStatus.COMPLETED,
            summary="Substituição dada.",
            notes=None,
        ),
        now_utc=lesson.ends_at,
    )
    await db_session.commit()

    counts = await db_session.run_sync(
        lambda sync_db: timesheet_service.week_slot_counts_sync(
            sync_db, seed.organization.id, teacher.id, WEEK_START
        )
    )
    assert counts["total_slots"] == 1
    assert counts["completed_slots"] == 1
    timesheet = await db_session.run_sync(
        lambda sync_db: timesheet_service.submit_timesheet_sync(
            sync_db,
            organization_id=seed.organization.id,
            teacher_id=teacher.id,
            week_start_date=WEEK_START,
        )
    )
    assert timesheet.status == models.TimesheetStatus.SUBMITTED


async def test_invalid_timesheet_transition_preserves_status_and_readable_message(db_session):
    seed, _ = await _seed_v1_week(db_session, suffix="invalid_transition")
    timesheet = await db_session.run_sync(
        lambda sync_db: timesheet_service.get_or_create_timesheet_sync(
            sync_db, seed.organization.id, seed.assignment.teacher_id, WEEK_START
        )
    )
    await db_session.commit()

    with pytest.raises(AppError) as invalid:
        await db_session.run_sync(
            lambda sync_db: timesheet_service.update_timesheet_status_sync(
                sync_db,
                seed.organization.id,
                timesheet.id,
                models.TimesheetStatus.APPROVED,
                seed.membership.id,
            )
        )

    assert invalid.value.detail == "Transição de estado inválida: OPEN → APPROVED."
    assert timesheet.status == models.TimesheetStatus.OPEN
    assert timesheet.approved_at is None
    assert timesheet.approved_by_membership_id is None
