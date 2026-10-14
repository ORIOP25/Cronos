"""W09 consumers: weekly map, lesson logs, occurrences and manual adjustments."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import and_, select

from app import models, schemas
from app.scheduler.infrastructure.models import (
    CurricularRequirement,
    SchedulerLessonLogV1,
    SchedulerLessonSliceV1,
    SchedulerLessonV1,
    SchedulerRecoveryReservationV1,
    SchedulerVersionV1,
)
from app.scheduler.infrastructure.operations import (
    adjust_class_progress,
    class_progress_map,
    record_lesson_log,
    week_schedule,
)
from app.scheduler.infrastructure.progress import load_executed_minutes, load_open_debt
from app.services.scheduler_state_service import SchedulerStateService
from tests._support.scheduler_v1 import (
    V1Seed,
    run_generation,
    seed_generatable_school,
)

pytestmark = pytest.mark.postgresql

MOMENT = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)


async def _minimal_school(
    db_session,
    *,
    clerk_user_id: str = "w09_admin",
    clerk_org_id: str = "w09_org",
    module_minutes: int = 100,
) -> V1Seed:
    return await seed_generatable_school(
        db_session,
        clerk_user_id=clerk_user_id,
        clerk_org_id=clerk_org_id,
        module_minutes=module_minutes,
    )


async def _publish_schedule(db_session, monkeypatch, seed: V1Seed) -> None:
    from tests._support.scheduler_v1 import publish_schedule

    await publish_schedule(db_session, monkeypatch, seed)


async def _two_module_school(db_session, *, suffix: str = ""):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id=f"w09_two_a{suffix}",
        clerk_org_id=f"w09_two_org{suffix}",
        module_minutes=75,
    )
    second = models.Module(
        organization_id=seed.organization.id,
        subject_id=seed.subject.id,
        name="Módulo B",
        required_minutes=75,
        order=2,
    )
    db_session.add(second)
    await db_session.flush()
    db_session.add(
        CurricularRequirement(
            organization_id=seed.organization.id,
            assignment_id=seed.assignment.id,
            module_id=second.id,
            sequence=second.order + 1,
            required_minutes=75,
        )
    )
    # The projection reads the selection, so the second module must be marked.
    link = await db_session.scalar(
        select(models.ClassSubjectLink).where(
            models.ClassSubjectLink.organization_id == seed.organization.id,
            models.ClassSubjectLink.class_id == seed.class_.id,
            models.ClassSubjectLink.subject_id == seed.subject.id,
        )
    )
    await db_session.execute(
        models.class_subject_module.insert().values(
            organization_id=seed.organization.id,
            class_subject_link_id=link.id,
            module_id=second.id,
        )
    )
    await db_session.commit()
    return seed, second


async def _crossing_lesson(db_session, seed: V1Seed) -> SchedulerLessonV1:
    lessons = (
        await db_session.scalars(
            select(SchedulerLessonV1)
            .where(SchedulerLessonV1.organization_id == seed.organization.id)
            .order_by(SchedulerLessonV1.school_date, SchedulerLessonV1.id)
        )
    ).all()
    slices = (
        await db_session.scalars(
            select(SchedulerLessonSliceV1).where(
                SchedulerLessonSliceV1.organization_id == seed.organization.id,
                SchedulerLessonSliceV1.lesson_id.in_([row.id for row in lessons]),
            )
        )
    ).all()
    modules_by_lesson: dict[int, set[int]] = {}
    for row in slices:
        modules_by_lesson.setdefault(row.lesson_id, set()).add(row.module_id)
    for lesson in lessons:
        if len(modules_by_lesson.get(lesson.id, ())) > 1:
            return lesson
    raise AssertionError("The generated schedule has no lesson crossing two modules.")


async def _first_lesson(db_session, seed: V1Seed) -> SchedulerLessonV1:
    return await db_session.scalar(
        select(SchedulerLessonV1)
        .where(SchedulerLessonV1.organization_id == seed.organization.id)
        .order_by(SchedulerLessonV1.id)
    )


async def _first_occurrence(db_session, seed: V1Seed) -> dict:
    from app.scheduler.infrastructure import occurrences as occurrences_v1

    page = await occurrences_v1.list_occurrences(db_session, seed.organization.id)
    return page["items"][0]


async def _decide_gap(db_session, seed: V1Seed, item: dict, *, now: datetime) -> dict:
    from app.scheduler.infrastructure import occurrences as occurrences_v1

    decided = await occurrences_v1.update_occurrence(
        db_session,
        seed.organization.id,
        item["id"],
        schemas.LessonOccurrenceUpdate(
            status=models.LessonOccurrenceStatus.GAP, version=item["version"]
        ),
        decided_by_membership_id=seed.membership.id,
        now_utc=now,
    )
    await db_session.commit()
    return decided


async def test_a_completed_lesson_log_credits_the_ledger_once(db_session, monkeypatch):
    seed = await _minimal_school(db_session)
    await db_session.commit()
    await _publish_schedule(db_session, monkeypatch, seed)
    lesson = await _first_lesson(db_session, seed)

    result = await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson.id,
        status="COMPLETED",
        summary="Primeira aula.",
        notes=None,
        now_utc=lesson.ends_at,
    )
    await db_session.commit()
    assert result["credited_minutes"] == lesson.credit_minutes

    executed = await load_executed_minutes(db_session, seed.organization.id, [lesson.assignment_id])
    assert sum(executed[lesson.assignment_id].values()) == lesson.credit_minutes

    replay = await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson.id,
        status="COMPLETED",
        summary="Primeira aula.",
        notes=None,
        now_utc=lesson.ends_at,
    )
    await db_session.commit()
    assert replay["credited_minutes"] == 0
    executed = await load_executed_minutes(db_session, seed.organization.id, [lesson.assignment_id])
    assert sum(executed[lesson.assignment_id].values()) == lesson.credit_minutes

    log = await db_session.scalar(
        select(SchedulerLessonLogV1).where(SchedulerLessonLogV1.lesson_id == lesson.id)
    )
    assert log.status == "COMPLETED"
    assert log.revision == 1


async def test_an_occurrence_defers_debt_until_the_decision_and_completion_settles_it(
    db_session, monkeypatch
):
    seed = await _minimal_school(db_session)
    await db_session.commit()
    await _publish_schedule(db_session, monkeypatch, seed)
    lesson = await _first_lesson(db_session, seed)

    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson.id,
        status="OCCURRENCE",
        summary="Falta do professor.",
        notes=None,
        now_utc=lesson.ends_at,
        planning_relevant=True,
    )
    await db_session.commit()
    open_debt, _ = await load_open_debt(db_session, seed.organization.id, [lesson.assignment_id])
    assert sum(open_debt.values()) == 0, "Ocorrência pendente não cria dívida."

    item = await _first_occurrence(db_session, seed)
    decided = await _decide_gap(db_session, seed, item, now=lesson.ends_at)
    assert decided["operational_state"] == "DECIDED_GAP"
    open_debt, _ = await load_open_debt(db_session, seed.organization.id, [lesson.assignment_id])
    assert sum(open_debt.values()) == lesson.credit_minutes

    from app.scheduler.infrastructure import occurrences as occurrences_v1

    given = await occurrences_v1.update_occurrence(
        db_session,
        seed.organization.id,
        item["id"],
        schemas.LessonOccurrenceUpdate(
            status=models.LessonOccurrenceStatus.GIVEN, version=decided["version"]
        ),
        decided_by_membership_id=seed.membership.id,
        now_utc=lesson.ends_at,
    )
    await db_session.commit()
    assert given["operational_state"] == "DECIDED_GIVEN"
    open_debt, _ = await load_open_debt(db_session, seed.organization.id, [lesson.assignment_id])
    assert sum(open_debt.values()) == 0
    executed = await load_executed_minutes(db_session, seed.organization.id, [lesson.assignment_id])
    assert sum(executed[lesson.assignment_id].values()) == lesson.credit_minutes


async def test_manual_adjustments_add_and_remove_minutes(db_session, monkeypatch):
    seed = await _minimal_school(db_session)
    await db_session.commit()
    await _publish_schedule(db_session, monkeypatch, seed)

    handled = await adjust_class_progress(
        db_session,
        seed.organization.id,
        seed.class_.id,
        [schemas.ClassProgressUpdate(module_id=seed.module.id, hours_completed=1.0)],
        membership_id=seed.membership.id,
        now_utc=MOMENT,
    )
    assert handled is True
    await db_session.commit()
    executed = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert executed[seed.assignment.id][seed.module.id] == 60

    await adjust_class_progress(
        db_session,
        seed.organization.id,
        seed.class_.id,
        [schemas.ClassProgressUpdate(module_id=seed.module.id, hours_completed=0.5)],
        membership_id=seed.membership.id,
        now_utc=MOMENT,
    )
    await db_session.commit()
    executed = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert executed[seed.assignment.id][seed.module.id] == 30

    progress = await class_progress_map(db_session, seed.organization.id, seed.class_.id)
    assert progress is not None
    assert progress[seed.module.id][0] == 30


async def test_the_week_map_exposes_multiple_slices_and_conserved_minutes(db_session, monkeypatch):
    seed = await _minimal_school(db_session, module_minutes=100)
    await db_session.commit()
    await _publish_schedule(db_session, monkeypatch, seed)
    lessons = (
        await db_session.scalars(
            select(SchedulerLessonV1)
            .where(SchedulerLessonV1.organization_id == seed.organization.id)
            .order_by(SchedulerLessonV1.school_date, SchedulerLessonV1.id)
        )
    ).all()
    assert lessons
    target = lessons[0]
    week_start = target.school_date - timedelta(days=target.school_date.weekday())
    slots = await week_schedule(
        db_session,
        seed.organization.id,
        week_start=week_start,
        class_id=seed.class_.id,
        teacher_id=None,
        today=date(2026, 9, 1),
    )
    assert slots is not None
    slot = next(row for row in slots if row["scheduler_lesson_id"] == target.id)
    local_start = target.starts_at.astimezone(ZoneInfo(seed.year.timezone))
    assert slot["credit_minutes"] == target.credit_minutes
    assert sum(parcel["minutes"] for parcel in slot["slices"]) == target.credit_minutes
    assert slot["timeslot"]["start_time"] == local_start.strftime("%H:%M")
    assert slot["subject"]["id"] == seed.subject.id
    assert slot["slices"][0]["module_id"] == seed.module.id


async def test_manual_reductions_are_per_module_on_a_crossing_lesson(db_session, monkeypatch):
    seed, second = await _two_module_school(db_session)
    await _publish_schedule(db_session, monkeypatch, seed)
    lesson = await _crossing_lesson(db_session, seed)

    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson.id,
        status="COMPLETED",
        summary="Aula cruzando módulos.",
        notes=None,
        now_utc=lesson.ends_at,
    )
    await db_session.commit()
    executed = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert executed[seed.assignment.id][seed.module.id] == 25
    assert executed[seed.assignment.id][second.id] == 25

    await adjust_class_progress(
        db_session,
        seed.organization.id,
        seed.class_.id,
        [
            schemas.ClassProgressUpdate(module_id=seed.module.id, hours_completed=0.0),
            schemas.ClassProgressUpdate(module_id=second.id, hours_completed=0.0),
        ],
        membership_id=seed.membership.id,
        now_utc=MOMENT,
    )
    await db_session.commit()
    executed = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert executed[seed.assignment.id][seed.module.id] == 0
    assert executed[seed.assignment.id][second.id] == 0


async def test_an_occurrence_reverses_only_the_remaining_module_balance(db_session, monkeypatch):
    seed, second = await _two_module_school(db_session, suffix="_occ")
    await _publish_schedule(db_session, monkeypatch, seed)
    lesson = await _crossing_lesson(db_session, seed)

    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson.id,
        status="COMPLETED",
        summary="Aula dada.",
        notes=None,
        now_utc=lesson.ends_at,
    )
    await db_session.commit()
    await adjust_class_progress(
        db_session,
        seed.organization.id,
        seed.class_.id,
        [schemas.ClassProgressUpdate(module_id=seed.module.id, hours_completed=0.0)],
        membership_id=seed.membership.id,
        now_utc=MOMENT,
    )
    await db_session.commit()

    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson.id,
        status="OCCURRENCE",
        summary="Aula não dada.",
        notes=None,
        now_utc=lesson.ends_at,
        planning_relevant=True,
    )
    await db_session.commit()
    item = await _first_occurrence(db_session, seed)
    await _decide_gap(db_session, seed, item, now=lesson.ends_at)
    executed = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert executed[seed.assignment.id][seed.module.id] == 0
    assert executed[seed.assignment.id][second.id] == 0
    open_debt, _ = await load_open_debt(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(open_debt.values()) == lesson.credit_minutes


async def test_a_completed_lesson_log_follows_the_lesson_into_the_next_version(
    db_session, monkeypatch
):

    seed = await _minimal_school(db_session)
    await db_session.commit()
    await _publish_schedule(db_session, monkeypatch, seed)
    lessons = (
        await db_session.scalars(
            select(SchedulerLessonV1)
            .where(SchedulerLessonV1.organization_id == seed.organization.id)
            .order_by(SchedulerLessonV1.school_date, SchedulerLessonV1.id)
        )
    ).all()
    target = lessons[0]
    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=target.id,
        status="COMPLETED",
        summary="Sumário persistente.",
        notes=None,
        now_utc=target.ends_at,
    )
    await db_session.commit()
    executed_before = await load_executed_minutes(
        db_session, seed.organization.id, [seed.assignment.id]
    )
    assert sum(executed_before[seed.assignment.id].values()) == target.credit_minutes

    state = await SchedulerStateService(db_session).get_state(seed.organization.id, seed.year.id)
    await db_session.refresh(state)
    state.input_revision += 1
    state.planning_revision += 1
    await db_session.commit()
    later = MOMENT + timedelta(days=21)
    await run_generation(db_session, monkeypatch, seed, key="repair-log", now=later)

    active_version_id = await db_session.scalar(
        select(SchedulerVersionV1.id).where(
            SchedulerVersionV1.organization_id == seed.organization.id,
            SchedulerVersionV1.status == "ACTIVE",
        )
    )
    rows = (
        await db_session.execute(
            select(SchedulerLessonLogV1, SchedulerLessonV1)
            .join(
                SchedulerLessonV1,
                and_(
                    SchedulerLessonV1.organization_id == SchedulerLessonLogV1.organization_id,
                    SchedulerLessonV1.school_year_id == SchedulerLessonLogV1.school_year_id,
                    SchedulerLessonV1.id == SchedulerLessonLogV1.lesson_id,
                ),
            )
            .where(SchedulerLessonV1.version_id == active_version_id)
        )
    ).all()
    assert len(rows) == 1
    log, new_lesson = rows[0]
    assert new_lesson.stable_key == target.stable_key
    assert new_lesson.school_date == target.school_date
    assert new_lesson.starts_at == target.starts_at
    assert log.status == "COMPLETED"
    assert log.summary == "Sumário persistente."

    week_start = target.school_date - timedelta(days=target.school_date.weekday())
    slots = await week_schedule(
        db_session,
        seed.organization.id,
        week_start=week_start,
        class_id=seed.class_.id,
        teacher_id=None,
        today=MOMENT.date(),
    )
    slot = next(row for row in slots if row["scheduler_lesson_id"] == new_lesson.id)
    assert slot["lesson_log_status"] == "COMPLETED"
    assert slot["lesson_log_summary"] == "Sumário persistente."

    executed = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(executed[seed.assignment.id].values()) == target.credit_minutes


async def test_a_repair_persists_planned_recovery_allocations(db_session, monkeypatch):

    seed = await _minimal_school(db_session)
    await db_session.commit()
    await _publish_schedule(db_session, monkeypatch, seed)
    lessons = (
        await db_session.scalars(
            select(SchedulerLessonV1)
            .where(SchedulerLessonV1.organization_id == seed.organization.id)
            .order_by(SchedulerLessonV1.school_date, SchedulerLessonV1.id)
        )
    ).all()
    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lessons[0].id,
        status="OCCURRENCE",
        summary="Falta.",
        notes=None,
        now_utc=MOMENT,
        planning_relevant=True,
    )
    await db_session.commit()
    open_debt, _ = await load_open_debt(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(open_debt.values()) == 0
    item = await _first_occurrence(db_session, seed)
    await _decide_gap(db_session, seed, item, now=lessons[0].ends_at)
    open_debt, _ = await load_open_debt(db_session, seed.organization.id, [seed.assignment.id])
    owed = sum(open_debt.values())
    assert owed == lessons[0].credit_minutes

    state = await SchedulerStateService(db_session).get_state(seed.organization.id, seed.year.id)
    await db_session.refresh(state)
    state.input_revision += 1
    state.planning_revision += 1
    await db_session.commit()
    await run_generation(db_session, monkeypatch, seed, key="repair-alloc")

    active_version_id = await db_session.scalar(
        select(SchedulerVersionV1.id).where(
            SchedulerVersionV1.organization_id == seed.organization.id,
            SchedulerVersionV1.status == "ACTIVE",
        )
    )
    reservations = (
        await db_session.scalars(
            select(SchedulerRecoveryReservationV1).where(
                SchedulerRecoveryReservationV1.organization_id == seed.organization.id,
                SchedulerRecoveryReservationV1.version_id == active_version_id,
            )
        )
    ).all()
    assert reservations, "A reparação deve planear a recuperação da dívida."
    assert sum(row.minutes for row in reservations) == owed
    version_lessons = {
        row.id: row.credit_minutes
        for row in (
            await db_session.scalars(
                select(SchedulerLessonV1).where(
                    SchedulerLessonV1.organization_id == seed.organization.id,
                    SchedulerLessonV1.version_id == active_version_id,
                )
            )
        ).all()
    }
    reserved_by_lesson: dict[int, int] = {}
    for row in reservations:
        reserved_by_lesson[row.lesson_id] = reserved_by_lesson.get(row.lesson_id, 0) + row.minutes
    for lesson_id, minutes in reserved_by_lesson.items():
        assert minutes <= version_lessons[lesson_id]
    reserved_by_claim: dict[int, int] = {}
    for row in reservations:
        reserved_by_claim[row.debt_id] = reserved_by_claim.get(row.debt_id, 0) + row.minutes
    for minutes in reserved_by_claim.values():
        assert minutes <= owed
