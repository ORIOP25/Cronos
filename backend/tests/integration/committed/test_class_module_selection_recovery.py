"""WBS 2.6.7: history stays valid when a module with logged lessons retires.

A logged absence (falta) on a lesson of a retired module must not break the
adaptive recovery. The logged lesson keeps its physical position and its
history is copied into the approved proposal, even though the module is closed
and receives no planned credit.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from app import models
from app.scheduler.infrastructure.models import (
    CurricularRequirement,
    SchedulerLessonLogV1,
    SchedulerLessonSliceV1,
    SchedulerLessonV1,
)
from app.scheduler.infrastructure.operations import record_lesson_log
from tests._support.scheduler_v1 import (
    run_generation,
    seed_generatable_school,
    seed_published_baseline,
    set_stability_window,
)

pytestmark = pytest.mark.postgresql


async def _link_id(db_session, seed) -> int:
    return await db_session.scalar(
        select(models.ClassSubjectLink.id).where(
            models.ClassSubjectLink.organization_id == seed.organization.id,
            models.ClassSubjectLink.class_id == seed.class_.id,
            models.ClassSubjectLink.subject_id == seed.subject.id,
        )
    )


async def _add_second_selected_module(db_session, seed, *, minutes: int = 50):
    module = models.Module(
        organization_id=seed.organization.id,
        subject_id=seed.subject.id,
        name="Módulo B",
        required_minutes=minutes,
        order=2,
    )
    db_session.add(module)
    await db_session.flush()
    db_session.add(
        CurricularRequirement(
            organization_id=seed.organization.id,
            assignment_id=seed.assignment.id,
            module_id=module.id,
            sequence=2,
            required_minutes=minutes,
        )
    )
    await db_session.execute(
        models.class_subject_module.insert().values(
            organization_id=seed.organization.id,
            class_subject_link_id=await _link_id(db_session, seed),
            module_id=module.id,
        )
    )
    await db_session.commit()
    return module


async def _lessons(db_session, seed) -> list[SchedulerLessonV1]:
    return list(
        (
            await db_session.scalars(
                select(SchedulerLessonV1)
                .where(SchedulerLessonV1.organization_id == seed.organization.id)
                .order_by(SchedulerLessonV1.school_date, SchedulerLessonV1.id)
            )
        ).all()
    )


async def _lesson_for_module(db_session, seed, module_id: int) -> SchedulerLessonV1:
    lesson_id = await db_session.scalar(
        select(SchedulerLessonSliceV1.lesson_id)
        .where(
            SchedulerLessonSliceV1.organization_id == seed.organization.id,
            SchedulerLessonSliceV1.module_id == module_id,
        )
        .order_by(SchedulerLessonSliceV1.lesson_id)
        .limit(1)
    )
    return await db_session.get(SchedulerLessonV1, lesson_id)


async def _deselect(db_session, seed, module_id: int) -> None:
    await db_session.execute(
        delete(models.class_subject_module).where(
            models.class_subject_module.c.organization_id == seed.organization.id,
            models.class_subject_module.c.class_subject_link_id == await _link_id(db_session, seed),
            models.class_subject_module.c.module_id == module_id,
        )
    )
    await db_session.commit()


async def test_recovery_accepts_a_logged_falta_on_a_retired_module(db_session, monkeypatch):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="selection_rec_a",
        clerk_org_id="selection_rec_a_org",
        module_minutes=50,
    )
    await _add_second_selected_module(db_session, seed, minutes=50)
    await db_session.commit()
    await seed_published_baseline(db_session, seed)

    history = await _lesson_for_module(db_session, seed, seed.module.id)
    assert history is not None
    now = history.ends_at + timedelta(minutes=1)
    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=history.id,
        status="OCCURRENCE",
        summary="Falta no módulo retirado.",
        notes=None,
        now_utc=now,
        planning_relevant=True,
    )
    await db_session.commit()
    await _deselect(db_session, seed, seed.module.id)

    # Adaptive recovery generates and approves a proposal without failing on
    # the closed module's logged lesson.
    await run_generation(db_session, monkeypatch, seed, key="selection-rec-a", now=now)

    version_id = int(seed.state.active_schedule_version_id)
    published = [
        row
        for row in (
            await db_session.scalars(
                select(SchedulerLessonV1).where(
                    SchedulerLessonV1.organization_id == seed.organization.id,
                    SchedulerLessonV1.version_id == version_id,
                )
            )
        ).all()
    ]
    copied = next(row for row in published if row.school_date == history.school_date)
    assert (copied.starts_at, copied.ends_at) == (history.starts_at, history.ends_at)
    log = await db_session.scalar(
        select(SchedulerLessonLogV1).where(SchedulerLessonLogV1.lesson_id == copied.id)
    )
    assert log is not None and log.status == "OCCURRENCE"
    assert log.summary == "Falta no módulo retirado."

    # The retired module has no planned requirement, so its closed history is
    # the only remaining evidence.
    planned = (
        await db_session.scalars(
            select(CurricularRequirement).where(
                CurricularRequirement.organization_id == seed.organization.id,
                CurricularRequirement.assignment_id == seed.assignment.id,
            )
        )
    ).all()
    assert seed.module.id not in {row.module_id for row in planned}


async def test_unmark_and_remark_an_earlier_module_after_later_progress(db_session, monkeypatch):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="selection_rec_b",
        clerk_org_id="selection_rec_b_org",
        module_minutes=50,
    )
    second = await _add_second_selected_module(db_session, seed, minutes=50)
    await db_session.commit()
    # The scenario tests re-marking a module, not the stability window.
    await set_stability_window(db_session, seed, 0)
    await seed_published_baseline(db_session, seed)

    # The later module B has executed hours before A is unmarked.
    from app.scheduler.domain.demand import ExecutionEntry, ModuleCredit
    from app.scheduler.infrastructure.progress import record_execution

    await record_execution(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        ExecutionEntry(
            "lesson:later",
            1,
            seed.membership.id,
            "Later module progressed",
            (ModuleCredit(second.id, 50),),
            recorded_at=datetime(2026, 9, 2, 9, 0, tzinfo=UTC),
        ),
        planning_relevant=True,
    )
    await db_session.commit()

    await _deselect(db_session, seed, seed.module.id)
    await db_session.execute(
        models.class_subject_module.insert().values(
            organization_id=seed.organization.id,
            class_subject_link_id=await _link_id(db_session, seed),
            module_id=seed.module.id,
        )
    )
    await db_session.commit()

    # Re-marking the earlier module restores it without an error.
    await run_generation(db_session, monkeypatch, seed, key="selection-rec-b")

    requirements = (
        await db_session.scalars(
            select(CurricularRequirement).where(
                CurricularRequirement.organization_id == seed.organization.id,
                CurricularRequirement.assignment_id == seed.assignment.id,
                CurricularRequirement.module_id == seed.module.id,
            )
        )
    ).all()
    assert requirements and requirements[0].planned is True
    assert requirements[0].required_minutes == seed.module.required_minutes
