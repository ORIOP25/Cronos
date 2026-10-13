"""Small focused PostgreSQL seeds for scheduler v1 transactions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select

from app import models
from app.scheduler.infrastructure.models import (
    CurricularAssignment,
    CurricularRequirement,
    SchedulerLessonV1,
    SchedulerVersionV1,
)
from tests._support.db_fixtures import create_completed_organization, create_teacher_profile


@dataclass
class V1Seed:
    organization: models.Organization
    membership: models.OrganizationMembership
    year: models.SchedulerSchoolYear
    assignment: CurricularAssignment
    module: models.Module
    state: models.SchedulerSchoolYearState
    room: models.Room
    course: models.Course
    subject: models.Subject
    class_: models.Class


async def seed_v1_assignment(
    db_session,
    *,
    clerk_user_id: str = "v1_admin",
    clerk_org_id: str = "v1_org",
    module_minutes: int = 100,
    label: str = "2026/27",
) -> V1Seed:
    organization, user = await create_completed_organization(
        db_session, clerk_user_id=clerk_user_id, clerk_org_id=clerk_org_id
    )
    membership = await db_session.scalar(
        select(models.OrganizationMembership).where(
            models.OrganizationMembership.organization_id == organization.id,
            models.OrganizationMembership.account_id == user.id,
        )
    )
    course = models.Course(name="Course", abbreviation="C", organization_id=organization.id)
    subject = models.Subject(name="Subject", organization_id=organization.id)
    year = models.SchedulerSchoolYear(
        organization_id=organization.id,
        label=label,
        start_date=date(2026, 9, 1),
        hard_end_date=date(2027, 7, 31),
    )
    room = models.Room(name="Sala", capacity=25, organization_id=organization.id)
    db_session.add_all((course, subject, year, room))
    await db_session.flush()
    class_ = models.Class(
        name="A",
        size=20,
        start_year=2026,
        end_year=2029,
        grade_level=10,
        course_id=course.id,
        organization_id=organization.id,
    )
    module = models.Module(
        organization_id=organization.id,
        subject_id=subject.id,
        name="Module",
        required_minutes=module_minutes,
        order=1,
    )
    db_session.add_all((class_, module))
    await db_session.flush()
    teacher = await create_teacher_profile(db_session, organization_id=organization.id)
    assignment = CurricularAssignment(
        organization_id=organization.id,
        school_year_id=year.id,
        class_id=class_.id,
        subject_id=subject.id,
        teacher_id=teacher.id,
    )
    state = models.SchedulerSchoolYearState(
        organization_id=organization.id,
        school_year_id=year.id,
        school_year_publication_state=models.SchoolYearPublicationState.UNPUBLISHED,
        scheduler_state_version=0,
        lock_version=0,
    )
    db_session.add_all((assignment, state))
    await db_session.flush()
    db_session.add(
        CurricularRequirement(
            organization_id=organization.id,
            assignment_id=assignment.id,
            module_id=module.id,
            sequence=1,
            required_minutes=module_minutes,
        )
    )
    db_session.add(
        models.ClassSubjectLink(
            organization_id=organization.id,
            class_id=class_.id,
            subject_id=subject.id,
            grade_level=class_.grade_level,
            teacher_id=teacher.id,
        )
    )
    await db_session.flush()
    return V1Seed(
        organization, membership, year, assignment, module, state, room, course, subject, class_
    )


async def seed_generatable_school(
    db_session,
    *,
    clerk_user_id: str = "v1_admin",
    clerk_org_id: str = "v1_org",
    module_minutes: int = 100,
    preferred_end_date: date = date(2026, 10, 30),
) -> V1Seed:
    """Minimal school with a grid and a preferred end date ready to generate."""
    seed = await seed_v1_assignment(
        db_session,
        clerk_user_id=clerk_user_id,
        clerk_org_id=clerk_org_id,
        module_minutes=module_minutes,
    )
    seed.year.preferred_end_date = preferred_end_date
    db_session.add_all(
        (
            models.Timeslot(
                organization_id=seed.organization.id,
                day_of_week=0,
                start_time=time(9, 0),
                end_time=time(9, 50),
            ),
            models.Timeslot(
                organization_id=seed.organization.id,
                day_of_week=1,
                start_time=time(9, 0),
                end_time=time(9, 50),
            ),
        )
    )
    await db_session.flush()
    return seed


async def add_version(
    db_session,
    seed: V1Seed,
    *,
    status: str = "ACTIVE",
    digest: str = "a" * 64,
    approved_at: datetime | None = None,
) -> SchedulerVersionV1:
    moment = approved_at or datetime(2026, 9, 22, 10, tzinfo=UTC)
    version = SchedulerVersionV1(
        organization_id=seed.organization.id,
        school_year_id=seed.year.id,
        origin=f"generation:{digest[:6]}",
        status=status,
        snapshot_digest=digest,
        created_at=moment,
        approved_at=moment if status == "ACTIVE" else None,
    )
    db_session.add(version)
    await db_session.flush()
    return version


async def add_lesson(
    db_session,
    seed: V1Seed,
    version: SchedulerVersionV1,
    *,
    stable_key: str,
    school_date: date,
    start: datetime,
    end: datetime,
    credit_minutes: int | None = None,
    room_id: int | None = None,
    assignment_id: int | None = None,
) -> SchedulerLessonV1:
    duration = int((end - start).total_seconds() // 60)
    lesson = SchedulerLessonV1(
        organization_id=seed.organization.id,
        school_year_id=seed.year.id,
        version_id=version.id,
        assignment_id=assignment_id or seed.assignment.id,
        stable_key=stable_key,
        school_date=school_date,
        starts_at=start,
        ends_at=end,
        room_id=room_id or seed.room.id,
        physical_minutes=duration,
        credit_minutes=duration if credit_minutes is None else credit_minutes,
    )
    db_session.add(lesson)
    await db_session.flush()
    return lesson


def lesson_interval(school_date: date, hour: int, minutes: int = 60) -> tuple[datetime, datetime]:
    start = datetime.combine(school_date, datetime.min.time(), tzinfo=UTC).replace(hour=hour)
    return start, start + timedelta(minutes=minutes)


MOMENT = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)


async def run_generation(
    db_session, monkeypatch, seed: V1Seed, *, key: str, now: datetime = MOMENT
) -> None:
    """Generate and approve one proposal through the real v1 worker."""
    from app import scheduler_v1_worker as worker
    from app.scheduler.infrastructure.jobs import enqueue_generation
    from app.scheduler.infrastructure.proposals import approve_proposal
    from app.scheduler.infrastructure.queries import current_proposal
    from tests._support.db_fixtures import TestingSessionLocal, test_engine

    await enqueue_generation(
        db_session,
        seed.organization.id,
        idempotency_key=key,
        requested_by_membership_id=seed.membership.id,
        now_utc=now,
    )
    await db_session.commit()
    monkeypatch.setattr(worker, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(worker, "engine_async", test_engine)
    monkeypatch.setattr(worker, "_now", lambda: now)
    monkeypatch.setattr(worker, "RECOVERY_ASSESSMENT_SECONDS", 0.0)
    await worker.process_next_jobs()
    await db_session.refresh(seed.state)
    proposal = await current_proposal(db_session, seed.organization.id)
    await approve_proposal(
        db_session,
        organization_id=seed.organization.id,
        proposal_id=proposal["proposal_id"],
        decided_by_membership_id=seed.membership.id,
        now_utc=now,
    )


async def publish_schedule(db_session, monkeypatch, seed: V1Seed) -> None:
    await run_generation(
        db_session,
        monkeypatch,
        seed,
        key=f"publish:{seed.organization.id}",
    )


async def seed_published_baseline(
    db_session,
    seed: V1Seed,
    *,
    now_utc: datetime = MOMENT,
) -> SchedulerVersionV1:
    """Persist the native constructive candidate as the active published baseline.

    Reuses the production constructive generator and validator, then writes the
    version/lesson/slice rows the publisher would. Later ``load_snapshot``
    (ADAPTIVE_RECOVERY) and real repair/approval cycles run unchanged.
    """
    from app.scheduler.domain.candidate import SchedulingStrategy
    from app.scheduler.domain.candidate_validation import validate_candidate
    from app.scheduler.infrastructure.constructive import construct_schedule
    from app.scheduler.infrastructure.models import SchedulerLessonSliceV1
    from app.scheduler.infrastructure.snapshot import load_snapshot

    bundle = await load_snapshot(
        db_session,
        seed.organization.id,
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        now_utc=now_utc,
        school_year_id=seed.year.id,
    )
    candidate = construct_schedule(bundle.snapshot, bundle.periods)
    if candidate is None:
        raise ValueError("The native constructive generator produced no baseline.")
    if not validate_candidate(bundle.snapshot, candidate).valid:
        raise ValueError("The native constructive baseline failed validation.")

    version = await add_version(
        db_session, seed, status="ACTIVE", digest=bundle.digest, approved_at=now_utc
    )
    for lesson in candidate.lessons:
        row = SchedulerLessonV1(
            organization_id=seed.organization.id,
            school_year_id=seed.year.id,
            version_id=version.id,
            assignment_id=lesson.assignment_id,
            stable_key=str(lesson.lesson_id),
            school_date=lesson.period.school_date,
            starts_at=lesson.period.start_utc,
            ends_at=lesson.period.end_utc,
            room_id=lesson.room_id,
            physical_minutes=lesson.period.duration_minutes,
            credit_minutes=lesson.credit_minutes,
        )
        db_session.add(row)
        await db_session.flush()
        for slice_ in lesson.slices:
            db_session.add(
                SchedulerLessonSliceV1(
                    organization_id=seed.organization.id,
                    school_year_id=seed.year.id,
                    lesson_id=row.id,
                    module_id=slice_.module_id,
                    offset_minutes=slice_.offset_minutes,
                    minutes=slice_.credit_minutes,
                )
            )
    seed.state.active_schedule_version_id = str(version.id)
    seed.state.school_year_publication_state = models.SchoolYearPublicationState.PUBLISHED
    seed.state.lock_version += 1
    if seed.organization.first_real_schedule_approved_at is None:
        seed.organization.first_real_schedule_approved_at = now_utc
    await db_session.commit()
    return version
