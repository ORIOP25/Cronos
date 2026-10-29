"""Regeneration reads current calendar, resources, preferences and manual credit."""

import pytest
from sqlalchemy import select

from app import models, schemas
from app.scheduler.domain.candidate import CandidateSchedule, SchedulingStrategy
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.infrastructure.models import SchedulerJobV1, SchedulerLessonV1
from app.scheduler.infrastructure.operations import adjust_class_progress
from app.scheduler.infrastructure.queries import current_proposal
from app.scheduler.infrastructure.snapshot import SnapshotConfigurationError, load_snapshot
from app.services import room_service, schedule_service, settings_service
from tests._support.scheduler_v1 import (
    MOMENT,
    run_generation,
    run_job,
    seed_generatable_school,
    seed_published_baseline,
    set_stability_window,
)


async def active_lessons(db, seed):
    return tuple(
        (
            await db.scalars(
                select(SchedulerLessonV1)
                .where(
                    SchedulerLessonV1.organization_id == seed.organization.id,
                    SchedulerLessonV1.version_id == int(seed.state.active_schedule_version_id),
                )
                .order_by(SchedulerLessonV1.starts_at)
            )
        ).all()
    )


@pytest.mark.parametrize(
    "change",
    [
        "holiday",
        "pause",
        "room",
        "room_added",
        "teacher",
        "preference",
        "manual_credit",
        "manual_partial_credit",
    ],
)
async def test_published_schedule_can_be_regenerated_after_configuration_changes(
    db_session, monkeypatch, change
):
    seed = await seed_generatable_school(
        db_session,
        clerk_org_id=f"adaptive_change_{change}",
        clerk_user_id=f"adaptive_change_admin_{change}",
        module_minutes=150,
    )
    await db_session.commit()
    # The scenario tests regeneration, not the stability window.
    await set_stability_window(db_session, seed, 0)
    await seed_published_baseline(db_session, seed)
    previous = await active_lessons(db_session, seed)
    changed_date = previous[0].school_date
    if change in ("holiday", "pause"):
        await settings_service.create_calendar_event(
            db_session,
            seed.organization.id,
            schemas.SchoolCalendarEventCreate(
                name="Alteração de calendário",
                start_date=changed_date,
                end_date=changed_date,
                event_type=(
                    models.CalendarEventType.national_holiday
                    if change == "holiday"
                    else models.CalendarEventType.school_break
                ),
            ),
        )
    elif change == "room":
        await room_service.create_room(
            db_session,
            schemas.RoomCreate(name="Nova sala", capacity=25, room_type_id=seed.room.room_type_id),
            seed.organization.id,
        )
        await room_service.update_room(
            db_session, seed.room.id, schemas.RoomUpdate(capacity=5), seed.organization.id
        )
    elif change == "room_added":
        await room_service.create_room(
            db_session,
            schemas.RoomCreate(
                name="Sala adicional", capacity=25, room_type_id=seed.room.room_type_id
            ),
            seed.organization.id,
        )
    elif change == "teacher":
        await schedule_service.create_constraint(
            db_session,
            schemas.TeacherUnavailableConstraintCreate(
                rule_type=schemas.SupportedConstraintType.teacher_unavailable,
                rule_payload=schemas.TeacherUnavailablePayload(
                    teacher_id=seed.assignment.teacher_id,
                    day_of_week=changed_date.weekday(),
                ),
            ),
            seed.organization.id,
        )
    elif change == "preference":
        slot = await db_session.scalar(
            select(models.Timeslot).where(
                models.Timeslot.organization_id == seed.organization.id,
                models.Timeslot.day_of_week == 1,
            )
        )
        await schedule_service.create_constraint(
            db_session,
            schemas.TeacherPreferredConstraintCreate(
                rule_type=schemas.SupportedConstraintType.teacher_preferred,
                rule_payload=schemas.TeacherPreferredPayload(
                    teacher_id=seed.assignment.teacher_id,
                    timeslot_id=slot.id,
                ),
            ),
            seed.organization.id,
        )
    else:
        assert await adjust_class_progress(
            db_session,
            seed.organization.id,
            seed.class_.id,
            [
                schemas.ClassProgressUpdate(
                    module_id=seed.module.id,
                    hours_completed=(25 if change == "manual_partial_credit" else 50) / 60,
                )
            ],
            membership_id=seed.membership.id,
            now_utc=MOMENT,
        )
    await db_session.commit()
    before = await load_snapshot(
        db_session,
        seed.organization.id,
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        now_utc=MOMENT,
        school_year_id=seed.year.id,
    )
    if change == "preference":
        assert before.snapshot.soft_unavailable
    await run_generation(
        db_session,
        monkeypatch,
        seed,
        key=f"changed:{change}:{seed.organization.id}",
        now=MOMENT,
    )
    current = await active_lessons(db_session, seed)
    assert int(seed.state.active_schedule_version_id) != previous[0].version_id
    if change in ("holiday", "pause", "teacher"):
        assert all(row.school_date != changed_date for row in current)
    if change == "room":
        assert all(row.room_id != seed.room.id for row in current)
    if change in ("manual_credit", "manual_partial_credit"):
        assert sum(row.credit_minutes for row in current) == (
            125 if change == "manual_partial_credit" else 100
        )
    else:
        assert sum(row.credit_minutes for row in current) == 150
    after = await load_snapshot(
        db_session,
        seed.organization.id,
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        now_utc=MOMENT,
        school_year_id=seed.year.id,
    )
    assert validate_candidate(
        after.snapshot, CandidateSchedule(after.snapshot.baseline_lessons)
    ).valid


