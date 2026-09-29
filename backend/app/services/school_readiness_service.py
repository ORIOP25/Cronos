"""Six-level readiness evaluation for schedule generation."""

from __future__ import annotations

import structlog
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app import models, schemas
from app.models import ScheduleGenerationStrategy
from app.services.scheduler_fingerprint_service import SchedulerFingerprintService
from app.services.scheduler_state_service import SchedulerStateService

logger = structlog.get_logger(__name__)

STEPS_METADATA = [
    ("ACTIVE_CLASSES", "/courses"),
    ("MODULES", "/subjects"),
    ("TEACHERS", "/members"),
    ("TEACHER_ASSIGNMENT", "/courses"),
    ("COMPATIBLE_ROOM", "/rooms"),
    ("TEACHER_AVAILABILITY", "/members"),
]

READINESS_ISSUE_MESSAGES = {
    "ACTIVE_CLASSES": "Registe pelo menos uma turma ativa.",
    "MODULES": "Adicione módulos com carga horária positiva às disciplinas.",
    "TEACHERS": "Registe pelo menos um professor ativo.",
    "TEACHER_ASSIGNMENT": "Atribua um professor ativo e competente à disciplina da turma.",
    "COMPATIBLE_ROOM": "Registe uma sala compatível com a tipologia e lotação.",
    "TEACHER_AVAILABILITY": "Registe disponibilidade docente não impossível.",
}


