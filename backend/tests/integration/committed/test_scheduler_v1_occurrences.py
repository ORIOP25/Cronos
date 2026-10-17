"""R89.08: the administrative occurrence page uses the v1 ledger as truth."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from itertools import pairwise

import pytest
from sqlalchemy import select

from app import models, schemas
from app.core.exceptions import AppError
from app.scheduler.domain.debt import DebtOrigin
from app.scheduler.infrastructure import occurrences as occurrences_v1
from app.scheduler.infrastructure.models import (
    CurricularAssignment,
    CurricularRequirement,
    SchedulerLessonLogV1,
    SchedulerLessonV1,
    SchedulerRecoveryReservationV1,
    SchedulerVersionV1,
)
from app.scheduler.infrastructure.operations import (
    lesson_context,
    record_lesson_log,
    reverse_lesson_execution,
    week_schedule,
)
from app.scheduler.infrastructure.progress import load_executed_minutes, load_open_debt, record_debt
from app.scheduler.infrastructure.snapshot import load_snapshot
from app.services.dashboard_service import get_dashboard_summary
from app.services.teacher_service import get_teacher_progress
from tests._support.db_fixtures import create_teacher_profile
from tests._support.scheduler_v1 import (
    MOMENT,
    V1Seed,
    add_lesson,
    add_version,
    run_generation,
    seed_generatable_school,
    seed_published_baseline,
)

pytestmark = pytest.mark.postgresql


@pytest.mark.parametrize(
    "provisional_debt,already_revoked,broken_lineage",
    [
        (False, False, False),
        (True, False, False),
        (True, True, False),
        (True, False, True),
        (True, True, True),
    ],
)
async def test_premature_historical_credit_is_visible_and_reversible(
    db_session, monkeypatch, provisional_debt, already_revoked, broken_lineage
):
    seed = await _school(db_session, suffix="_historical")
    await db_session.commit()
    await seed_published_baseline(db_session, seed)
    lesson = (await _lessons(db_session, seed))[0]
    if provisional_debt:
        await record_debt(
            db_session,
            seed.organization.id,
            seed.year.id,
            seed.assignment.id,
            DebtOrigin(
                origin=f"lesson-occurrence:{lesson.id}",
                revision=1,
                origin_date=lesson.school_date,
                minutes=lesson.credit_minutes,
                author_id=seed.membership.id,
                reason="Dívida provisória histórica QA",
                recorded_at=MOMENT,
            ),
        )
    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson.id,
        status="COMPLETED",
        summary="Registo histórico QA",
        notes=None,
        now_utc=lesson.ends_at,
    )
    log = await db_session.scalar(
        select(SchedulerLessonLogV1).where(
            SchedulerLessonLogV1.organization_id == seed.organization.id,
            SchedulerLessonLogV1.lesson_id == lesson.id,
        )
    )
    valid = await occurrences_v1.list_occurrences(db_session, seed.organization.id)
    assert valid["total"] == 0, "A normal completed lesson is not an occurrence."
    log.logged_at = lesson.starts_at - timedelta(days=1)
    for _ in range(2):
        previous = await db_session.get(SchedulerVersionV1, lesson.version_id)
        previous.status = "SUPERSEDED"
        await db_session.flush()
        version = await add_version(db_session, seed)
        moved_lesson = await add_lesson(
            db_session,
            seed,
            version,
            stable_key=lesson.stable_key,
            school_date=lesson.school_date,
            start=lesson.starts_at,
            end=lesson.ends_at,
            credit_minutes=lesson.credit_minutes,
        )
        moved_lesson.source_lesson_id = lesson.id
        log.lesson_id = moved_lesson.id
        lesson = moved_lesson
    await db_session.commit()
    page = await occurrences_v1.list_occurrences(db_session, seed.organization.id)
    assert page["total"] == 1
    item = page["items"][0]
    assert item["status"] == "GIVEN"
    assert item["decided_at"] is None
    if already_revoked:
        await reverse_lesson_execution(
            db_session,
            seed.organization.id,
            await lesson_context(db_session, seed.organization.id, log.lesson_id),
            membership_id=seed.membership.id,
            now_utc=lesson.ends_at,
        )
        log.status = "REVOKED"
        log.revoked_at = lesson.ends_at
        log.revoked_by_membership_id = seed.membership.id
        log.revoked_reason = "Reversão histórica QA com saldo residual"
        await db_session.commit()
    unrelated_debt_id = None
    if broken_lineage:
        lesson.source_lesson_id = None
        unrelated_version = await add_version(db_session, seed, status="SUPERSEDED")
        unrelated = await add_lesson(
            db_session,
            seed,
            unrelated_version,
            stable_key=lesson.stable_key,
            school_date=lesson.school_date + timedelta(days=7),
            start=lesson.starts_at + timedelta(days=7),
            end=lesson.ends_at + timedelta(days=7),
            credit_minutes=lesson.credit_minutes,
        )
        unrelated_debt_id = await record_debt(
            db_session,
            seed.organization.id,
            seed.year.id,
            seed.assignment.id,
            DebtOrigin(
                origin=f"lesson-occurrence:{unrelated.id}",
                revision=1,
                origin_date=unrelated.school_date,
                minutes=50,
                author_id=seed.membership.id,
                reason="Separate physical lesson",
                recorded_at=MOMENT,
            ),
        )
        await db_session.commit()
    for _ in range(2):
        await occurrences_v1.cancel_occurrence(
            db_session,
            seed.organization.id,
            log.id,
            version=item["version"],
            reason="Reversão de crédito QA antecipado",
            cancelled_by_membership_id=seed.membership.id,
            now_utc=MOMENT,
        )
        await db_session.commit()
    executed = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(executed.get(seed.assignment.id, {}).values()) == 0
    assert log.status == "REVOKED"
    assert log.decision is None, "Reversal must not fabricate a historical decision."
    if already_revoked:
        assert log.revoked_reason == "Reversão histórica QA com saldo residual"
    debt, _ = await load_open_debt(db_session, seed.organization.id, [seed.assignment.id])
    expected_debt = {unrelated_debt_id: 50} if broken_lineage else {}
    assert debt == expected_debt, "Cancel only the original physical lesson's reopened debt."
    assert (await occurrences_v1.get_debts(db_session, seed.organization.id))["total_gaps"] == int(
        broken_lineage
    )


async def _school(db_session, *, suffix: str = "", minutes: int = 100) -> V1Seed:
    return await seed_generatable_school(
        db_session,
        clerk_user_id=f"w09_occ_a{suffix}",
        clerk_org_id=f"w09_occ_org{suffix}",
        module_minutes=minutes,
    )


async def test_dashboard_identifies_conflicting_published_lessons(db_session):
    seed = await _school(db_session, suffix="_conflicts")
    version = await add_version(db_session, seed)
    seed.organization.first_real_schedule_approved_at = MOMENT
    lessons = [
        await add_lesson(
            db_session,
            seed,
            version,
            stable_key=f"conflict-{index}",
            school_date=MOMENT.date(),
            start=MOMENT,
            end=MOMENT + timedelta(minutes=50),
        )
        for index in range(2)
    ]
    await db_session.commit()
    dashboard = await get_dashboard_summary(db_session, seed.organization.id)
    health = dashboard.schedule_health
    assert health.duplicate_teacher_slots == 1
    assert health.duplicate_class_slots == 1
    assert {row.lesson_id for row in health.conflicting_lessons} == {row.id for row in lessons}
    for row in health.conflicting_lessons:
        assert row.class_name == seed.class_.name
        assert row.teacher_id == seed.assignment.teacher_id
        assert row.subject_name == seed.subject.name
        assert row.school_date == MOMENT.date()

    lessons[1].starts_at = lessons[0].ends_at
    lessons[1].ends_at = lessons[1].starts_at + timedelta(minutes=50)
    await db_session.commit()
    health = (await get_dashboard_summary(db_session, seed.organization.id)).schedule_health
    assert health.duplicate_teacher_slots == health.duplicate_class_slots == 0
    assert health.conflicting_lessons == []


async def _lessons(db_session, seed: V1Seed) -> list[SchedulerLessonV1]:
    return list(
        (
            await db_session.scalars(
                select(SchedulerLessonV1)
                .where(SchedulerLessonV1.organization_id == seed.organization.id)
                .order_by(SchedulerLessonV1.school_date, SchedulerLessonV1.id)
            )
        ).all()
    )


async def _second_assignment(db_session, seed: V1Seed):
    subject = models.Subject(
        name="Matemática",
        organization_id=seed.organization.id,
        room_type_id=seed.subject.room_type_id,
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


async def _occurrence(db_session, seed: V1Seed, lesson: SchedulerLessonV1) -> None:
    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson.id,
        status="OCCURRENCE",
        summary="Falta registada.",
        notes=None,
        now_utc=MOMENT,
        planning_relevant=True,
    )
    await db_session.commit()


async def _decide(db_session, seed: V1Seed, item, status, *, now, **extra):
    decided = await occurrences_v1.update_occurrence(
        db_session,
        seed.organization.id,
        item["id"],
        schemas.LessonOccurrenceUpdate(status=status, version=item["version"], **extra),
        decided_by_membership_id=seed.membership.id,
        now_utc=now,
    )
    await db_session.commit()
    return decided


async def test_future_gap_history_does_not_overlap_repaired_lessons(db_session, monkeypatch):
    seed = await _school(db_session, suffix="_future_history")
    await db_session.commit()
    await seed_published_baseline(db_session, seed)
    missed = (await _lessons(db_session, seed))[0]
    previous_by_key = {row.stable_key: row.id for row in await _lessons(db_session, seed)}
    now = missed.starts_at - timedelta(days=1)
    await _occurrence(db_session, seed, missed)
    item = (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]
    await _decide(db_session, seed, item, models.LessonOccurrenceStatus.GAP, now=now)

    for cycle in range(2):
        await run_generation(db_session, monkeypatch, seed, key=f"future-history:{cycle}", now=now)
        published = await db_session.scalars(
            select(SchedulerLessonV1)
            .where(
                SchedulerLessonV1.organization_id == seed.organization.id,
                SchedulerLessonV1.version_id == int(seed.state.active_schedule_version_id),
            )
            .order_by(SchedulerLessonV1.starts_at)
        )
        rows = list(published)
        assert len(rows) == 3 - cycle, "Preserve gap history until its audited reversal."
        assert any(row.stable_key == missed.stable_key for row in rows)
        assert all(left.ends_at <= right.starts_at for left, right in pairwise(rows))
        for row in rows:
            if row.stable_key in previous_by_key:
                assert row.source_lesson_id == previous_by_key[row.stable_key]
        previous_by_key = {row.stable_key: row.id for row in rows}
        if cycle == 0:
            current = (await occurrences_v1.list_occurrences(db_session, seed.organization.id))[
                "items"
            ][0]
            await occurrences_v1.cancel_occurrence(
                db_session,
                seed.organization.id,
                current["id"],
                version=current["version"],
                reason="Reversão QA da ocorrência futura",
                cancelled_by_membership_id=seed.membership.id,
                now_utc=now,
            )
            await db_session.commit()
            assert (await occurrences_v1.get_debts(db_session, seed.organization.id))[
                "total_gaps"
            ] == 0


@pytest.mark.parametrize("stability_days", [0, 2])
async def test_a_missed_past_lesson_leaves_its_minutes_to_recover(
    db_session, monkeypatch, stability_days
):
    from app.scheduler.domain.candidate import SchedulingStrategy
    from app.scheduler.domain.recovery import assess_baseline

    seed = await _school(db_session, suffix="_repair_snapshot")
    db_session.add(
        models.OrganizationSettings(
            organization_id=seed.organization.id, repair_stability_window_days=stability_days
        )
    )
    await db_session.commit()
    await seed_published_baseline(db_session, seed)
    lessons = await _lessons(db_session, seed)
    missed = lessons[0]
    now = missed.ends_at + timedelta(minutes=1)
    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=missed.id,
        status="OCCURRENCE",
        summary="Aula não realizada.",
        notes=None,
        now_utc=now,
        planning_relevant=True,
    )
    await db_session.commit()

    pending_debt, _ = await load_open_debt(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(pending_debt.values()) == 0, "Uma ocorrência pendente não cria dívida."

    item = (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]
    decided = await _decide(db_session, seed, item, models.LessonOccurrenceStatus.GAP, now=now)
    assert decided["operational_state"] == "DECIDED_GAP"

    bundle = await load_snapshot(
        db_session,
        seed.organization.id,
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        now_utc=now,
        school_year_id=seed.year.id,
    )

    assert sum(bundle.snapshot.open_debt_minutes.values()) == missed.credit_minutes
    assert all(row.lesson_id != int(missed.stable_key) for row in bundle.snapshot.protected_lessons)
    assert bundle.baseline is not None
    assessment = assess_baseline(bundle.snapshot, bundle.baseline.lessons)
    assert assessment.missing_minutes == missed.credit_minutes

    frozen = {
        row.lesson_id: (row.period.start_utc, row.period.end_utc, row.room_id)
        for row in bundle.snapshot.protected_lessons
    }
    await run_generation(
        db_session, monkeypatch, seed, key=f"repair:{seed.organization.id}", now=now
    )
    version_id = int(seed.state.active_schedule_version_id)
    published = (
        await db_session.scalars(
            select(SchedulerLessonV1).where(
                SchedulerLessonV1.organization_id == seed.organization.id,
                SchedulerLessonV1.version_id == version_id,
            )
        )
    ).all()
    history = next(row for row in published if row.stable_key == missed.stable_key)
    assert (history.starts_at, history.ends_at, history.room_id) == (
        missed.starts_at,
        missed.ends_at,
        missed.room_id,
    )
    log = await db_session.scalar(
        select(SchedulerLessonLogV1).where(SchedulerLessonLogV1.lesson_id == history.id)
    )
    assert log.status == "OCCURRENCE"
    assert log.decision == "GAP"
    assert sum(row.credit_minutes for row in published if row.id != history.id) == 100
    for identity, physical in frozen.items():
        row = next(row for row in published if row.stable_key == str(identity))
        assert (row.starts_at, row.ends_at, row.room_id) == physical
    reservations = (
        await db_session.scalars(
            select(SchedulerRecoveryReservationV1).where(
                SchedulerRecoveryReservationV1.organization_id == seed.organization.id,
                SchedulerRecoveryReservationV1.version_id == version_id,
            )
        )
    ).all()
    assert sum(row.minutes for row in reservations) == missed.credit_minutes
    recovery = next(row for row in published if row.id == reservations[0].lesson_id)
    assert recovery.starts_at > now
    assert recovery.school_date not in bundle.snapshot.protected_dates
    debt, _ = await load_open_debt(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(debt.values()) == missed.credit_minutes
    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=recovery.id,
        status="COMPLETED",
        summary="Reposição realizada.",
        notes=None,
        now_utc=recovery.ends_at,
        planning_relevant=True,
    )
    debt, _ = await load_open_debt(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(debt.values()) == 0


async def test_execution_after_a_missed_lesson_keeps_history_out_of_frozen_credit(
    db_session, monkeypatch
):
    from app.scheduler.domain.candidate import SchedulingStrategy
    from app.scheduler.domain.recovery import assess_baseline

    seed = await _school(db_session, suffix="_later_execution", minutes=150)
    db_session.add(
        models.OrganizationSettings(
            organization_id=seed.organization.id, repair_stability_window_days=2
        )
    )
    await db_session.commit()
    await seed_published_baseline(db_session, seed)
    missed, completed, frozen = await _lessons(db_session, seed)
    now = completed.ends_at + timedelta(minutes=1)
    for row, status in ((missed, "OCCURRENCE"), (completed, "COMPLETED")):
        await record_lesson_log(
            db_session,
            seed.organization.id,
            membership_id=seed.membership.id,
            lesson_id=row.id,
            status=status,
            summary="Registo da aula.",
            notes=None,
            now_utc=now,
            planning_relevant=True,
        )
    await db_session.commit()
    item = (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]
    await _decide(db_session, seed, item, models.LessonOccurrenceStatus.GAP, now=now)
    bundle = await load_snapshot(
        db_session,
        seed.organization.id,
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        now_utc=now,
        school_year_id=seed.year.id,
    )

    assert [row.lesson_id for row in bundle.snapshot.protected_lessons] == [int(frozen.stable_key)]
    assert sum(bundle.snapshot.executed_minutes[seed.assignment.id].values()) == 50
    assert bundle.snapshot.protected_lessons[0].slices[0].offset_minutes == 50
    assert assess_baseline(bundle.snapshot, bundle.baseline.lessons).missing_minutes == 50


async def test_a_v1_occurrence_is_listed_and_decided_as_given(db_session, monkeypatch):
    seed = await _school(db_session)
    await db_session.commit()
    await seed_published_baseline(db_session, seed)
    lessons = await _lessons(db_session, seed)
    await _occurrence(db_session, seed, lessons[0])

    page = await occurrences_v1.list_occurrences(db_session, seed.organization.id)
    assert page["total"] == 1
    item = page["items"][0]
    assert item["operational_state"] == "OPEN_PENDING"
    assert item["class_id"] == seed.class_.id
    assert item["subject_id"] == seed.subject.id
    pending_debt, _ = await load_open_debt(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(pending_debt.values()) == 0

    decided = await _decide(
        db_session,
        seed,
        item,
        models.LessonOccurrenceStatus.GIVEN,
        now=lessons[0].ends_at,
    )
    assert decided["status"] == "GIVEN"
    assert decided["operational_state"] == "DECIDED_GIVEN"

    pending = await occurrences_v1.list_occurrences(
        db_session, seed.organization.id, status_filter="OPEN_PENDING"
    )
    assert pending["total"] == 0
    debts = await occurrences_v1.get_debts(db_session, seed.organization.id)
    assert debts["total_gaps"] == 0
    open_debt, _ = await load_open_debt(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(open_debt.values()) == 0
    executed = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(executed[seed.assignment.id].values()) == lessons[0].credit_minutes


async def test_a_substitution_credits_the_substitute_subject_and_keeps_the_debt(
    db_session, monkeypatch
):
    from app.core.exceptions import AppError
    from app.scheduler.infrastructure import operations

    seed = await _school(db_session, suffix="_sub")
    await db_session.commit()
    await seed_published_baseline(db_session, seed)
    lessons = await _lessons(db_session, seed)
    subject, _module, teacher, assignment = await _second_assignment(db_session, seed)
    await _occurrence(db_session, seed, lessons[0])

    recommendations = await occurrences_v1.get_substitute_recommendations(
        db_session,
        seed.organization.id,
        (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]["id"],
    )
    assert recommendations, "O substituto elegível deve ser recomendado."
    assert {row["teacher_id"] for row in recommendations} == {teacher.id}
    assert {row["subject_id"] for row in recommendations} == {subject.id}

    page = await occurrences_v1.list_occurrences(db_session, seed.organization.id)
    item = page["items"][0]
    decided = await _decide(
        db_session,
        seed,
        item,
        models.LessonOccurrenceStatus.SUBSTITUTED,
        now=MOMENT,
        substitute_teacher_id=teacher.id,
        substitute_subject_id=subject.id,
    )
    assert decided["status"] == "SUBSTITUTED"
    assert decided["operational_state"] == "DECIDED_SUBSTITUTED"
    assert decided["substitute_teacher_id"] == teacher.id
    assert decided["substitute_execution_status"] == "PENDING_LOG"
    assert decided["hours_given"] == 0.0, "Planear não credita execução."

    executed = await load_executed_minutes(db_session, seed.organization.id, [assignment.id])
    assert sum(executed.get(assignment.id, {}).values()) == 0
    open_debt, _ = await load_open_debt(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(open_debt.values()) == lessons[0].credit_minutes

    debts = await occurrences_v1.get_debts(db_session, seed.organization.id)
    assert debts["total_gaps"] == 1
    assert debts["items"][0]["subject_id"] == seed.subject.id
    assert debts["items"][0]["hours_owed"] == lessons[0].credit_minutes / 60

    week_start = lessons[0].school_date - timedelta(days=lessons[0].school_date.weekday())
    slots = await week_schedule(
        db_session,
        seed.organization.id,
        week_start=week_start,
        class_id=seed.class_.id,
        teacher_id=None,
        now_utc=MOMENT,
    )
    assert all(slot["scheduler_lesson_id"] != lessons[0].id for slot in slots)
    substitute_slot = next(
        slot for slot in slots if slot["operational_block_id"] == decided["substitute_block_id"]
    )
    assert substitute_slot["block_source"] == "operational"
    assert substitute_slot["is_substituted_block"] is True
    assert substitute_slot["teacher"]["id"] == teacher.id
    assert substitute_slot["subject"]["id"] == subject.id
    assert substitute_slot["can_complete"] is False
    assert substitute_slot["blocked_reason"] == "lesson_not_finished"
    substitute_week = await week_schedule(
        db_session,
        seed.organization.id,
        week_start=week_start,
        class_id=None,
        teacher_id=teacher.id,
        now_utc=MOMENT,
    )
    assert any(
        slot["operational_block_id"] == decided["substitute_block_id"] for slot in substitute_week
    )
    original_week = await week_schedule(
        db_session,
        seed.organization.id,
        week_start=week_start,
        class_id=None,
        teacher_id=seed.assignment.teacher_id,
        now_utc=MOMENT,
    )
    assert all(slot["scheduler_lesson_id"] != lessons[0].id for slot in original_week)

    await operations.record_operational_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        operational_block_id=decided["substitute_block_id"],
        payload=schemas.LessonLogCreate(
            status=models.LessonLogStatus.COMPLETED, summary="Matemática dada.", notes=None
        ),
        now_utc=lessons[0].ends_at,
    )
    await db_session.commit()

    completed = await occurrences_v1.get_occurrence(db_session, seed.organization.id, item["id"])
    assert completed["substitute_execution_status"] == "COMPLETED"
    assert completed["hours_given"] == lessons[0].credit_minutes / 60
    executed = await load_executed_minutes(db_session, seed.organization.id, [assignment.id])
    assert sum(executed[assignment.id].values()) == lessons[0].credit_minutes
    open_debt, _ = await load_open_debt(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(open_debt.values()) == lessons[0].credit_minutes

    with pytest.raises(AppError) as locked:
        await occurrences_v1.cancel_occurrence(
            db_session,
            seed.organization.id,
            item["id"],
            version=completed["version"],
            reason="Reversão administrativa",
            cancelled_by_membership_id=seed.membership.id,
            now_utc=MOMENT,
        )
    assert locked.value.detail == "SUBSTITUTE_LOG_LOCKED"

    cancelled = await occurrences_v1.cancel_occurrence(
        db_session,
        seed.organization.id,
        item["id"],
        version=completed["version"],
        reason="Reversão administrativa",
        cancelled_by_membership_id=seed.membership.id,
        cancel_completed_substitute_log=True,
        now_utc=MOMENT,
    )
    await db_session.commit()
    assert cancelled["cancelled"] is True
    executed = await load_executed_minutes(db_session, seed.organization.id, [assignment.id])
    assert sum(executed[assignment.id].values()) == 0
    open_debt, _ = await load_open_debt(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(open_debt.values()) == 0
    final_page = await occurrences_v1.list_occurrences(db_session, seed.organization.id)
    assert final_page["items"][0]["status"] == "REVOKED"
    assert final_page["items"][0]["is_active"] is False
    debts = await occurrences_v1.get_debts(db_session, seed.organization.id)
    assert debts["total_gaps"] == 0


async def test_open_debts_aggregate_occurrence_claims(db_session, monkeypatch):
    seed = await _school(db_session, suffix="_debts")
    await db_session.commit()
    await seed_published_baseline(db_session, seed)
    lessons = await _lessons(db_session, seed)
    await _occurrence(db_session, seed, lessons[0])
    await _occurrence(db_session, seed, lessons[1])

    page = await occurrences_v1.list_occurrences(db_session, seed.organization.id)
    for item in page["items"]:
        await _decide(
            db_session, seed, item, models.LessonOccurrenceStatus.GAP, now=item["ends_at"]
        )

    class ReferenceDate(date):
        @classmethod
        def today(cls):
            return max(row.school_date for row in lessons)

    monkeypatch.setattr(occurrences_v1, "date", ReferenceDate)

    debts = await occurrences_v1.get_debts(db_session, seed.organization.id)
    assert debts["total_gaps"] == 2
    assert len(debts["items"]) == 1
    assert debts["items"][0]["gap_occurrences"] == 2
    assert debts["items"][0]["hours_owed"] == 2 * lessons[0].credit_minutes / 60
    overdue = await occurrences_v1.get_debts(db_session, seed.organization.id)
    assert overdue["total_gaps_overdue"] == 2


async def test_teacher_progress_reads_v1_execution_and_open_debt(db_session, monkeypatch):
    seed = await _school(db_session, suffix="_teacher_progress")
    await db_session.commit()
    await seed_published_baseline(db_session, seed)
    lessons = await _lessons(db_session, seed)
    missed, completed = lessons[:2]
    await _occurrence(db_session, seed, missed)
    pending = (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]
    before = await get_teacher_progress(
        db_session, seed.assignment.teacher_id, seed.organization.id
    )
    assert before[0]["subjects"][0]["modules"][0]["hours_debt"] == 0
    await _decide(db_session, seed, pending, models.LessonOccurrenceStatus.GAP, now=missed.ends_at)
    gap = await get_teacher_progress(db_session, seed.assignment.teacher_id, seed.organization.id)
    assert gap[0]["subjects"][0]["modules"][0]["hours_debt"] == round(missed.credit_minutes / 60, 1)
    assert gap[0]["subjects"][0]["completed_hours"] == 0
    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=completed.id,
        status="COMPLETED",
        summary="Aula concluída.",
        notes=None,
        now_utc=completed.ends_at + timedelta(minutes=1),
        planning_relevant=True,
    )
    await db_session.commit()
    result = await get_teacher_progress(
        db_session, seed.assignment.teacher_id, seed.organization.id
    )
    module = result[0]["subjects"][0]["modules"][0]
    assert module["hours_completed"] == round(completed.credit_minutes / 60, 1)
    # Completing the remaining minutes also settles the open claim in this assignment.
    assert module["hours_debt"] == 0
    assert (await occurrences_v1.get_debts(db_session, seed.organization.id))[
        "total_hours_owed"
    ] == 0
    assert result[0]["subjects"][0]["completed_hours"] == round(completed.credit_minutes / 60, 1)
    assert (
        await get_teacher_progress(
            db_session, seed.assignment.teacher_id, seed.organization.id + 100000
        )
        == []
    )


async def test_v1_stale_decision_has_no_effects_and_matching_retry_is_idempotent(
    db_session, monkeypatch
):
    seed = await _school(db_session, suffix="_stale_decision")
    await db_session.commit()
    await seed_published_baseline(db_session, seed)
    lesson = (await _lessons(db_session, seed))[0]
    subject, _module, teacher, _assignment = await _second_assignment(db_session, seed)
    await _occurrence(db_session, seed, lesson)
    pending = (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]
    gap = await _decide(db_session, seed, pending, models.LessonOccurrenceStatus.GAP, now=MOMENT)
    debt = await occurrences_v1.get_debts(db_session, seed.organization.id)
    assert debt["total_hours_owed"] == lesson.credit_minutes / 60
    with pytest.raises(AppError) as conflict:
        await occurrences_v1.update_occurrence(
            db_session,
            seed.organization.id,
            pending["id"],
            schemas.LessonOccurrenceUpdate(
                status=models.LessonOccurrenceStatus.SUBSTITUTED,
                version=pending["version"],
                substitute_teacher_id=teacher.id,
                substitute_subject_id=subject.id,
            ),
            decided_by_membership_id=seed.membership.id,
            now_utc=MOMENT,
        )
    assert conflict.value.kind == "conflict"
    assert conflict.value.detail == "OCCURRENCE_STALE_VERSION"
    assert (
        await occurrences_v1.get_occurrence(db_session, seed.organization.id, gap["id"], MOMENT)
        == gap
    )
    assert await occurrences_v1.get_debts(db_session, seed.organization.id) == debt
    blocks = list(
        await db_session.scalars(
            select(models.OperationalScheduleBlock).where(
                models.OperationalScheduleBlock.organization_id == seed.organization.id,
            )
        )
    )
    assert blocks == []
    repeated = await _decide(
        db_session, seed, pending, models.LessonOccurrenceStatus.GAP, now=MOMENT
    )
    assert repeated == gap
    assert await occurrences_v1.get_debts(db_session, seed.organization.id) == debt


async def test_recommendations_exclude_the_planned_teacher_and_subject(db_session, monkeypatch):
    seed = await _school(db_session, suffix="_recs")
    await db_session.commit()
    await seed_published_baseline(db_session, seed)
    lessons = await _lessons(db_session, seed)
    await _second_assignment(db_session, seed)
    await _occurrence(db_session, seed, lessons[0])

    page = await occurrences_v1.list_occurrences(db_session, seed.organization.id)
    recommendations = await occurrences_v1.get_substitute_recommendations(
        db_session, seed.organization.id, page["items"][0]["id"]
    )
    assert recommendations
    for row in recommendations:
        assert row["teacher_id"] != seed.assignment.teacher_id
        assert row["subject_id"] != seed.subject.id


async def test_given_before_the_lesson_end_is_rejected_without_persisted_effects(
    db_session, monkeypatch
):
    from app.core.exceptions import AppError

    seed = await _school(db_session, suffix="_guard")
    await db_session.commit()
    await seed_published_baseline(db_session, seed)
    lessons = await _lessons(db_session, seed)
    await _occurrence(db_session, seed, lessons[0])
    item = (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]

    with pytest.raises(AppError) as excinfo:
        await occurrences_v1.update_occurrence(
            db_session,
            seed.organization.id,
            item["id"],
            schemas.LessonOccurrenceUpdate(
                status=models.LessonOccurrenceStatus.GIVEN, version=item["version"]
            ),
            decided_by_membership_id=seed.membership.id,
            now_utc=lessons[0].ends_at - timedelta(seconds=1),
        )
    assert excinfo.value.kind == "validation"
    assert excinfo.value.code == "lesson_not_finished"

    log = await db_session.scalar(
        select(SchedulerLessonLogV1).where(SchedulerLessonLogV1.id == item["id"])
    )
    assert log.status == "OCCURRENCE"
    assert log.decision is None
    executed = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(executed.get(seed.assignment.id, {}).values()) == 0

    decided = await _decide(
        db_session, seed, item, models.LessonOccurrenceStatus.GIVEN, now=lessons[0].ends_at
    )
    assert decided["operational_state"] == "DECIDED_GIVEN"

    repeated = await occurrences_v1.update_occurrence(
        db_session,
        seed.organization.id,
        item["id"],
        schemas.LessonOccurrenceUpdate(
            status=models.LessonOccurrenceStatus.GIVEN, version=item["version"]
        ),
        decided_by_membership_id=seed.membership.id,
        now_utc=lessons[0].ends_at,
    )
    assert repeated["operational_state"] == "DECIDED_GIVEN"
    executed = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(executed[seed.assignment.id].values()) == lessons[0].credit_minutes


async def test_a_closed_week_blocks_occurrence_changes_and_reopening_allows_them(
    db_session, monkeypatch
):
    from app.core.exceptions import AppError
    from app.scheduler.infrastructure import operations

    seed = await _school(db_session, suffix="_closed")
    await db_session.commit()
    await seed_published_baseline(db_session, seed)
    lesson = (await _lessons(db_session, seed))[0]
    await _occurrence(db_session, seed, lesson)
    item = (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]

    week_start = lesson.school_date - timedelta(days=lesson.school_date.weekday())
    timesheet = models.TeacherWeeklyTimesheet(
        organization_id=seed.organization.id,
        teacher_id=seed.assignment.teacher_id,
        week_start_date=week_start,
        status=models.TimesheetStatus.SUBMITTED,
    )
    db_session.add(timesheet)
    await db_session.commit()

    with pytest.raises(AppError) as locked:
        await _decide_locked(
            db_session, seed, item, models.LessonOccurrenceStatus.GAP, now=lesson.ends_at
        )
    assert locked.value.code == "week_locked"

    with pytest.raises(operations.OperationsError) as summary_locked:
        await operations.record_lesson_log(
            db_session,
            seed.organization.id,
            membership_id=seed.membership.id,
            lesson_id=lesson.id,
            status="COMPLETED",
            summary="Fora de prazo.",
            notes=None,
            now_utc=lesson.ends_at,
        )
    assert summary_locked.value.code == "week_locked"

    log = await db_session.scalar(
        select(SchedulerLessonLogV1).where(SchedulerLessonLogV1.id == item["id"])
    )
    assert log.decision is None
    debt, _ = await load_open_debt(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(debt.values()) == 0

    timesheet.status = models.TimesheetStatus.OPEN
    await db_session.commit()
    decided = await _decide(
        db_session, seed, item, models.LessonOccurrenceStatus.GAP, now=lesson.ends_at
    )
    assert decided["operational_state"] == "DECIDED_GAP"


async def _decide_locked(db_session, seed, item, status, *, now):
    """Call the decision without the committing helper, to keep the rollback."""
    return await occurrences_v1.update_occurrence(
        db_session,
        seed.organization.id,
        item["id"],
        schemas.LessonOccurrenceUpdate(status=status, version=item["version"]),
        decided_by_membership_id=seed.membership.id,
        now_utc=now,
    )


async def test_the_given_gap_cycle_compensates_and_recreates_the_debt(db_session, monkeypatch):
    seed = await _school(db_session, suffix="_cycle")
    await db_session.commit()
    await seed_published_baseline(db_session, seed)
    lesson = (await _lessons(db_session, seed))[0]
    await _occurrence(db_session, seed, lesson)
    item = (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]

    given = await _decide(
        db_session, seed, item, models.LessonOccurrenceStatus.GIVEN, now=lesson.ends_at
    )
    executed = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(executed[seed.assignment.id].values()) == lesson.credit_minutes
    debt, _ = await load_open_debt(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(debt.values()) == 0

    gap = await _decide(
        db_session, seed, given, models.LessonOccurrenceStatus.GAP, now=lesson.ends_at
    )
    assert gap["operational_state"] == "DECIDED_GAP"
    executed = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(executed.get(seed.assignment.id, {}).values()) == 0
    debt, _ = await load_open_debt(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(debt.values()) == lesson.credit_minutes
    debts = await occurrences_v1.get_debts(db_session, seed.organization.id)
    assert debts["total_gaps"] == 1
    assert debts["total_hours_owed"] == lesson.credit_minutes / 60
    dashboard = await get_dashboard_summary(db_session, seed.organization.id)
    assert dashboard.debts.total_gaps == debts["total_gaps"]
    assert dashboard.debts.total_hours_owed == debts["total_hours_owed"]
    log = await db_session.scalar(
        select(SchedulerLessonLogV1).where(SchedulerLessonLogV1.id == item["id"])
    )
    assert log.status == "OCCURRENCE"

    given_again = await _decide(
        db_session, seed, gap, models.LessonOccurrenceStatus.GIVEN, now=lesson.ends_at
    )
    debt, _ = await load_open_debt(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(debt.values()) == 0
    executed = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(executed[seed.assignment.id].values()) == lesson.credit_minutes

    gap_again = await _decide(
        db_session, seed, given_again, models.LessonOccurrenceStatus.GAP, now=lesson.ends_at
    )
    debt, _ = await load_open_debt(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(debt.values()) == lesson.credit_minutes
    debts = await occurrences_v1.get_debts(db_session, seed.organization.id)
    assert debts["total_gaps"] == 1, "Prior decision cycles must not multiply the open claim."
    assert debts["total_hours_owed"] == lesson.credit_minutes / 60
    executed = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(executed.get(seed.assignment.id, {}).values()) == 0

    await occurrences_v1.cancel_occurrence(
        db_session,
        seed.organization.id,
        item["id"],
        version=gap_again["version"],
        reason="Reversão final",
        cancelled_by_membership_id=seed.membership.id,
        now_utc=lesson.ends_at,
    )
    await db_session.commit()
    debt, _ = await load_open_debt(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(debt.values()) == 0
    executed = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(executed.get(seed.assignment.id, {}).values()) == 0


async def test_the_normal_summary_log_cannot_change_a_decided_occurrence(db_session, monkeypatch):
    from app.scheduler.infrastructure import operations

    seed = await _school(db_session, suffix="_summary")
    await db_session.commit()
    await seed_published_baseline(db_session, seed)
    lesson = (await _lessons(db_session, seed))[0]
    await _occurrence(db_session, seed, lesson)
    item = (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]
    await _decide(db_session, seed, item, models.LessonOccurrenceStatus.GAP, now=lesson.ends_at)

    with pytest.raises(operations.OperationsError) as blocked:
        await operations.record_lesson_log(
            db_session,
            seed.organization.id,
            membership_id=seed.membership.id,
            lesson_id=lesson.id,
            status="COMPLETED",
            summary="Tentativa pela API direta.",
            notes=None,
            now_utc=lesson.ends_at,
        )
    assert blocked.value.code == "occurrence_active"

    edited = await operations.record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson.id,
        status="OCCURRENCE",
        summary="Texto atualizado.",
        notes=None,
        now_utc=lesson.ends_at,
    )
    await db_session.commit()
    assert edited["status"] == "OCCURRENCE"
    after = await occurrences_v1.get_occurrence(db_session, seed.organization.id, item["id"])
    assert after["operational_state"] == "DECIDED_GAP"
    assert after["lesson_log_summary"] == "Texto atualizado."
    debt, _ = await load_open_debt(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(debt.values()) == lesson.credit_minutes


async def test_a_revoked_occurrence_can_start_a_new_cycle(db_session, monkeypatch):
    seed = await _school(db_session, suffix="_reopen")
    await db_session.commit()
    await seed_published_baseline(db_session, seed)
    lesson = (await _lessons(db_session, seed))[0]
    await _occurrence(db_session, seed, lesson)
    item = (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]
    decided = await _decide(
        db_session, seed, item, models.LessonOccurrenceStatus.GAP, now=lesson.ends_at
    )
    await occurrences_v1.cancel_occurrence(
        db_session,
        seed.organization.id,
        item["id"],
        version=decided["version"],
        reason="Reversão para novo ciclo",
        cancelled_by_membership_id=seed.membership.id,
        now_utc=lesson.ends_at,
    )
    await db_session.commit()

    week_start = lesson.school_date - timedelta(days=lesson.school_date.weekday())
    slots = await week_schedule(
        db_session,
        seed.organization.id,
        week_start=week_start,
        class_id=seed.class_.id,
        teacher_id=None,
        now_utc=lesson.ends_at,
    )
    validated = [schemas.WeekSlotRead.model_validate(slot) for slot in slots]
    reverted = next(slot for slot in validated if slot.scheduler_lesson_id == lesson.id)
    assert reverted.occurrence_status == "REVOKED"
    assert reverted.lesson_log_status == models.LessonLogStatus.PENDING
    assert reverted.can_create_occurrence is True

    result = await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson.id,
        status="OCCURRENCE",
        summary="Nova ocorrência.",
        notes=None,
        now_utc=lesson.ends_at,
        planning_relevant=True,
    )
    await db_session.commit()
    assert result["status"] == "OCCURRENCE"

    log = await db_session.scalar(
        select(SchedulerLessonLogV1).where(SchedulerLessonLogV1.id == item["id"])
    )
    assert log.status == "OCCURRENCE"
    assert log.decision is None
    assert log.revoked_reason == "Reversão para novo ciclo"
    page = await occurrences_v1.list_occurrences(
        db_session, seed.organization.id, status_filter="OPEN_PENDING"
    )
    assert page["total"] == 1
    debt, _ = await load_open_debt(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(debt.values()) == 0


async def test_substitution_diagnostics_explain_the_excluded_candidate(db_session, monkeypatch):
    seed = await _school(db_session, suffix="_diag")
    await db_session.commit()
    await seed_published_baseline(db_session, seed)
    lesson = (await _lessons(db_session, seed))[0]
    _subject, _module, teacher, _assignment = await _second_assignment(db_session, seed)
    await _occurrence(db_session, seed, lesson)
    item = (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]

    diagnostics = await occurrences_v1.get_substitute_diagnostics(
        db_session, seed.organization.id, item["id"]
    )
    assert any(candidate["eligible"] for candidate in diagnostics["candidates"])

    db_session.add(
        models.Availability(
            organization_id=seed.organization.id,
            teacher_id=teacher.id,
            timeslot_id=item["timeslot_id"],
            score=-1,
        )
    )
    await db_session.commit()

    diagnostics = await occurrences_v1.get_substitute_diagnostics(
        db_session, seed.organization.id, item["id"]
    )
    candidate = next(row for row in diagnostics["candidates"] if row["teacher_id"] == teacher.id)
    assert candidate["eligible"] is False
    assert {exclusion["code"] for exclusion in candidate["exclusions"]} == {"unavailable"}
    assert diagnostics["setup_actions"] == ["availability"]
    assert diagnostics["eligible_count"] == 0


async def test_substitution_room_compatibility_uses_school_type_ids(db_session):
    seed = await _school(db_session, suffix="_room_type_ids")
    await db_session.commit()
    await seed_published_baseline(db_session, seed)
    lesson = (await _lessons(db_session, seed))[0]
    subject, _module, teacher, _assignment = await _second_assignment(db_session, seed)

    room_type_a = models.SchoolRoomType(
        organization_id=seed.organization.id,
        name="Laboratório de Química",
        is_normal=False,
    )
    room_type_b = models.SchoolRoomType(
        organization_id=seed.organization.id,
        name="Laboratório de Informática",
        is_normal=False,
    )
    db_session.add_all((room_type_a, room_type_b))
    await db_session.flush()
    seed.room.type = models.RoomType.lab
    seed.room.room_type_id = room_type_a.id
    subject.required_room_type = models.RoomType.lab
    subject.room_type_id = room_type_b.id
    await db_session.commit()

    await _occurrence(db_session, seed, lesson)
    item = (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]
    diagnostics = await occurrences_v1.get_substitute_diagnostics(
        db_session, seed.organization.id, item["id"]
    )

    candidate = next(row for row in diagnostics["candidates"] if row["teacher_id"] == teacher.id)
    assert candidate["eligible"] is False
    assert {exclusion["code"] for exclusion in candidate["exclusions"]} == {"room_mismatch"}


async def test_a_planned_substitution_reserves_resources_and_demand(db_session, monkeypatch):
    from app.scheduler.domain.candidate import SchedulingStrategy, UnavailableResource
    from app.scheduler.infrastructure import operations

    seed = await _school(db_session, suffix="_reserve")
    await db_session.commit()
    await seed_published_baseline(db_session, seed)
    lesson = (await _lessons(db_session, seed))[0]
    subject, module, teacher, assignment = await _second_assignment(db_session, seed)
    await _occurrence(db_session, seed, lesson)
    item = (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]

    before = await load_snapshot(
        db_session,
        seed.organization.id,
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        now_utc=MOMENT,
        school_year_id=seed.year.id,
    )

    decided = await _decide(
        db_session,
        seed,
        item,
        models.LessonOccurrenceStatus.SUBSTITUTED,
        now=MOMENT,
        substitute_teacher_id=teacher.id,
        substitute_subject_id=subject.id,
    )

    bundle = await load_snapshot(
        db_session,
        seed.organization.id,
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        now_utc=MOMENT,
        school_year_id=seed.year.id,
    )
    snapshot = bundle.snapshot
    assert bundle.digest != before.digest
    assert snapshot.executed_minutes[assignment.id][module.id] == lesson.credit_minutes
    for resource_type, resource_id in (
        (UnavailableResource.TEACHER, teacher.id),
        (UnavailableResource.ROOM, lesson.room_id),
        (UnavailableResource.CLASS, seed.class_.id),
    ):
        entries = snapshot.hard_unavailable_on(resource_type, resource_id, lesson.school_date)
        assert any(
            entry.period.start_utc <= lesson.starts_at and entry.period.end_utc >= lesson.ends_at
            for entry in entries
        )

    await operations.record_operational_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        operational_block_id=decided["substitute_block_id"],
        payload=schemas.LessonLogCreate(
            status=models.LessonLogStatus.COMPLETED, summary="Substituição dada.", notes=None
        ),
        now_utc=lesson.ends_at,
    )
    await db_session.commit()

    after = await load_snapshot(
        db_session,
        seed.organization.id,
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        now_utc=MOMENT,
        school_year_id=seed.year.id,
    )
    # The completed block arrives through the ledger exactly once.
    assert sum(after.snapshot.executed_minutes[assignment.id].values()) == lesson.credit_minutes


@pytest.mark.parametrize(
    "timezone,moment,school_date,overdue",
    [
        ("Europe/Lisbon", datetime(2026, 9, 22, 23, 30, tzinfo=UTC), date(2026, 9, 23), 1),
        ("Atlantic/Azores", datetime(2026, 9, 23, 0, 30, tzinfo=UTC), date(2026, 9, 23), 1),
        ("America/New_York", datetime(2026, 9, 23, 0, 30, tzinfo=UTC), date(2026, 9, 22), 0),
    ],
)
async def test_debts_use_school_date_at_midnight(
    db_session, monkeypatch, timezone, moment, school_date, overdue
):
    seed = await _school(db_session, suffix="_debt_timezone")
    seed.year.timezone = timezone
    await add_version(db_session, seed)
    await record_debt(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        DebtOrigin(
            origin="lesson-occurrence:midnight",
            revision=1,
            origin_date=date(2026, 9, 23),
            minutes=50,
            author_id=seed.membership.id,
            reason="Dívida de teste",
            recorded_at=moment,
        ),
    )
    await db_session.commit()

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return moment.astimezone(tz) if tz is not None else moment.replace(tzinfo=None)

    class ServerDate(date):
        @classmethod
        def today(cls):
            return moment.date()

    monkeypatch.setattr(occurrences_v1, "datetime", FrozenDatetime)
    monkeypatch.setattr(occurrences_v1, "date", ServerDate)

    debts = await occurrences_v1.get_debts(db_session, seed.organization.id)

    assert debts["as_of_date"] == school_date
    assert debts["total_gaps"] == 1
    assert debts["total_hours_owed"] == 50 / 60
    assert debts["total_gaps_overdue"] == overdue
    assert debts["total_hours_owed_overdue"] == overdue * 50 / 60
    assert debts["items"][0]["gap_occurrences_overdue"] == overdue
    assert debts["items"][0]["hours_owed_overdue"] == overdue * 50 / 60
