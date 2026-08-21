"""School Readiness Service — Cumulative 7-level chain evaluation for scheduling readiness."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.models import PreferenceLevel, ScheduleGenerationStrategy
from app.services.availability_matrix_service import AvailabilityMatrixInspector
from app.services.scheduler_fingerprint_service import SchedulerFingerprintService
from app.services.scheduler_state_service import SchedulerStateService

logger = structlog.get_logger(__name__)

PERCENTAGE_MAP = [0, 14, 28, 42, 57, 71, 85, 100]

STEPS_METADATA = [
    ("ACTIVE_CLASSES", "/courses"),
    ("CLASS_SUBJECTS", "/courses"),
    ("MODULES", "/subjects"),
    ("TEACHER_ASSIGNMENT", "/members"),
    ("COMPATIBLE_ROOM", "/rooms"),
    ("TIMESLOTS", "/config"),
    ("TEACHER_AVAILABILITY", "/members"),
]


class SchoolReadinessService:
    """Evaluates the 7 cumulative depths of school readiness for schedule generation."""

    def __init__(self, db: AsyncSession):
        self._db = db

    async def evaluate_bases(self, organization_id: int) -> schemas.BasesReadinessResponse:
        depth = 0
        issues: list[schemas.PreflightIssue] = []

        # 1. Depth 1: Active (non-archived) class exists
        class_q = select(models.Class).where(
            models.Class.organization_id == organization_id,
            models.Class.is_archived.is_(False),
        )
        classes = (await self._db.execute(class_q)).scalars().all()
        if not classes:
            return self._build_response(depth, issues)
        depth = 1

        # 2. Depth 2: ClassSubjectLink for active class in current grade_level
        class_ids = [c.id for c in classes]
        link_q = select(models.ClassSubjectLink).where(
            models.ClassSubjectLink.organization_id == organization_id,
            models.ClassSubjectLink.class_id.in_(class_ids),
        )
        links = (await self._db.execute(link_q)).scalars().all()
        class_by_id = {c.id: c for c in classes}
        valid_links = [
            lnk
            for lnk in links
            if class_by_id.get(lnk.class_id)
            and lnk.grade_level == class_by_id[lnk.class_id].grade_level
        ]
        if not valid_links:
            return self._build_response(depth, issues)
        depth = 2

        # 3. Depth 3: Subject has Module with required_minutes > 0
        subject_ids = {lnk.subject_id for lnk in valid_links}
        module_q = select(models.Module).where(
            models.Module.organization_id == organization_id,
            models.Module.subject_id.in_(subject_ids),
            models.Module.required_minutes > 0,
        )
        modules = (await self._db.execute(module_q)).scalars().all()
        subjects_with_modules = {m.subject_id for m in modules}
        links_with_modules = [lnk for lnk in valid_links if lnk.subject_id in subjects_with_modules]
        if not links_with_modules:
            return self._build_response(depth, issues)
        depth = 3

        # 4. Depth 4: Assigned competent teacher in teacher_subject_link
        assigned_links = [lnk for lnk in links_with_modules if lnk.teacher_id is not None]
        if not assigned_links:
            return self._build_response(depth, issues)

        teacher_ids = {lnk.teacher_id for lnk in assigned_links}
        active_teacher_rows = await self._db.execute(
            select(models.Teacher.id)
            .join(
                models.OrganizationMembership,
                models.OrganizationMembership.id == models.Teacher.organization_membership_id,
            )
            .where(
                models.Teacher.organization_id == organization_id,
                models.Teacher.id.in_(teacher_ids),
                models.OrganizationMembership.organization_id == organization_id,
                models.OrganizationMembership.lifecycle_status
                == models.MembershipLifecycleStatus.active,
            )
        )
        active_teacher_ids = set(active_teacher_rows.scalars().all())
        assigned_links = [lnk for lnk in assigned_links if lnk.teacher_id in active_teacher_ids]
        if not assigned_links:
            return self._build_response(depth, issues)
        teacher_ids = {lnk.teacher_id for lnk in assigned_links}
        comp_q = select(
            models.teacher_subject_link.c.teacher_id,
            models.teacher_subject_link.c.subject_id,
        ).where(
            models.teacher_subject_link.c.organization_id == organization_id,
            models.teacher_subject_link.c.teacher_id.in_(teacher_ids),
        )
        comp_rows = (await self._db.execute(comp_q)).all()
        comp_set = {(r.teacher_id, r.subject_id) for r in comp_rows}
        competent_links = [
            lnk for lnk in assigned_links if (lnk.teacher_id, lnk.subject_id) in comp_set
        ]
        if not competent_links:
            return self._build_response(depth, issues)
        depth = 4

        # 5. Depth 5: Compatible room exists (room.type == subject.required_room_type and room.capacity >= class.size)
        subjects_q = select(models.Subject).where(
            models.Subject.organization_id == organization_id,
            models.Subject.id.in_({lnk.subject_id for lnk in competent_links}),
        )
        subjects = {s.id: s for s in (await self._db.execute(subjects_q)).scalars().all()}
        rooms_q = select(models.Room).where(models.Room.organization_id == organization_id)
        rooms = (await self._db.execute(rooms_q)).scalars().all()

        compatible_links = []
        for lnk in competent_links:
            subj = subjects.get(lnk.subject_id)
            cls_obj = class_by_id.get(lnk.class_id)
            if subj and cls_obj:
                for r in rooms:
                    if r.type == subj.required_room_type and r.capacity >= cls_obj.size:
                        compatible_links.append(lnk)
                        break

        if not compatible_links:
            return self._build_response(depth, issues)
        depth = 5

        # 6. Depth 6: At least one Timeslot exists
        ts_q = select(models.Timeslot).where(models.Timeslot.organization_id == organization_id)
        timeslots = (await self._db.execute(ts_q)).scalars().all()
        if not timeslots:
            return self._build_response(depth, issues)
        depth = 6

        # 7. Depth 7: Teacher has non-impossible availability in timeslot
        inspection = await AvailabilityMatrixInspector.inspect(
            self._db,
            organization_id=organization_id,
            teacher_ids=[lnk.teacher_id for lnk in compatible_links],
            timeslot_ids=[ts.id for ts in timeslots],
        )
        has_available_slot = False
        for lnk in compatible_links:
            for ts in timeslots:
                if inspection.get_score(lnk.teacher_id, ts.id) != PreferenceLevel.IMPOSSIBLE.value:
                    has_available_slot = True
                    break
            if has_available_slot:
                break

        if not has_available_slot:
            return self._build_response(depth, issues)
        depth = 7

        # When depth is 7, resolve active school year and calculate canonical fingerprint
        state_service = SchedulerStateService(self._db)
        active_school_year = await state_service.get_active_school_year(organization_id)
        if active_school_year is None:
            issues.append(
                schemas.PreflightIssue(
                    code="ACTIVE_SCHOOL_YEAR_REQUIRED",
                    severity="BLOCKER",
                    message="Defina o ano letivo ativo antes de gerar.",
                    route="/config",
                )
            )
            return self._build_response(depth, issues, fingerprint=None)

        fingerprint_service = SchedulerFingerprintService(self._db)
        fp_result = await fingerprint_service.generation_input_fingerprint(
            organization_id=organization_id,
            school_year_id=active_school_year.id,
            strategy=ScheduleGenerationStrategy.COMPLETE_GENERATION,
        )
        return self._build_response(depth, issues, fingerprint=fp_result.value)

    def _build_response(
        self,
        depth: int,
        issues: list[schemas.PreflightIssue],
        fingerprint: str | None = None,
    ) -> schemas.BasesReadinessResponse:
        percentage = PERCENTAGE_MAP[min(depth, 7)]
        steps: list[schemas.ReadinessStep] = []
        for i, (code, route) in enumerate(STEPS_METADATA):
            status = "COMPLETE" if depth > i else "PENDING"
            steps.append(schemas.ReadinessStep(code=code, status=status, route=route))

        return schemas.BasesReadinessResponse(
            percentage=percentage,
            depth=depth,
            complete=(depth == 7 and not any(i.severity == "BLOCKER" for i in issues)),
            fingerprint=fingerprint,
            issues=issues,
            steps=steps,
        )