class SchoolReadinessService:
    """Evaluate the cumulative readiness chain with one aggregate query."""

    def __init__(self, db: AsyncSession):
        self._db = db

    async def evaluate_bases(
        self,
        organization_id: int,
        *,
        resolve_fingerprint: bool = True,
    ) -> schemas.BasesReadinessResponse:
        class_alias = aliased(models.Class)
        link_alias = aliased(models.ClassSubjectLink)
        subject_alias = aliased(models.Subject)
        teacher_alias = aliased(models.Teacher)
        membership_alias = aliased(models.OrganizationMembership)

        valid_link = (
            (link_alias.organization_id == organization_id)
            & (class_alias.organization_id == organization_id)
            & (subject_alias.organization_id == organization_id)
            & class_alias.is_archived.is_(False)
            & subject_alias.is_archived.is_(False)
            & (link_alias.grade_level == class_alias.grade_level)
            & exists(
                select(1).where(
                    models.Module.organization_id == organization_id,
                    models.Module.subject_id == link_alias.subject_id,
                    models.Module.required_minutes > 0,
                )
            )
        )
        competent_teacher = exists(
            select(1)
            .select_from(teacher_alias)
            .join(
                membership_alias,
                membership_alias.id == teacher_alias.organization_membership_id,
            )
            .where(
                teacher_alias.organization_id == organization_id,
                teacher_alias.id == link_alias.teacher_id,
                membership_alias.organization_id == organization_id,
                membership_alias.lifecycle_status == models.MembershipLifecycleStatus.active,
                membership_alias.can_teach.is_(True),
            )
        )
        competent_link = (
            valid_link
            & link_alias.teacher_id.is_not(None)
            & competent_teacher
            & exists(
                select(1).where(
                    models.teacher_subject_link.c.organization_id == organization_id,
                    models.teacher_subject_link.c.teacher_id == link_alias.teacher_id,
                    models.teacher_subject_link.c.subject_id == link_alias.subject_id,
                )
            )
        )
        active_teacher = exists(
            select(1)
            .select_from(teacher_alias)
            .join(
                membership_alias,
                membership_alias.id == teacher_alias.organization_membership_id,
            )
            .where(
                teacher_alias.organization_id == organization_id,
                membership_alias.organization_id == organization_id,
                membership_alias.lifecycle_status == models.MembershipLifecycleStatus.active,
                membership_alias.can_teach.is_(True),
            )
        )
        compatible_room = exists(
            select(1)
            .select_from(models.Room)
            .where(
                models.Room.organization_id == organization_id,
                models.Room.type == subject_alias.required_room_type,
                models.Room.capacity >= class_alias.size,
                models.Room.is_archived.is_(False),
            )
            .correlate(class_alias, subject_alias)
        )
        compatible_link = competent_link & compatible_room
        possible_timeslot = exists(
            select(1)
            .select_from(models.Timeslot)
            .where(
                models.Timeslot.organization_id == organization_id,
                ~exists(
                    select(1).where(
                        models.Availability.organization_id == organization_id,
                        models.Availability.teacher_id == link_alias.teacher_id,
                        models.Availability.timeslot_id == models.Timeslot.id,
                        models.Availability.score == models.PreferenceLevel.IMPOSSIBLE.value,
                    )
                ).correlate(link_alias, models.Timeslot),
            )
            .correlate(link_alias)
        )

        facts_query = select(
            exists(
                select(1).where(
                    models.Class.organization_id == organization_id,
                    models.Class.is_archived.is_(False),
                )
            ).label("active_classes"),
            exists(
                select(1)
                .select_from(models.Module)
                .join(models.Subject, models.Subject.id == models.Module.subject_id)
                .where(
                    models.Module.organization_id == organization_id,
                    models.Module.required_minutes > 0,
                    models.Subject.is_archived.is_(False),
                )
            ).label("modules"),
            active_teacher.label("active_teacher"),
            exists(
                select(1)
                .select_from(link_alias)
                .join(class_alias, class_alias.id == link_alias.class_id)
                .join(subject_alias, subject_alias.id == link_alias.subject_id)
                .where(competent_link)
            ).label("teacher_assignment"),
            exists(
                select(1)
                .select_from(link_alias)
                .join(class_alias, class_alias.id == link_alias.class_id)
                .join(subject_alias, subject_alias.id == link_alias.subject_id)
                .where(compatible_link)
            ).label("compatible_room"),
            exists(
                select(1)
                .select_from(link_alias)
                .join(class_alias, class_alias.id == link_alias.class_id)
                .join(subject_alias, subject_alias.id == link_alias.subject_id)
                .where(compatible_link & possible_timeslot)
            ).label("teacher_availability"),
        )
        facts = (await self._db.execute(facts_query)).one()._mapping

        depth = 0
        for fact_name in (
            "active_classes",
            "modules",
            "active_teacher",
            "teacher_assignment",
            "compatible_room",
            "teacher_availability",
        ):
            if not facts[fact_name]:
                break
            depth += 1

        step_routes: dict[str, str] = {}
        if depth in (3, 4):
            step_routes["TEACHER_ASSIGNMENT"] = await self._first_class_subject_route(
                organization_id
            )

        fingerprint = None
        if depth == len(STEPS_METADATA):
            active_school_year = await SchedulerStateService(self._db).get_active_school_year(
                organization_id
            )
            if active_school_year is None:
                return self._build_response(
                    depth,
                    [
                        schemas.PreflightIssue(
                            code="ACTIVE_SCHOOL_YEAR_REQUIRED",
                            severity="BLOCKER",
                            message="Defina o ano letivo ativo antes de gerar.",
                            route="/config",
                        )
                    ],
                    step_routes=step_routes,
                )
            if resolve_fingerprint:
                fingerprint = (
                    await SchedulerFingerprintService(self._db).generation_input_fingerprint(
                        organization_id=organization_id,
                        school_year_id=active_school_year.id,
                        strategy=ScheduleGenerationStrategy.COMPLETE_GENERATION,
                    )
                ).value

        return self._build_response(
            depth,
            [],
            fingerprint=fingerprint,
            step_routes=step_routes,
        )

    async def _first_class_subject_route(self, organization_id: int) -> str:
        class_alias = aliased(models.Class)
        link_alias = aliased(models.ClassSubjectLink)
        row = (
            await self._db.execute(
                select(class_alias.course_id, class_alias.id)
                .select_from(link_alias)
                .join(class_alias, class_alias.id == link_alias.class_id)
                .where(
                    link_alias.organization_id == organization_id,
                    class_alias.organization_id == organization_id,
                    class_alias.is_archived.is_(False),
                    link_alias.grade_level == class_alias.grade_level,
                )
                .order_by(link_alias.class_id, link_alias.subject_id)
                .limit(1)
            )
        ).first()
        if row is None:
            return "/courses"
        return f"/courses/{row.course_id}/classes/{row.id}/subjects"

    def _build_response(
        self,
        depth: int,
        issues: list[schemas.PreflightIssue],
        fingerprint: str | None = None,
        step_routes: dict[str, str] | None = None,
    ) -> schemas.BasesReadinessResponse:
        routes = {code: route for code, route in STEPS_METADATA}
        routes.update(step_routes or {})
        if depth < len(STEPS_METADATA) and not issues:
            code, _ = STEPS_METADATA[depth]
            issues = [
                schemas.PreflightIssue(
                    code=f"{code}_REQUIRED",
                    severity="BLOCKER",
                    message=READINESS_ISSUE_MESSAGES[code],
                    route=routes[code],
                )
            ]
        percentage = round(depth / len(STEPS_METADATA) * 100)
        steps = [
            schemas.ReadinessStep(
                code=code,
                status="COMPLETE" if depth > index else "PENDING",
                route=routes[code],
            )
            for index, (code, _) in enumerate(STEPS_METADATA)
        ]
        return schemas.BasesReadinessResponse(
            percentage=percentage,
            depth=depth,
            complete=depth == len(STEPS_METADATA)
            and not any(issue.severity == "BLOCKER" for issue in issues),
            fingerprint=fingerprint,
            issues=issues,
            steps=steps,
        )
