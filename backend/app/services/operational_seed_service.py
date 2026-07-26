"""Deterministic operational seed using the canonical scheduler lifecycle."""

from __future__ import annotations

from datetime import date, time
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app import models
from app.db.tenant import set_async_tenant_context, set_sync_tenant_context

ACADEMIC_YEAR = "2025/2026"
REFERENCE_DATE = date(2026, 4, 20)


def _one_or_create(db: Session, model: type, /, defaults: dict | None = None, **identity):
    instance = db.execute(select(model).filter_by(**identity)).scalar_one_or_none()
    if instance is None:
        instance = model(**identity, **(defaults or {}))
        db.add(instance)
        db.flush()
    return instance


def _seed_organization(db: Session, *, suffix: str) -> dict[str, int]:
    slug = suffix.lower()
    organization_name = f"Escola Piloto Operacional {suffix}"
    email = f"admin.operacional.{slug}@seed.pt"
    principal = (
        db.execute(
            text(
                """
            SELECT account_id, organization_id, membership_id
            FROM app_security.bootstrap_founder(
                :clerk_user_id, :clerk_org_id, :organization_name,
                :email, :profile_name, :provider_membership_id
            )
            """
            ),
            {
                "clerk_user_id": f"seed_admin_operational_{slug}",
                "clerk_org_id": f"org_operational_{slug}",
                "organization_name": organization_name,
                "email": email,
                "profile_name": f"Admin Operacional {suffix}",
                "provider_membership_id": f"seed_membership_operational_{slug}",
            },
        )
        .mappings()
        .one()
    )
    set_sync_tenant_context(db, principal["organization_id"])
    organization = db.get(models.Organization, principal["organization_id"])
    admin = db.get(models.User, principal["account_id"])
    membership = db.get(models.OrganizationMembership, principal["membership_id"])
    if organization is None or admin is None or membership is None:
        raise RuntimeError("Operational seed principal could not be loaded")
    membership.can_admin = True
    membership.can_teach = True
    membership.teacher_access_mode = models.TeacherAccessMode.platform
    settings = _one_or_create(
        db,
        models.OrganizationSettings,
        organization_id=organization.id,
        defaults={
            "school_start_date": date(2025, 9, 15),
            "school_hard_end_date": date(2026, 7, 31),
            "repair_stability_window_days": 14,
        },
    )
    del settings

    school_year = _one_or_create(
        db,
        models.SchedulerSchoolYear,
        organization_id=organization.id,
        label=ACADEMIC_YEAR,
        defaults={
            "start_date": date(2025, 9, 15),
            "hard_end_date": date(2026, 7, 31),
            "timezone": "Europe/Lisbon",
            "is_active": True,
        },
    )
    _one_or_create(
        db,
        models.SchedulerSchoolYearState,
        organization_id=organization.id,
        school_year_id=school_year.id,
    )

    teacher = db.execute(
        select(models.Teacher).where(models.Teacher.organization_membership_id == membership.id)
    ).scalar_one_or_none()
    if teacher is None:
        teacher = models.Teacher(
            organization_id=organization.id,
            organization_membership_id=membership.id,
        )
        db.add(teacher)
        db.flush()

    course = _one_or_create(
        db,
        models.Course,
        organization_id=organization.id,
        abbreviation=f"OP{suffix}",
        defaults={"name": f"Curso Operacional {suffix}"},
    )
    klass = _one_or_create(
        db,
        models.Class,
        organization_id=organization.id,
        name=f"Turma Operacional {suffix}",
        defaults={
            "size": 24,
            "start_year": 2025,
            "end_year": 2028,
            "grade_level": 10,
            "course_id": course.id,
        },
    )
    room = _one_or_create(
        db,
        models.Room,
        organization_id=organization.id,
        name=f"Sala Operacional {suffix}",
        defaults={"capacity": 30, "type": models.RoomType.normal},
    )
    subject = _one_or_create(
        db,
        models.Subject,
        organization_id=organization.id,
        name=f"Programação Operacional {suffix}",
        defaults={"required_room_type": models.RoomType.normal},
    )
    _one_or_create(
        db,
        models.Module,
        organization_id=organization.id,
        subject_id=subject.id,
        order=0,
        defaults={
            "name": f"Módulo Operacional {suffix}",
            "code": f"OP-{suffix}-01",
            "required_minutes": 60,
        },
    )
    timeslot = _one_or_create(
        db,
        models.Timeslot,
        organization_id=organization.id,
        day_of_week=0,
        start_time=time(9),
        defaults={"end_time": time(10)},
    )
    _one_or_create(
        db,
        models.ClassSubjectLink,
        organization_id=organization.id,
        class_id=klass.id,
        subject_id=subject.id,
        grade_level=klass.grade_level,
        defaults={"teacher_id": teacher.id},
    )
    teacher_subject_exists = db.scalar(
        select(models.teacher_subject_link.c.teacher_id).where(
            models.teacher_subject_link.c.organization_id == organization.id,
            models.teacher_subject_link.c.teacher_id == teacher.id,
            models.teacher_subject_link.c.subject_id == subject.id,
        )
    )
    if teacher_subject_exists is None:
        db.execute(
            models.teacher_subject_link.insert().values(
                organization_id=organization.id,
                teacher_id=teacher.id,
                subject_id=subject.id,
            )
        )
    _one_or_create(
        db,
        models.Availability,
        organization_id=organization.id,
        teacher_id=teacher.id,
        timeslot_id=timeslot.id,
        defaults={"score": models.PreferenceLevel.PREFERRED.value},
    )

    return {
        "organization_id": organization.id,
        "admin_account_id": admin.id,
        "school_year_id": school_year.id,
        "teacher_id": teacher.id,
        "class_id": klass.id,
        "subject_id": subject.id,
        "room_id": room.id,
    }