async def test_manual_reduction_of_progress_restores_the_new_debt_in_the_future(
    db_session, monkeypatch
):
    seed = await seed_generatable_school(
        db_session,
        clerk_org_id="adaptive_manual_reduction",
        module_minutes=150,
    )
    await db_session.commit()
    # The scenario tests regeneration, not the stability window.
    await set_stability_window(db_session, seed, 0)
    await seed_published_baseline(db_session, seed)
    for minutes in (50, 0):
        await adjust_class_progress(
            db_session,
            seed.organization.id,
            seed.class_.id,
            [schemas.ClassProgressUpdate(module_id=seed.module.id, hours_completed=minutes / 60)],
            membership_id=seed.membership.id,
            now_utc=MOMENT,
        )
        await db_session.commit()
        await run_generation(
            db_session,
            monkeypatch,
            seed,
            key=f"manual:{minutes}:{seed.organization.id}",
            now=MOMENT,
        )
        rows = await active_lessons(db_session, seed)
        assert sum(row.credit_minutes for row in rows) == 150 - minutes


async def test_holiday_on_a_protected_lesson_inside_the_window_does_not_move_it(
    db_session, monkeypatch
):
    seed = await seed_generatable_school(
        db_session,
        clerk_org_id="adaptive_protected_holiday",
        module_minutes=150,
    )
    await db_session.commit()
    await seed_published_baseline(db_session, seed)
    previous = await active_lessons(db_session, seed)
    await settings_service.create_calendar_event(
        db_session,
        seed.organization.id,
        schemas.SchoolCalendarEventCreate(
            name="Feriado sobre aula protegida",
            start_date=previous[0].school_date,
            end_date=previous[0].school_date,
            event_type=models.CalendarEventType.national_holiday,
        ),
    )
    await db_session.commit()

    await run_job(db_session, monkeypatch, seed, key=f"protected-holiday:{seed.organization.id}")

    job = await db_session.scalar(
        select(SchedulerJobV1)
        .where(SchedulerJobV1.organization_id == seed.organization.id)
        .order_by(SchedulerJobV1.id.desc())
    )
    assert job.status == "FAILED"
    assert await current_proposal(db_session, seed.organization.id) is None
    assert int(seed.state.active_schedule_version_id) == previous[0].version_id
    assert tuple(row.id for row in await active_lessons(db_session, seed)) == tuple(
        row.id for row in previous
    )


async def test_manual_credit_inside_the_window_is_refused_with_a_clear_error(db_session):
    seed = await seed_generatable_school(
        db_session,
        clerk_org_id="adaptive_protected_credit",
        module_minutes=150,
    )
    await db_session.commit()
    await seed_published_baseline(db_session, seed)
    await adjust_class_progress(
        db_session,
        seed.organization.id,
        seed.class_.id,
        [schemas.ClassProgressUpdate(module_id=seed.module.id, hours_completed=50 / 60)],
        membership_id=seed.membership.id,
        now_utc=MOMENT,
    )
    await db_session.commit()

    with pytest.raises(SnapshotConfigurationError) as error:
        await load_snapshot(
            db_session,
            seed.organization.id,
            strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
            now_utc=MOMENT,
            school_year_id=seed.year.id,
        )

    assert error.value.code == "PROTECTED_LESSON_EXCEEDS_CURRICULUM"
    assert "janela de estabilidade" in str(error.value)
