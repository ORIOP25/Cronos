"""Prepare the v1 projection for browser tests against an isolated Docker stack."""

from __future__ import annotations

import argparse
import asyncio
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.db.database import SessionLocal
from app.db.tenant import set_async_tenant_context
from app.scheduler.infrastructure.models import CurricularAssignment, CurricularRequirement
from app.scheduler.infrastructure.progress import configure_school_year


async def seed_scheduler_e2e(
    db: AsyncSession,
    *,
    organization_id: int,
    class_id: int,
    subject_id: int,
    preferred_end_date: date,
) -> None:
    year = await db.scalar(
        select(models.SchedulerSchoolYear).where(
            models.SchedulerSchoolYear.organization_id == organization_id,
            models.SchedulerSchoolYear.is_active.is_(True),
        )
    )
    classroom = await db.scalar(
        select(models.Class).where(
            models.Class.organization_id == organization_id,
            models.Class.id == class_id,
        )
    )
    if year is None or classroom is None:
        raise ValueError("The E2E school year or class was not found.")
    link = await db.scalar(
        select(models.ClassSubjectLink).where(
            models.ClassSubjectLink.organization_id == organization_id,
            models.ClassSubjectLink.class_id == class_id,
            models.ClassSubjectLink.subject_id == subject_id,
            models.ClassSubjectLink.grade_level == classroom.grade_level,
        )
    )
    if link is None or link.teacher_id is None:
        raise ValueError("The E2E class subject requires an assigned teacher.")
    modules = (
        await db.scalars(
            select(models.Module)
            .where(
                models.Module.organization_id == organization_id,
                models.Module.subject_id == subject_id,
            )
            .order_by(models.Module.order, models.Module.id)
        )
    ).all()
    if not modules:
        raise ValueError("The E2E subject requires at least one module.")

    await configure_school_year(db, organization_id, year.id, preferred_end_date=preferred_end_date)
    assignment = await db.scalar(
        select(CurricularAssignment).where(
            CurricularAssignment.organization_id == organization_id,
            CurricularAssignment.school_year_id == year.id,
            CurricularAssignment.class_id == class_id,
            CurricularAssignment.subject_id == subject_id,
        )
    )
    if assignment is None:
        assignment = CurricularAssignment(
            organization_id=organization_id,
            school_year_id=year.id,
            class_id=class_id,
            subject_id=subject_id,
            teacher_id=link.teacher_id,
        )
        db.add(assignment)
        await db.flush()
    else:
        assignment.teacher_id = link.teacher_id

    existing_requirements = {
        row.module_id: row
        for row in (
            await db.scalars(
                select(CurricularRequirement).where(
                    CurricularRequirement.organization_id == organization_id,
                    CurricularRequirement.assignment_id == assignment.id,
                )
            )
        ).all()
    }
    for sequence, module in enumerate(modules, start=1):
        requirement = existing_requirements.get(module.id)
        if requirement is None:
            db.add(
                CurricularRequirement(
                    organization_id=organization_id,
                    assignment_id=assignment.id,
                    module_id=module.id,
                    sequence=sequence,
                    required_minutes=module.required_minutes,
                )
            )
        else:
            requirement.sequence = sequence
            requirement.required_minutes = module.required_minutes
    await db.flush()


async def _main(args: argparse.Namespace) -> None:
    async with SessionLocal() as db, db.begin():
        await set_async_tenant_context(db, args.organization_id)
        await seed_scheduler_e2e(
            db,
            organization_id=args.organization_id,
            class_id=args.class_id,
            subject_id=args.subject_id,
            preferred_end_date=date.fromisoformat(args.preferred_end_date),
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--organization-id", type=int, required=True)
    parser.add_argument("--class-id", type=int, required=True)
    parser.add_argument("--subject-id", type=int, required=True)
    parser.add_argument("--preferred-end-date", required=True)
    asyncio.run(_main(parser.parse_args()))
