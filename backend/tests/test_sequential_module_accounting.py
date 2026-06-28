import pytest
from sqlalchemy import select

from app import models
from app.services import occurrence_service


pytestmark = pytest.mark.integration


def test_delivered_subject_hours_cross_module_boundary_and_reverse(sync_db):
    organization = models.Organization(name="Sequential Accounting", plan_status="active")
    sync_db.add(organization)
    sync_db.flush()
    course = models.Course(
        organization_id=organization.id,
        name="Course",
        abbreviation="SEQ",
    )
    subject = models.Subject(
        organization_id=organization.id,
        name="Mathematics",
        required_room_type=models.RoomType.normal,
    )
    sync_db.add_all([course, subject])
    sync_db.flush()
    class_ = models.Class(
        organization_id=organization.id,
        name="10A",
        size=20,
        start_year=2025,
        end_year=2026,
        grade_level=10,
        course_id=course.id,
    )
    first_module = models.Module(
        organization_id=organization.id,
        subject_id=subject.id,
        name="Module 1",
        hours_total=30,
        order=0,
    )
    second_module = models.Module(
        organization_id=organization.id,
        subject_id=subject.id,
        name="Module 2",
        hours_total=20,
        order=1,
    )
    sync_db.add_all([class_, first_module, second_module])
    sync_db.flush()
    sync_db.add(
        models.ClassProgress(
            organization_id=organization.id,
            class_id=class_.id,
            module_id=first_module.id,
            hours_completed=29,
            hours_debt=0,
            is_completed=False,
        )
    )
    sync_db.commit()

    applied = occurrence_service._apply_state_accounting(
        sync_db,
        organization_id=organization.id,
        class_id=class_.id,
        status=models.LessonOccurrenceStatus.GIVEN,
        planned_module_id=first_module.id,
        executed_module_id=first_module.id,
        planned_hours=2,
        direction=1,
    )
    occurrence_service._record_progress_ledger_entries(
        sync_db,
        organization_id=organization.id,
        source_type="TEST_DELIVERY",
        source_id=1,
        source_revision=1,
        class_id=class_.id,
        status=models.LessonOccurrenceStatus.GIVEN,
        planned_module_id=first_module.id,
        executed_module_id=first_module.id,
        planned_hours=2,
        direction=1,
        operation_id="sequential-forward",
        accounting_deltas=applied,
    )
    sync_db.flush()

    progress = {
        row.module_id: row
        for row in sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.organization_id == organization.id,
                models.ClassProgress.class_id == class_.id,
            )
        ).scalars()
    }
    assert progress[first_module.id].hours_completed == pytest.approx(30)
    assert progress[first_module.id].is_completed is True
    assert progress[second_module.id].hours_completed == pytest.approx(1)
    assert [delta[:2] for delta in applied] == [
        (first_module.id, 1),
        (second_module.id, 1),
    ]

    reversed_deltas = occurrence_service._apply_state_accounting(
        sync_db,
        organization_id=organization.id,
        class_id=class_.id,
        status=models.LessonOccurrenceStatus.GIVEN,
        planned_module_id=first_module.id,
        executed_module_id=first_module.id,
        planned_hours=2,
        direction=-1,
    )
    sync_db.flush()

    assert progress[first_module.id].hours_completed == pytest.approx(29)
    assert progress[first_module.id].is_completed is False
    assert progress[second_module.id].hours_completed == pytest.approx(0)
    assert [delta[:2] for delta in reversed_deltas] == [
        (second_module.id, -1),
        (first_module.id, -1),
    ]
    ledger_rows = sync_db.execute(
        select(models.ProgressLedgerEntry)
        .where(models.ProgressLedgerEntry.source_type == "TEST_DELIVERY")
        .order_by(models.ProgressLedgerEntry.id)
    ).scalars().all()
    assert [(row.module_id, row.completed_delta) for row in ledger_rows] == [
        (first_module.id, 1),
        (second_module.id, 1),
    ]
