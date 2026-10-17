from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from alembic import command
from app import models
from app.db.database import Base
from app.scheduler.infrastructure.models import (
    CurricularAssignment,
    SchedulerJobV1,
    SchedulerLessonV1,
    SchedulerProposalV1,
    SchedulerVersionV1,
)
from scripts.audit_database_integrity import _audit_connection
from tests._support.db_fixtures import (
    _alembic_config,
    create_completed_organization,
    create_teacher_profile,
    get_school_room_type_id,
    runtime_sync_test_engine,
    sync_test_engine,
)

pytestmark = pytest.mark.postgresql

CURRICULAR_TABLES = {
    "curricular_assignment",
    "curricular_requirement",
    "curricular_execution",
    "curricular_execution_credit",
    "curricular_debt",
    "curricular_debt_revision",
    "curricular_debt_settlement",
    "scheduler_version_v1",
    "scheduler_lesson_v1",
    "scheduler_lesson_slice_v1",
    "scheduler_recovery_reservation_v1",
    "scheduler_job_v1",
    "scheduler_proposal_v1",
}

MUTABLE_CURRICULAR_TABLES = {
    "curricular_assignment",
    "curricular_requirement",
    "scheduler_version_v1",
    "scheduler_job_v1",
    "scheduler_proposal_v1",
}


def test_w02_alembic_metadata_matches_installed_schema(clean_database):
    command.check(_alembic_config())


def test_w02_installed_schema_passes_the_integrity_audit(clean_database):
    with sync_test_engine.connect() as connection:
        assert _audit_connection(connection) == []


def test_w02_empty_database_migration_roundtrip(clean_database):
    config = _alembic_config()
    try:
        command.downgrade(config, "base")
    finally:
        command.upgrade(config, "head")
    command.check(config)


def test_w02_curricular_tables_are_installed_with_forced_tenant_rls(clean_database):
    with sync_test_engine.connect() as connection:
        installed = {
            row.relname: (row.relrowsecurity, row.relforcerowsecurity)
            for row in connection.execute(
                text(
                    """
                    SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public' AND c.relkind = 'r'
                    """
                )
            )
        }

    assert CURRICULAR_TABLES <= installed.keys()
    assert all(installed[name] == (True, True) for name in CURRICULAR_TABLES)


def test_w02_curricular_models_match_columns_and_evidence_is_append_only(clean_database):
    evidence_tables = CURRICULAR_TABLES - MUTABLE_CURRICULAR_TABLES
    with sync_test_engine.connect() as connection:
        inspector = inspect(connection)
        for table_name in CURRICULAR_TABLES:
            actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
            model_columns = set(Base.metadata.tables[table_name].c.keys())
            assert actual_columns == model_columns
        for table_name in evidence_tables:
            privileges = connection.execute(
                text(
                    """
                    SELECT has_table_privilege('cronos_app', :table_name, 'SELECT'),
                           has_table_privilege('cronos_app', :table_name, 'INSERT'),
                           has_table_privilege('cronos_app', :table_name, 'UPDATE'),
                           has_table_privilege('cronos_app', :table_name, 'DELETE')
                    """
                ),
                {"table_name": f"public.{table_name}"},
            ).one()
            assert privileges == (True, True, False, False)