def seed_operational_scenarios_sync(db: Session) -> dict[str, Any]:
    """Upsert two isolated canonical tenants without committing the caller's UoW."""
    tenants = [_seed_organization(db, suffix=suffix) for suffix in ("A", "B")]
    counted_models = (
        ("organizations", models.Organization),
        ("memberships", models.OrganizationMembership),
        ("teachers", models.Teacher),
        ("classes", models.Class),
        ("class_subject_links", models.ClassSubjectLink),
    )
    totals = {name: 0 for name, _ in counted_models}
    for tenant in tenants:
        set_sync_tenant_context(db, tenant["organization_id"])
        for name, model in counted_models:
            totals[name] += int(db.scalar(select(func.count(model.id))) or 0)
    return {
        "signature": {
            "profile": "canonical_operational_v1",
            "reference_date": REFERENCE_DATE.isoformat(),
            "organization_count": len(tenants),
            "totals": totals,
        },
        "runtime": {"tenants": tenants},
    }


async def seed_and_publish_operational_scenarios(db: AsyncSession) -> dict[str, Any]:
    """Seed master data and publish one real generated schedule per tenant."""
    from app.services.scheduler_approval_service import SchedulerApprovalService
    from app.services.scheduler_complete_engine import run_complete_generation
    from app.services.scheduler_generation_service import SchedulerGenerationService
    from app.services.scheduler_job_runtime import SchedulerJobRuntime
    from app.services.scheduler_job_service import SchedulerJobService

    async with db.begin():
        payload = await db.run_sync(seed_operational_scenarios_sync)

    stable_keys: list[str] = []
    active_block_count = 0
    for tenant in payload["runtime"]["tenants"]:
        organization_id = tenant["organization_id"]
        await set_async_tenant_context(db, organization_id)
        existing_count = int(
            await db.scalar(
                select(func.count(models.ActiveScheduleBlock.id)).where(
                    models.ActiveScheduleBlock.organization_id == organization_id,
                    models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
                )
            )
            or 0
        )
        if existing_count == 0:
            draft_id = await db.scalar(
                select(models.SchedulerSchoolYearState.pending_draft_id).where(
                    models.SchedulerSchoolYearState.organization_id == organization_id,
                    models.SchedulerSchoolYearState.school_year_id == tenant["school_year_id"],
                )
            )
            if draft_id is None:
                selection = await SchedulerGenerationService(db).select_strategy(organization_id)
                handle = await SchedulerJobService(db).create_or_get_job(
                    selection,
                    requested_by_membership_id=tenant["admin_account_id"],
                    idempotency_key=f"operational-seed:{organization_id}:{ACADEMIC_YEAR}",
                )
                await db.commit()
                finished = await SchedulerJobRuntime(db).execute(
                    handle.job.id,
                    run_complete_generation,
                    organization_id=organization_id,
                )
                if finished.job_status != models.ScheduleGenerationJobStatus.SUCCEEDED:
                    raise RuntimeError(
                        "Operational seed generation failed: "
                        f"{finished.failure_code}: {finished.failure_message}"
                    )
                await set_async_tenant_context(db, organization_id)
                draft_id = await db.scalar(
                    select(models.ScheduleDraft.id).where(
                        models.ScheduleDraft.organization_id == organization_id,
                        models.ScheduleDraft.generation_job_id == finished.id,
                    )
                )
                if draft_id is None:
                    raise RuntimeError("Operational seed generation produced no draft")
            await SchedulerApprovalService(db).approve(
                organization_id,
                draft_id,
                decided_by_membership_id=tenant["admin_account_id"],
            )
            await db.commit()

        await set_async_tenant_context(db, organization_id)
        keys = list(
            await db.scalars(
                select(models.ActiveScheduleBlock.stable_block_key)
                .where(
                    models.ActiveScheduleBlock.organization_id == organization_id,
                    models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
                )
                .order_by(models.ActiveScheduleBlock.stable_block_key)
            )
        )
        stable_keys.extend(f"{organization_id}:{key}" for key in keys)
        active_block_count += len(keys)
        await db.rollback()

    payload["signature"]["active_block_count"] = active_block_count
    payload["signature"]["active_stable_keys"] = stable_keys
    return payload
