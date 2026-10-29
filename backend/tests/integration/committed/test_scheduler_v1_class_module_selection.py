"""WBS 2.5-2.6: the engine reads the per-class module selection.

Covers the projection (selected modules, stable sequence, retired modules),
the shared planning loader, the lesson-log credit redirect, the year-reset
settlement and the adaptive recovery of history in a retired module.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import delete, func, select

from app import models, schemas
from app.scheduler.domain.debt import DebtOrigin
from app.scheduler.domain.demand import ExecutionEntry, ModuleCredit
from app.scheduler.domain.projection import ModuleRequirement
from app.scheduler.infrastructure.curriculum import sync_curricular_projection
from app.scheduler.infrastructure.jobs import enqueue_generation
from app.scheduler.infrastructure.models import (
    CurricularRequirement,
    SchedulerLessonSliceV1,
    SchedulerLessonV1,
)
from app.scheduler.infrastructure.operations import (
    OperationsError,
    adjust_class_progress,
    record_lesson_log,
)
from app.scheduler.infrastructure.progress import (
    load_executed_minutes,
    load_planning_requirements,
    reconcile_assignment_requirements,
    record_debt,
    record_execution,
    revise_debt,
    settle_open_debt,
)
from app.scheduler.infrastructure.snapshot import SnapshotConfigurationError
from tests._support.scheduler_v1 import (
    add_lesson,
    add_version,
    lesson_interval,
    run_generation,
    seed_generatable_school,
    seed_published_baseline,
    set_stability_window,
)

pytestmark = pytest.mark.postgresql

MOMENT = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)


async def _add_module(db_session, seed, *, name: str, minutes: int, order: int):
    module = models.Module(
        organization_id=seed.organization.id,
        subject_id=seed.subject.id,
        name=name,
        required_minutes=minutes,
        order=order,
    )
    db_session.add(module)
    await db_session.flush()
    db_session.add(
        CurricularRequirement(
            organization_id=seed.organization.id,
            assignment_id=seed.assignment.id,
            module_id=module.id,
            sequence=order + 1,
            required_minutes=minutes,
        )
    )
    await db_session.flush()
    return module


async def _add_catalogue_module(db_session, seed, *, name: str, minutes: int, order: int):
    """Add a catalogue module without a projection requirement row."""
    module = models.Module(
        organization_id=seed.organization.id,
        subject_id=seed.subject.id,
        name=name,
        required_minutes=minutes,
        order=order,
    )
    db_session.add(module)
    await db_session.flush()
    return module


async def _requirement_row(db_session, seed, module_id: int):
    return await db_session.scalar(
        select(CurricularRequirement).where(
            CurricularRequirement.organization_id == seed.organization.id,
            CurricularRequirement.assignment_id == seed.assignment.id,
            CurricularRequirement.module_id == module_id,
        )
    )


async def _link(db_session, seed) -> models.ClassSubjectLink:
    return await db_session.scalar(
        select(models.ClassSubjectLink).where(
            models.ClassSubjectLink.organization_id == seed.organization.id,
            models.ClassSubjectLink.class_id == seed.class_.id,
            models.ClassSubjectLink.subject_id == seed.subject.id,
        )
    )


async def _select(db_session, seed, module_ids) -> None:
    link = await _link(db_session, seed)
    await db_session.execute(
        delete(models.class_subject_module).where(
            models.class_subject_module.c.organization_id == seed.organization.id,
            models.class_subject_module.c.class_subject_link_id == link.id,
        )
    )
    for module_id in module_ids:
        await db_session.execute(
            models.class_subject_module.insert().values(
                organization_id=seed.organization.id,
                class_subject_link_id=link.id,
                module_id=module_id,
            )
        )
    await db_session.flush()


async def _requirements(db_session, organization_id):
    return {
        module_id: (sequence, planned, required)
        for module_id, sequence, planned, required in (
            await db_session.execute(
                select(
                    CurricularRequirement.module_id,
                    CurricularRequirement.sequence,
                    CurricularRequirement.planned,
                    CurricularRequirement.required_minutes,
                )
                .where(CurricularRequirement.organization_id == organization_id)
                .order_by(CurricularRequirement.sequence)
            )
        ).all()
    }


async def _add_slice(db_session, seed, lesson, module_id: int, offset: int, minutes: int) -> None:
    db_session.add(
        SchedulerLessonSliceV1(
            organization_id=seed.organization.id,
            school_year_id=seed.year.id,
            lesson_id=lesson.id,
            module_id=module_id,
            offset_minutes=offset,
            minutes=minutes,
        )
    )
    await db_session.flush()


async def test_projection_projects_only_selected_modules_with_stable_sequence(db_session):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="cms_proj",
        clerk_org_id="cms_proj_org",
        module_minutes=60,
    )
    module_b = await _add_module(db_session, seed, name="B", minutes=80, order=2)
    await _select(db_session, seed, [seed.module.id, module_b.id])
    await db_session.commit()

    await sync_curricular_projection(db_session, seed.organization.id, seed.year)
    await db_session.commit()

    assert await _requirements(db_session, seed.organization.id) == {
        seed.module.id: (seed.module.order + 1, True, 60),
        module_b.id: (module_b.order + 1, True, 80),
    }


async def test_retired_module_keeps_history_and_reselects(db_session):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="cms_retire",
        clerk_org_id="cms_retire_org",
        module_minutes=60,
    )
    module_b = await _add_module(db_session, seed, name="B", minutes=60, order=2)
    module_c = await _add_module(db_session, seed, name="C", minutes=60, order=3)
    await _select(db_session, seed, [seed.module.id, module_b.id, module_c.id])
    await db_session.commit()

    await record_execution(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        ExecutionEntry(
            "lesson:b",
            1,
            seed.membership.id,
            "B taught",
            (ModuleCredit(module_b.id, 25),),
            recorded_at=MOMENT,
        ),
        planning_relevant=True,
    )
    await db_session.commit()

    await _select(db_session, seed, [seed.module.id])
    await db_session.commit()
    await sync_curricular_projection(db_session, seed.organization.id, seed.year)
    await db_session.commit()

    stored = await _requirements(db_session, seed.organization.id)
    assert stored[seed.module.id] == (seed.module.order + 1, True, 60)
    assert stored[module_b.id] == (module_b.order + 1, False, 60)
    assert module_c.id not in stored

    await _select(db_session, seed, [seed.module.id, module_b.id])
    await db_session.commit()
    await sync_curricular_projection(db_session, seed.organization.id, seed.year)
    await db_session.commit()

    assert (await _requirements(db_session, seed.organization.id))[module_b.id] == (
        module_b.order + 1,
        True,
        60,
    )


async def test_link_without_selected_modules_raises_configuration_error(db_session):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="cms_empty",
        clerk_org_id="cms_empty_org",
        module_minutes=60,
    )
    await _select(db_session, seed, [])
    await db_session.commit()

    with pytest.raises(SnapshotConfigurationError) as error:
        await sync_curricular_projection(db_session, seed.organization.id, seed.year)

    assert error.value.code == "CLASS_SUBJECT_WITHOUT_MODULES"


async def test_planning_loader_closes_a_retired_module_at_its_credit(db_session):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="cms_plan",
        clerk_org_id="cms_plan_org",
        module_minutes=60,
    )
    module_b = await _add_module(db_session, seed, name="B", minutes=60, order=2)
    await _select(db_session, seed, [seed.module.id, module_b.id])
    await db_session.commit()
    await record_execution(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        ExecutionEntry(
            "lesson:a",
            1,
            seed.membership.id,
            "A taught",
            (ModuleCredit(seed.module.id, 20),),
            recorded_at=MOMENT,
        ),
        planning_relevant=True,
    )
    await db_session.commit()

    await _select(db_session, seed, [module_b.id])
    await db_session.commit()
    await sync_curricular_projection(db_session, seed.organization.id, seed.year)
    await db_session.commit()

    planning, executed = await load_planning_requirements(
        db_session, seed.organization.id, [seed.assignment.id]
    )
    assert planning[seed.assignment.id] == (
        ModuleRequirement(seed.module.id, seed.module.order + 1, 20),
        ModuleRequirement(module_b.id, module_b.order + 1, 60),
    )
    assert executed[seed.assignment.id] == {seed.module.id: 20, module_b.id: 0}


async def test_a_log_after_retiring_a_module_credits_the_next_selected_module(db_session):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="cms_ops",
        clerk_org_id="cms_ops_org",
        module_minutes=100,
    )
    module_b = await _add_module(db_session, seed, name="B", minutes=100, order=2)
    await _select(db_session, seed, [seed.module.id, module_b.id])
    await db_session.commit()
    version = await add_version(db_session, seed, status="ACTIVE")

    first_start, first_end = lesson_interval(date(2026, 9, 7), 9)
    second_start, second_end = lesson_interval(date(2026, 9, 8), 9)
    first = await add_lesson(
        db_session,
        seed,
        version,
        stable_key="lesson:1",
        school_date=date(2026, 9, 7),
        start=first_start,
        end=first_end,
    )
    second = await add_lesson(
        db_session,
        seed,
        version,
        stable_key="lesson:2",
        school_date=date(2026, 9, 8),
        start=second_start,
        end=second_end,
    )
    await _add_slice(db_session, seed, first, seed.module.id, 0, 50)
    await _add_slice(db_session, seed, second, seed.module.id, 50, 50)
    await db_session.commit()

    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=first.id,
        status="COMPLETED",
        summary="Primeira aula.",
        notes=None,
        now_utc=first.ends_at,
        planning_relevant=True,
    )
    await db_session.commit()

    # Real selection change, with no projection sync before the next log.
    await _select(db_session, seed, [module_b.id])
    await db_session.commit()

    result = await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=second.id,
        status="COMPLETED",
        summary="Segunda aula.",
        notes=None,
        now_utc=second.ends_at,
        planning_relevant=True,
    )
    await db_session.commit()

    assert result["credited_minutes"] == 50
    executed = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert executed[seed.assignment.id] == {seed.module.id: 50, module_b.id: 50}


async def test_occurrence_requirements_ignore_a_retired_module(db_session):
    from app.scheduler.infrastructure import occurrences as occurrences_v1

    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="cms_occ",
        clerk_org_id="cms_occ_org",
        module_minutes=60,
    )
    module_b = await _add_module(db_session, seed, name="B", minutes=60, order=2)
    await _select(db_session, seed, [seed.module.id, module_b.id])
    await db_session.commit()

    await _select(db_session, seed, [module_b.id])
    await db_session.commit()

    modules = await occurrences_v1._requirements(
        db_session, seed.organization.id, seed.assignment.id
    )
    assert [module.module_id for module in modules] == [module_b.id]


async def test_year_reset_settlement_does_not_credit_a_retired_module(db_session):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="cms_reset",
        clerk_org_id="cms_reset_org",
        module_minutes=60,
    )
    module_b = await _add_module(db_session, seed, name="B", minutes=60, order=2)
    await _select(db_session, seed, [seed.module.id, module_b.id])
    await db_session.commit()
    await record_execution(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        ExecutionEntry(
            "lesson:a",
            1,
            seed.membership.id,
            "A taught",
            (ModuleCredit(seed.module.id, 20),),
            recorded_at=MOMENT,
        ),
        planning_relevant=True,
    )
    await db_session.commit()

    # Retire A by selection alone; the projection has not run yet.
    await _select(db_session, seed, [module_b.id])
    await db_session.commit()
    await record_debt(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        DebtOrigin(
            "occurrence:1",
            1,
            date(2026, 9, 22),
            30,
            seed.membership.id,
            "Missed lesson",
            recorded_at=MOMENT,
        ),
    )
    await db_session.commit()

    settled = await settle_open_debt(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        membership_id=seed.membership.id,
        reason="Reinício do ano",
        now_utc=MOMENT,
    )

    assert settled == 30
    executed = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert executed[seed.assignment.id] == {seed.module.id: 20, module_b.id: 30}


async def test_a_log_beyond_the_selected_curriculum_raises(db_session):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="cms_cap",
        clerk_org_id="cms_cap_org",
        module_minutes=50,
    )
    module_b = await _add_module(db_session, seed, name="B", minutes=50, order=2)
    await _select(db_session, seed, [seed.module.id, module_b.id])
    await db_session.commit()
    version = await add_version(db_session, seed, status="ACTIVE")

    first_start, first_end = lesson_interval(date(2026, 9, 7), 9)
    second_start, second_end = lesson_interval(date(2026, 9, 8), 9)
    first = await add_lesson(
        db_session,
        seed,
        version,
        stable_key="lesson:1",
        school_date=date(2026, 9, 7),
        start=first_start,
        end=first_end,
    )
    second = await add_lesson(
        db_session,
        seed,
        version,
        stable_key="lesson:2",
        school_date=date(2026, 9, 8),
        start=second_start,
        end=second_end,
    )
    await _add_slice(db_session, seed, first, seed.module.id, 0, 50)
    await _add_slice(db_session, seed, second, seed.module.id, 50, 50)
    await db_session.commit()

    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=first.id,
        status="COMPLETED",
        summary="Primeira aula.",
        notes=None,
        now_utc=first.ends_at,
        planning_relevant=True,
    )
    await db_session.commit()

    await _select(db_session, seed, [])
    await db_session.commit()

    with pytest.raises(OperationsError) as error:
        await record_lesson_log(
            db_session,
            seed.organization.id,
            membership_id=seed.membership.id,
            lesson_id=second.id,
            status="COMPLETED",
            summary="Sem capacidade.",
            notes=None,
            now_utc=second.ends_at,
            planning_relevant=True,
        )
    assert error.value.code == "lesson_without_slices"


async def test_a_new_selected_module_receives_the_redirected_credit(db_session):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="cms_newmod",
        clerk_org_id="cms_newmod_org",
        module_minutes=50,
    )
    module_b = await _add_catalogue_module(db_session, seed, name="B", minutes=50, order=2)
    version = await add_version(db_session, seed, status="ACTIVE")
    start, end = lesson_interval(date(2026, 9, 7), 9)
    lesson = await add_lesson(
        db_session,
        seed,
        version,
        stable_key="lesson:1",
        school_date=date(2026, 9, 7),
        start=start,
        end=end,
    )
    await _add_slice(db_session, seed, lesson, seed.module.id, 0, 50)
    await db_session.commit()

    # Retire A and select the new B, which has no projection row yet.
    await _select(db_session, seed, [module_b.id])
    await db_session.commit()

    result = await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson.id,
        status="COMPLETED",
        summary="Aula redirecionada.",
        notes=None,
        now_utc=lesson.ends_at,
        planning_relevant=True,
    )
    await db_session.commit()

    assert result["credited_minutes"] == 50
    executed = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert executed[seed.assignment.id] == {module_b.id: 50}
    row = await _requirement_row(db_session, seed, module_b.id)
    assert row is not None
    assert (row.planned, row.required_minutes, row.sequence) == (True, 50, module_b.order + 1)


async def test_reselecting_a_deleted_uncredited_module_logs_successfully(db_session):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="cms_deleted",
        clerk_org_id="cms_deleted_org",
        module_minutes=50,
    )
    module_b = await _add_module(db_session, seed, name="B", minutes=50, order=2)
    await _select(db_session, seed, [seed.module.id, module_b.id])
    await db_session.commit()
    await _select(db_session, seed, [seed.module.id])
    await db_session.commit()
    await sync_curricular_projection(db_session, seed.organization.id, seed.year)
    await db_session.commit()
    assert await _requirement_row(db_session, seed, module_b.id) is None

    await _select(db_session, seed, [seed.module.id, module_b.id])
    await db_session.commit()

    version = await add_version(db_session, seed, status="ACTIVE")
    start, end = lesson_interval(date(2026, 9, 7), 9)
    lesson = await add_lesson(
        db_session,
        seed,
        version,
        stable_key="lesson:1",
        school_date=date(2026, 9, 7),
        start=start,
        end=end,
    )
    await _add_slice(db_session, seed, lesson, module_b.id, 0, 50)
    await db_session.commit()

    result = await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson.id,
        status="COMPLETED",
        summary="Aula de B.",
        notes=None,
        now_utc=lesson.ends_at,
        planning_relevant=True,
    )
    await db_session.commit()

    assert result["credited_minutes"] == 50
    executed = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert executed[seed.assignment.id] == {seed.module.id: 0, module_b.id: 50}
    row = await _requirement_row(db_session, seed, module_b.id)
    assert row is not None and row.planned


async def test_manual_progress_accepts_a_selected_unprojected_module(db_session):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="cms_manual_new",
        clerk_org_id="cms_manual_new_org",
        module_minutes=50,
    )
    module_b = await _add_catalogue_module(db_session, seed, name="B", minutes=50, order=2)
    await _select(db_session, seed, [seed.module.id, module_b.id])
    await db_session.commit()

    handled = await adjust_class_progress(
        db_session,
        seed.organization.id,
        seed.class_.id,
        [schemas.ClassProgressUpdate(module_id=module_b.id, hours_completed=0.5)],
        membership_id=seed.membership.id,
        now_utc=MOMENT,
    )
    await db_session.commit()

    assert handled is True
    executed = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert executed[seed.assignment.id][module_b.id] == 30
    row = await _requirement_row(db_session, seed, module_b.id)
    assert row is not None and row.planned


async def test_year_reset_settlement_reaches_a_reselected_module(db_session):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="cms_reset_new",
        clerk_org_id="cms_reset_new_org",
        module_minutes=50,
    )
    module_b = await _add_module(db_session, seed, name="B", minutes=50, order=2)
    await _select(db_session, seed, [seed.module.id, module_b.id])
    await db_session.commit()
    await record_execution(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        ExecutionEntry(
            "lesson:a",
            1,
            seed.membership.id,
            "A taught",
            (ModuleCredit(seed.module.id, 50),),
            recorded_at=MOMENT,
        ),
        planning_relevant=True,
    )
    await db_session.commit()
    await record_debt(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        DebtOrigin(
            "occurrence:1",
            1,
            date(2026, 9, 22),
            20,
            seed.membership.id,
            "Missed lesson",
            recorded_at=MOMENT,
        ),
    )
    await db_session.commit()

    await _select(db_session, seed, [seed.module.id])
    await db_session.commit()
    await sync_curricular_projection(db_session, seed.organization.id, seed.year)
    await db_session.commit()
    assert await _requirement_row(db_session, seed, module_b.id) is None
    await _select(db_session, seed, [seed.module.id, module_b.id])
    await db_session.commit()

    settled = await settle_open_debt(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        membership_id=seed.membership.id,
        reason="Reinício do ano",
        now_utc=MOMENT,
    )

    assert settled == 20
    executed = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert executed[seed.assignment.id] == {seed.module.id: 50, module_b.id: 20}


async def test_reconcile_sees_a_pending_requirement_row(db_session):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="cms_pending",
        clerk_org_id="cms_pending_org",
        module_minutes=50,
    )
    module_b = await _add_catalogue_module(db_session, seed, name="B", minutes=50, order=2)
    await _select(db_session, seed, [seed.module.id, module_b.id])
    await db_session.commit()

    # A requirement row the session has not flushed yet (autoflush is off).
    db_session.add(
        CurricularRequirement(
            organization_id=seed.organization.id,
            assignment_id=seed.assignment.id,
            module_id=module_b.id,
            sequence=module_b.order + 1,
            required_minutes=50,
        )
    )

    await reconcile_assignment_requirements(db_session, seed.organization.id, seed.assignment.id)
    await db_session.commit()

    rows = (
        await db_session.scalars(
            select(CurricularRequirement).where(
                CurricularRequirement.organization_id == seed.organization.id,
                CurricularRequirement.assignment_id == seed.assignment.id,
                CurricularRequirement.module_id == module_b.id,
            )
        )
    ).all()
    assert len(rows) == 1


async def test_debt_on_a_selected_unprojected_module_is_accepted(db_session):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="cms_debt_new",
        clerk_org_id="cms_debt_new_org",
        module_minutes=50,
    )
    module_b = await _add_catalogue_module(db_session, seed, name="B", minutes=50, order=2)
    await _select(db_session, seed, [seed.module.id, module_b.id])
    await db_session.commit()

    debt_id = await record_debt(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        DebtOrigin(
            "occurrence:1",
            1,
            date(2026, 9, 22),
            80,
            seed.membership.id,
            "Missed lesson",
            recorded_at=MOMENT,
        ),
    )
    await db_session.commit()

    assert debt_id > 0
    row = await _requirement_row(db_session, seed, module_b.id)
    assert row is not None and row.planned


async def test_revise_debt_on_a_selected_unprojected_module_is_accepted(db_session):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="cms_revise_new",
        clerk_org_id="cms_revise_new_org",
        module_minutes=50,
    )
    module_b = await _add_catalogue_module(db_session, seed, name="B", minutes=50, order=2)
    await _select(db_session, seed, [seed.module.id, module_b.id])
    await db_session.commit()
    debt_id = await record_debt(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        DebtOrigin(
            "occurrence:1",
            1,
            date(2026, 9, 22),
            40,
            seed.membership.id,
            "Missed lesson",
            recorded_at=MOMENT,
        ),
    )
    await db_session.commit()

    revision_id = await revise_debt(
        db_session,
        seed.organization.id,
        seed.year.id,
        debt_id,
        origin="manual:1",
        revision=1,
        delta_minutes=20,
        author_id=seed.membership.id,
        reason="Add missed minutes",
        recorded_at=MOMENT,
    )
    await db_session.commit()

    assert revision_id > 0


async def test_repeated_and_reversed_redirected_credit_stays_stable(db_session):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="cms_repeat",
        clerk_org_id="cms_repeat_org",
        module_minutes=50,
    )
    module_b = await _add_catalogue_module(db_session, seed, name="B", minutes=50, order=2)
    version = await add_version(db_session, seed, status="ACTIVE")
    start, end = lesson_interval(date(2026, 9, 7), 9)
    lesson = await add_lesson(
        db_session,
        seed,
        version,
        stable_key="lesson:1",
        school_date=date(2026, 9, 7),
        start=start,
        end=end,
    )
    await _add_slice(db_session, seed, lesson, seed.module.id, 0, 50)
    await db_session.commit()

    await _select(db_session, seed, [module_b.id])
    await db_session.commit()

    async def log(status: str) -> dict:
        outcome = await record_lesson_log(
            db_session,
            seed.organization.id,
            membership_id=seed.membership.id,
            lesson_id=lesson.id,
            status=status,
            summary="Aula.",
            notes=None,
            now_utc=lesson.ends_at,
            planning_relevant=status == "OCCURRENCE",
        )
        await db_session.commit()
        return outcome

    first = await log("COMPLETED")
    repeat = await log("COMPLETED")
    await log("OCCURRENCE")
    again = await log("COMPLETED")

    assert first["credited_minutes"] == 50
    assert repeat["credited_minutes"] == 0
    assert again["credited_minutes"] == 50
    executed = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert executed[seed.assignment.id] == {module_b.id: 50}


async def test_stale_reselection_overrides_the_projection_flag(db_session):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="cms_stale",
        clerk_org_id="cms_stale_org",
        module_minutes=60,
    )
    module_b = await _add_module(db_session, seed, name="B", minutes=60, order=2)
    await _select(db_session, seed, [seed.module.id, module_b.id])
    await db_session.commit()

    requirement = await db_session.scalar(
        select(CurricularRequirement).where(
            CurricularRequirement.organization_id == seed.organization.id,
            CurricularRequirement.assignment_id == seed.assignment.id,
            CurricularRequirement.module_id == seed.module.id,
        )
    )
    requirement.planned = False  # stale flag from an older projection
    await db_session.commit()

    planning, _ = await load_planning_requirements(
        db_session, seed.organization.id, [seed.assignment.id]
    )
    assert planning[seed.assignment.id] == (
        ModuleRequirement(seed.module.id, seed.module.order + 1, 60),
        ModuleRequirement(module_b.id, module_b.order + 1, 60),
    )


async def test_retire_credit_next_reselect_generates_and_approves(db_session, monkeypatch):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="cms_resel",
        clerk_org_id="cms_resel_org",
        module_minutes=100,
    )
    module_b = await _add_module(db_session, seed, name="B", minutes=100, order=2)
    await _select(db_session, seed, [seed.module.id, module_b.id])
    await db_session.commit()
    await seed_published_baseline(db_session, seed)
    previous_version_id = int(seed.state.active_schedule_version_id)

    a_lessons = await _lessons_with_module(db_session, seed, previous_version_id, seed.module.id)
    assert len(a_lessons) >= 2
    first, second = a_lessons[0], a_lessons[1]

    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=first.id,
        status="COMPLETED",
        summary="Aula de A.",
        notes=None,
        now_utc=first.ends_at,
        planning_relevant=True,
    )
    await db_session.commit()

    await _select(db_session, seed, [module_b.id])
    await db_session.commit()

    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=second.id,
        status="COMPLETED",
        summary="Aula depois de retirar A.",
        notes=None,
        now_utc=second.ends_at,
        planning_relevant=True,
    )
    await db_session.commit()

    ledger = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert ledger[seed.assignment.id] == {seed.module.id: 50, module_b.id: 50}

    await _select(db_session, seed, [seed.module.id, module_b.id])
    await db_session.commit()
    await run_generation(db_session, monkeypatch, seed, key="cms-reselect")
    await db_session.refresh(seed.state)
    new_version_id = int(seed.state.active_schedule_version_id)
    assert new_version_id != previous_version_id

    after = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert after[seed.assignment.id] == {seed.module.id: 50, module_b.id: 50}
    retained = await _lessons_with_module(db_session, seed, new_version_id, seed.module.id)
    assert {first.stable_key, second.stable_key} <= {row.stable_key for row in retained}


async def test_generation_omits_a_retired_module_and_keeps_the_ledger(db_session, monkeypatch):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="cms_gen",
        clerk_org_id="cms_gen_org",
        module_minutes=100,
    )
    module_b = await _add_module(db_session, seed, name="B", minutes=100, order=2)
    await _select(db_session, seed, [seed.module.id, module_b.id])
    await db_session.commit()
    await seed_published_baseline(db_session, seed)
    previous_version_id = int(seed.state.active_schedule_version_id)

    lesson = await _first_lesson_with_module(db_session, seed, previous_version_id, seed.module.id)
    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson.id,
        status="COMPLETED",
        summary="Aula do módulo retirado.",
        notes=None,
        now_utc=lesson.ends_at,
        planning_relevant=True,
    )
    await db_session.commit()

    await _select(db_session, seed, [module_b.id])
    await db_session.commit()
    await run_generation(db_session, monkeypatch, seed, key="cms-retire")
    await db_session.refresh(seed.state)
    new_version_id = int(seed.state.active_schedule_version_id)
    assert new_version_id != previous_version_id

    by_module = {
        module_id: int(minutes)
        for module_id, minutes in (
            await db_session.execute(
                select(
                    SchedulerLessonSliceV1.module_id,
                    func.sum(SchedulerLessonSliceV1.minutes),
                )
                .join(
                    SchedulerLessonV1,
                    SchedulerLessonV1.id == SchedulerLessonSliceV1.lesson_id,
                )
                .where(SchedulerLessonV1.version_id == new_version_id)
                .group_by(SchedulerLessonSliceV1.module_id)
            )
        ).all()
    }
    assert by_module.get(seed.module.id, 0) == 50  # only the copied history
    assert by_module.get(module_b.id, 0) == 100

    executed = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert executed[seed.assignment.id][seed.module.id] == 50


async def _publish_then_retire_a_after_gap(db_session, seed):
    """Publish a baseline, log A's second lesson as a GAP, then retire module A.

    Returns module B, the GAP lesson and the id of the published baseline version.
    """
    from app.scheduler.infrastructure import occurrences as occurrences_v1

    module_b = await _add_module(db_session, seed, name="B", minutes=100, order=2)
    await _select(db_session, seed, [seed.module.id, module_b.id])
    await db_session.commit()
    await seed_published_baseline(db_session, seed)
    previous_version_id = int(seed.state.active_schedule_version_id)

    a_lessons = await _lessons_with_module(db_session, seed, previous_version_id, seed.module.id)
    assert len(a_lessons) >= 2
    taught, absence = a_lessons[0], a_lessons[1]

    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=taught.id,
        status="COMPLETED",
        summary="Aula dada de A.",
        notes=None,
        now_utc=taught.ends_at,
        planning_relevant=True,
    )
    await db_session.commit()

    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=absence.id,
        status="OCCURRENCE",
        summary="Falta registada.",
        notes=None,
        now_utc=absence.ends_at,
        planning_relevant=True,
    )
    await db_session.commit()

    item = (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]
    await occurrences_v1.update_occurrence(
        db_session,
        seed.organization.id,
        item["id"],
        schemas.LessonOccurrenceUpdate(
            status=models.LessonOccurrenceStatus.GAP, version=item["version"]
        ),
        decided_by_membership_id=seed.membership.id,
        now_utc=absence.ends_at,
    )
    await db_session.commit()

    await _select(db_session, seed, [module_b.id])
    await db_session.commit()
    return module_b, absence, previous_version_id


async def test_logged_absence_in_a_retired_module_is_refused_inside_the_default_window(
    db_session,
):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="cms_abs_window",
        clerk_org_id="cms_abs_window_org",
        module_minutes=100,
    )
    await _publish_then_retire_a_after_gap(db_session, seed)

    with pytest.raises(SnapshotConfigurationError) as error:
        await enqueue_generation(
            db_session,
            seed.organization.id,
            idempotency_key="cms-abs-window",
            requested_by_membership_id=seed.membership.id,
            now_utc=MOMENT,
        )

    assert error.value.code == "DEBT_EXCEEDS_RECOVERY_CAPACITY"


async def test_logged_absence_in_a_retired_module_generates_and_approves(db_session, monkeypatch):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="cms_abs",
        clerk_org_id="cms_abs_org",
        module_minutes=100,
    )
    # This scenario tests the retired-module history, not the stability window.
    await set_stability_window(db_session, seed, 0)
    module_b, absence, previous_version_id = await _publish_then_retire_a_after_gap(
        db_session, seed
    )

    await run_generation(db_session, monkeypatch, seed, key="cms-absence")
    await db_session.refresh(seed.state)
    new_version_id = int(seed.state.active_schedule_version_id)
    assert new_version_id != previous_version_id

    retained = await _lessons_with_module(db_session, seed, new_version_id, seed.module.id)
    absence_copy = next(row for row in retained if row.stable_key == absence.stable_key)
    slices = (
        await db_session.scalars(
            select(SchedulerLessonSliceV1)
            .where(SchedulerLessonSliceV1.lesson_id == absence_copy.id)
            .order_by(SchedulerLessonSliceV1.offset_minutes)
        )
    ).all()
    assert [(row.module_id, row.offset_minutes, row.minutes) for row in slices] == [
        (seed.module.id, 50, 50)
    ]

    ledger = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert ledger[seed.assignment.id] == {seed.module.id: 50, module_b.id: 0}


async def test_future_protected_excess_is_released_on_a_curriculum_change(db_session, monkeypatch):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="cms_protected",
        clerk_org_id="cms_protected_org",
        module_minutes=100,
    )
    module_b = await _add_module(db_session, seed, name="B", minutes=100, order=2)
    await _select(db_session, seed, [seed.module.id, module_b.id])
    await db_session.commit()
    await seed_published_baseline(db_session, seed)
    previous_version_id = int(seed.state.active_schedule_version_id)
    db_session.add(
        models.OrganizationSettings(
            organization_id=seed.organization.id,
            repair_stability_window_days=60,
        )
    )
    await db_session.commit()

    first = await _first_lesson_with_module(db_session, seed, previous_version_id, seed.module.id)
    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=first.id,
        status="COMPLETED",
        summary="Aula de A.",
        notes=None,
        now_utc=first.ends_at,
        planning_relevant=True,
    )
    await db_session.commit()

    await _select(db_session, seed, [module_b.id])
    await db_session.commit()
    await run_generation(db_session, monkeypatch, seed, key="cms-protected")
    await db_session.refresh(seed.state)
    new_version_id = int(seed.state.active_schedule_version_id)
    assert new_version_id != previous_version_id

    by_module = {
        module_id: int(minutes)
        for module_id, minutes in (
            await db_session.execute(
                select(
                    SchedulerLessonSliceV1.module_id,
                    func.sum(SchedulerLessonSliceV1.minutes),
                )
                .join(
                    SchedulerLessonV1,
                    SchedulerLessonV1.id == SchedulerLessonSliceV1.lesson_id,
                )
                .where(SchedulerLessonV1.version_id == new_version_id)
                .group_by(SchedulerLessonSliceV1.module_id)
            )
        ).all()
    }
    assert by_module.get(seed.module.id, 0) == 50  # only the registered history
    assert by_module.get(module_b.id, 0) == 100

    ledger = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert ledger[seed.assignment.id][seed.module.id] == 50
    retained = await _lessons_with_module(db_session, seed, new_version_id, seed.module.id)
    assert first.stable_key in {row.stable_key for row in retained}


async def test_past_lessons_are_never_deleted(db_session, monkeypatch):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="cms_past",
        clerk_org_id="cms_past_org",
        module_minutes=100,
    )
    module_b = await _add_module(db_session, seed, name="B", minutes=100, order=2)
    await _select(db_session, seed, [seed.module.id, module_b.id])
    await db_session.commit()
    await seed_published_baseline(db_session, seed)
    db_session.add(
        models.OrganizationSettings(
            organization_id=seed.organization.id,
            repair_stability_window_days=60,
        )
    )
    await db_session.commit()

    await _select(db_session, seed, [module_b.id])
    await db_session.commit()

    # Moving "today" past three unlogged lessons makes them impossible to drop.
    later = datetime(2026, 9, 15, 8, 0, tzinfo=UTC)
    with pytest.raises(SnapshotConfigurationError) as error:
        await run_generation(db_session, monkeypatch, seed, key="cms-past", now=later)

    assert error.value.code == "PROTECTED_LESSON_EXCEEDS_CURRICULUM"


async def _lessons_with_module(
    db_session, seed, version_id: int, module_id: int
) -> list[SchedulerLessonV1]:
    lessons = (
        await db_session.scalars(
            select(SchedulerLessonV1)
            .where(
                SchedulerLessonV1.organization_id == seed.organization.id,
                SchedulerLessonV1.version_id == version_id,
            )
            .order_by(SchedulerLessonV1.starts_at, SchedulerLessonV1.id)
        )
    ).all()
    slices = (
        await db_session.scalars(
            select(SchedulerLessonSliceV1).where(
                SchedulerLessonSliceV1.lesson_id.in_([row.id for row in lessons])
            )
        )
    ).all()
    owners: dict[int, set[int]] = {}
    for row in slices:
        owners.setdefault(row.lesson_id, set()).add(row.module_id)
    return [lesson for lesson in lessons if module_id in owners.get(lesson.id, set())]


async def _first_lesson_with_module(
    db_session, seed, version_id: int, module_id: int
) -> SchedulerLessonV1:
    matches = await _lessons_with_module(db_session, seed, version_id, module_id)
    if not matches:
        raise AssertionError("No lesson references the requested module.")
    return matches[0]