@pytest.mark.asyncio
async def test_w02_assignment_rejects_other_school_class_and_rls_hides_rows(db_session):
    organization, _ = await create_completed_organization(
        db_session, clerk_user_id="w02_admin_a", clerk_org_id="w02_org_a"
    )
    other, _ = await create_completed_organization(
        db_session, clerk_user_id="w02_admin_b", clerk_org_id="w02_org_b"
    )
    course_a = models.Course(name="Course A", abbreviation="A", organization_id=organization.id)
    course_b = models.Course(name="Course B", abbreviation="B", organization_id=other.id)
    subject = models.Subject(
        name="Mathematics",
        organization_id=organization.id,
        room_type_id=await get_school_room_type_id(db_session, organization.id, "Normal"),
    )
    year = models.SchedulerSchoolYear(
        organization_id=organization.id,
        label="2026/27",
        start_date=date(2026, 9, 1),
        hard_end_date=date(2027, 7, 31),
    )
    db_session.add_all((course_a, course_b, subject, year))
    await db_session.flush()
    class_a = models.Class(
        name="A",
        size=20,
        start_year=2026,
        end_year=2029,
        grade_level=10,
        course_id=course_a.id,
        organization_id=organization.id,
    )
    class_b = models.Class(
        name="B",
        size=20,
        start_year=2026,
        end_year=2029,
        grade_level=10,
        course_id=course_b.id,
        organization_id=other.id,
    )
    db_session.add_all((class_a, class_b))
    await db_session.flush()
    teacher = await create_teacher_profile(db_session, organization_id=organization.id)

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                CurricularAssignment(
                    organization_id=organization.id,
                    school_year_id=year.id,
                    class_id=class_b.id,
                    subject_id=subject.id,
                    teacher_id=teacher.id,
                )
            )
            await db_session.flush()

    assignment = CurricularAssignment(
        organization_id=organization.id,
        school_year_id=year.id,
        class_id=class_a.id,
        subject_id=subject.id,
        teacher_id=teacher.id,
    )
    db_session.add(assignment)
    await db_session.commit()

    with runtime_sync_test_engine.begin() as connection:
        connection.execute(
            text("SELECT set_config('app.current_organization_id', :id, true)"),
            {"id": str(organization.id)},
        )
        visible_here = connection.scalar(text("SELECT count(*) FROM curricular_assignment"))
        connection.execute(
            text("SELECT set_config('app.current_organization_id', :id, true)"),
            {"id": str(other.id)},
        )
        visible_elsewhere = connection.scalar(text("SELECT count(*) FROM curricular_assignment"))

    assert visible_here == 1
    assert visible_elsewhere == 0

    room = models.Room(
        name="A1",
        capacity=25,
        organization_id=organization.id,
        room_type_id=await get_school_room_type_id(db_session, organization.id, "Normal"),
    )
    other_room = models.Room(
        name="B1",
        capacity=25,
        organization_id=other.id,
        room_type_id=await get_school_room_type_id(db_session, other.id, "Normal"),
    )
    db_session.add_all((room, other_room))
    await db_session.flush()
    approved_at = datetime(2026, 9, 23, 10, tzinfo=UTC)
    active = SchedulerVersionV1(
        organization_id=organization.id,
        school_year_id=year.id,
        origin="generation:1",
        status="ACTIVE",
        snapshot_digest="a" * 64,
        created_at=approved_at,
        approved_at=approved_at,
    )
    db_session.add(active)
    await db_session.flush()
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                SchedulerVersionV1(
                    organization_id=organization.id,
                    school_year_id=year.id,
                    origin="generation:2",
                    status="ACTIVE",
                    snapshot_digest="b" * 64,
                    created_at=approved_at,
                    approved_at=approved_at,
                )
            )
            await db_session.flush()

    candidate = SchedulerVersionV1(
        organization_id=organization.id,
        school_year_id=year.id,
        origin="generation:2",
        status="CANDIDATE",
        snapshot_digest="b" * 64,
        previous_version_id=active.id,
        created_at=approved_at,
    )
    db_session.add(candidate)
    await db_session.flush()
    start = approved_at + timedelta(days=1)
    original = SchedulerLessonV1(
        organization_id=organization.id,
        school_year_id=year.id,
        version_id=active.id,
        assignment_id=assignment.id,
        stable_key="lesson:1",
        school_date=start.date(),
        starts_at=start,
        ends_at=start + timedelta(minutes=50),
        room_id=room.id,
        physical_minutes=50,
        credit_minutes=50,
    )
    db_session.add(original)
    await db_session.flush()
    moved = SchedulerLessonV1(
        organization_id=organization.id,
        school_year_id=year.id,
        version_id=candidate.id,
        assignment_id=assignment.id,
        stable_key="lesson:1",
        source_lesson_id=original.id,
        school_date=start.date(),
        starts_at=start + timedelta(minutes=50),
        ends_at=start + timedelta(minutes=100),
        room_id=room.id,
        physical_minutes=50,
        credit_minutes=20,
    )
    db_session.add(moved)
    await db_session.flush()
    assert moved.source_lesson_id == original.id
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                SchedulerLessonV1(
                    organization_id=organization.id,
                    school_year_id=year.id,
                    version_id=candidate.id,
                    assignment_id=assignment.id,
                    stable_key="lesson:1",
                    school_date=start.date(),
                    starts_at=start,
                    ends_at=start + timedelta(minutes=50),
                    room_id=room.id,
                    physical_minutes=50,
                    credit_minutes=50,
                )
            )
            await db_session.flush()
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            moved.room_id = other_room.id
            await db_session.flush()


@pytest.mark.asyncio
async def test_w02_job_and_proposal_lifecycle_constraints(db_session):
    organization, _ = await create_completed_organization(
        db_session, clerk_user_id="w02_job_admin", clerk_org_id="w02_job_org"
    )
    year = models.SchedulerSchoolYear(
        organization_id=organization.id,
        label="2026/27",
        start_date=date(2026, 9, 1),
        hard_end_date=date(2027, 7, 31),
    )
    db_session.add(year)
    await db_session.flush()
    queued_at = datetime(2026, 9, 23, 10, tzinfo=UTC)

    job = SchedulerJobV1(
        organization_id=organization.id,
        school_year_id=year.id,
        strategy="COMPLETE_GENERATION",
        status="QUEUED",
        origin="request:1",
        revision=1,
        attempt_token=1,
        queued_at=queued_at,
    )
    db_session.add(job)
    await db_session.flush()
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                SchedulerJobV1(
                    organization_id=organization.id,
                    school_year_id=year.id,
                    strategy="ADAPTIVE_RECOVERY",
                    status="RUNNING",
                    origin="request:2",
                    revision=1,
                    attempt_token=1,
                    queued_at=queued_at,
                )
            )
            await db_session.flush()

    job.status = "SUCCEEDED"
    job.finished_at = queued_at
    await db_session.flush()
    later_job = SchedulerJobV1(
        organization_id=organization.id,
        school_year_id=year.id,
        strategy="ADAPTIVE_RECOVERY",
        status="QUEUED",
        origin="request:3",
        revision=2,
        attempt_token=1,
        queued_at=queued_at,
    )
    db_session.add(later_job)
    await db_session.flush()

    proposal = SchedulerProposalV1(
        organization_id=organization.id,
        school_year_id=year.id,
        job_id=later_job.id,
        status="PENDING",
        snapshot_digest="c" * 64,
        policy_version="quality-v1",
        input_revision_used=0,
        planning_revision_used=0,
        created_at=queued_at,
    )
    db_session.add(proposal)
    await db_session.flush()
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                SchedulerProposalV1(
                    organization_id=organization.id,
                    school_year_id=year.id,
                    job_id=job.id,
                    status="PENDING",
                    snapshot_digest="d" * 64,
                    policy_version="quality-v1",
                    input_revision_used=0,
                    planning_revision_used=0,
                    created_at=queued_at,
                )
            )
            await db_session.flush()
