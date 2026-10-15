import structlog
from sqlalchemy import and_, func, or_
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.scheduler.domain.constraint_policy import (
    RoomEligibilityReason,
    SchoolConstraintPolicy,
    assess_room_eligibility,
)
from app.scheduler.infrastructure.models import SchedulerProposalV1
from app.services import grid_version_service
from app.services.availability_matrix_service import AvailabilityMatrixInspector
from app.services.scheduler_fingerprint_service import SchedulerFingerprintService
from app.services.scheduler_state_service import SchedulerStateService

logger = structlog.get_logger(__name__)


CONFIG_ROUTE = "/config"


async def _get_latest_settings_with_dates(
    db: AsyncSession,
    organization_id: int,
) -> models.OrganizationSettings | None:
    settings_result = await db.execute(
        sa_select(models.OrganizationSettings).where(
            models.OrganizationSettings.organization_id == organization_id,
            models.OrganizationSettings.school_start_date.isnot(None),
            models.OrganizationSettings.school_hard_end_date.isnot(None),
        )
    )
    return settings_result.scalars().first()


async def _get_generation_workload_counts(
    db: AsyncSession, organization_id: int
) -> tuple[int, int]:
    class_subject_count = await db.scalar(
        sa_select(func.count(models.ClassSubjectLink.id))
        .join(models.Class, models.ClassSubjectLink.class_id == models.Class.id)
        .where(
            models.Class.organization_id == organization_id,
            models.ClassSubjectLink.organization_id == organization_id,
            models.Class.is_archived == False,  # noqa: E712
            models.ClassSubjectLink.grade_level == models.Class.grade_level,
        )
    )
    count = class_subject_count or 0
    return count, count


async def _collect_generation_teacher_ids(db: AsyncSession, organization_id: int) -> set[int]:
    class_subject_teacher_rows = await db.execute(
        sa_select(models.ClassSubjectLink.teacher_id)
        .join(models.Class, models.ClassSubjectLink.class_id == models.Class.id)
        .join(models.Teacher, models.Teacher.id == models.ClassSubjectLink.teacher_id)
        .join(
            models.OrganizationMembership,
            models.OrganizationMembership.id == models.Teacher.organization_membership_id,
        )
        .where(
            models.Class.organization_id == organization_id,
            models.ClassSubjectLink.organization_id == organization_id,
            models.Class.is_archived == False,  # noqa: E712
            models.ClassSubjectLink.teacher_id.isnot(None),
            models.ClassSubjectLink.grade_level == models.Class.grade_level,
            models.OrganizationMembership.organization_id == organization_id,
            models.OrganizationMembership.lifecycle_status
            == models.MembershipLifecycleStatus.active,
            models.OrganizationMembership.can_teach.is_(True),
        )
        .distinct()
    )
    return {row[0] for row in class_subject_teacher_rows.all()}


async def _collect_generation_subject_ids(db: AsyncSession, organization_id: int) -> set[int]:
    class_subject_subject_rows = await db.execute(
        sa_select(models.ClassSubjectLink.subject_id)
        .join(models.Class, models.ClassSubjectLink.class_id == models.Class.id)
        .where(
            models.Class.organization_id == organization_id,
            models.ClassSubjectLink.organization_id == organization_id,
            models.Class.is_archived == False,  # noqa: E712
            models.ClassSubjectLink.teacher_id.isnot(None),
            models.ClassSubjectLink.grade_level == models.Class.grade_level,
        )
        .distinct()
    )
    return {row[0] for row in class_subject_subject_rows.all()}


async def _validate_teacher_availabilities(
    db: AsyncSession,
    organization_id: int,
    teacher_ids: set[int],
    timeslot_ids: set[int],
) -> str | None:
    if not teacher_ids or not timeslot_ids:
        return None

    missing_availability_ids = await AvailabilityMatrixInspector.fully_impossible_teacher_ids(
        db,
        organization_id=organization_id,
        teacher_ids=teacher_ids,
        timeslot_ids=timeslot_ids,
    )
    if not missing_availability_ids:
        return None

    teacher_name_rows = await db.execute(
        sa_select(models.Teacher.name)
        .where(
            models.Teacher.organization_id == organization_id,
            models.Teacher.id.in_(missing_availability_ids),
        )
        .order_by(models.Teacher.name)
    )
    missing_names = [row[0] for row in teacher_name_rows.all()]
    return (
        "Professores com todos os blocos marcados como Impossível: "
        f"{', '.join(missing_names)}. "
        "Marque pelo menos um bloco como Neutro, Evitar ou Preferencial em "
        "Equipa > Editar disponibilidade."
    )


async def _validate_class_availability(
    db: AsyncSession,
    organization_id: int,
    timeslot_ids: set[int],
) -> list[schemas.PreflightIssue]:
    """One blocker per eligible class whose every visible block is IMPOSSIBLE.

    A missing class-availability row means the block is possible (NEUTRAL), so the
    class is blocked only when the count of impossible rows matches every visible
    block. The eligibility filter mirrors the generation inputs: non-archived
    class, class-subject link with a teacher, and a matching grade level.
    """
    if not timeslot_ids:
        return []
    impossible_blocks = (
        sa_select(func.count())
        .select_from(models.ClassAvailability)
        .where(
            models.ClassAvailability.organization_id == organization_id,
            models.ClassAvailability.class_id == models.Class.id,
            models.ClassAvailability.timeslot_id.in_(timeslot_ids),
            models.ClassAvailability.score == models.PreferenceLevel.IMPOSSIBLE.value,
        )
        .correlate(models.Class)
        .scalar_subquery()
    )
    rows = (
        await db.execute(
            sa_select(
                models.Class.id,
                models.Class.name,
                models.Class.course_id,
            )
            .select_from(models.ClassSubjectLink)
            .join(models.Class, models.Class.id == models.ClassSubjectLink.class_id)
            .where(
                models.Class.organization_id == organization_id,
                models.ClassSubjectLink.organization_id == organization_id,
                models.Class.is_archived.is_(False),
                models.ClassSubjectLink.teacher_id.isnot(None),
                models.ClassSubjectLink.grade_level == models.Class.grade_level,
                impossible_blocks == len(timeslot_ids),
            )
            .distinct()
            .order_by(models.Class.name, models.Class.id)
        )
    ).all()
    return [
        schemas.PreflightIssue(
            code="CLASS_WITHOUT_AVAILABILITY",
            severity="BLOCKER",
            message=(
                f"A turma {row.name} tem todos os blocos marcados como Impossível. "
                "Marque pelo menos um bloco como Neutro, Evitar ou Preferencial."
            ),
            route=f"/courses/{row.course_id}/classes/{row.id}",
        )
        for row in rows
    ]


async def _validate_subject_requirements(
    db: AsyncSession,
    organization_id: int,
    subject_ids: set[int],
) -> list[str]:
    if not subject_ids:
        return []

    errors: list[str] = []
    module_rows = await db.execute(
        sa_select(models.Module.subject_id, models.Module.required_minutes).where(
            models.Module.organization_id == organization_id,
            models.Module.subject_id.in_(subject_ids),
        )
    )
    modules_by_subject: dict[int, list[int]] = {}
    for subject_id, hours_total in module_rows.all():
        modules_by_subject.setdefault(subject_id, []).append(hours_total)

    missing_module_subject_ids = {
        subject_id for subject_id in subject_ids if subject_id not in modules_by_subject
    }
    invalid_module_subject_ids = {
        subject_id
        for subject_id, hours_list in modules_by_subject.items()
        if any(hours <= 0 for hours in hours_list)
    }
    impacted_subject_ids = missing_module_subject_ids | invalid_module_subject_ids

    if impacted_subject_ids:
        subject_rows = await db.execute(
            sa_select(models.Subject.id, models.Subject.name).where(
                models.Subject.organization_id == organization_id,
                models.Subject.id.in_(impacted_subject_ids),
            )
        )
        subject_name_map = {row[0]: row[1] for row in subject_rows.all()}

        if missing_module_subject_ids:
            missing_names = sorted(
                subject_name_map.get(sid, f"ID {sid}") for sid in missing_module_subject_ids
            )
            errors.append(
                "Disciplinas sem módulos definidos: "
                f"{', '.join(missing_names)}. "
                "Adicione módulos com horas > 0 em Disciplinas."
            )

        if invalid_module_subject_ids:
            invalid_names = sorted(
                subject_name_map.get(sid, f"ID {sid}") for sid in invalid_module_subject_ids
            )
            errors.append(
                "Disciplinas com módulos inválidos (hours_total <= 0): "
                f"{', '.join(invalid_names)}. "
                "Corrija a carga horária dos módulos."
            )

    return errors


def _room_issue_message(issue: dict[str, object]) -> str:
    class_name = issue["class_name"]
    subject_name = issue["subject_name"]
    room_type = issue["required_room_type"]
    reason = issue["reason"]
    if reason == RoomEligibilityReason.NO_ROOM_OF_TYPE.value:
        return (
            f"{class_name} / {subject_name}: não existe uma sala do tipo «{room_type}». "
            "Adicione uma sala desse tipo em Salas."
        )
    if reason == RoomEligibilityReason.INSUFFICIENT_CAPACITY.value:
        return (
            f"{class_name} / {subject_name} ({issue['required_capacity']} alunos): "
            f"a maior sala do tipo «{room_type}» tem "
            f"{issue['max_available_capacity']} lugares. Aumente a lotação em Salas."
        )
    return (
        f"{class_name} / {subject_name} ({issue['required_capacity']} alunos): "
        "as salas permitidas pelas regras não têm lugares suficientes. "
        "Ajuste as regras ou as salas em Salas."
    )


async def _validate_room_requirements(
    db: AsyncSession,
    organization_id: int,
) -> list[schemas.PreflightIssue]:
    """One structured NO_ELIGIBLE_ROOM diagnosis per active class/subject pair."""
    rooms = [
        (room.id, room.type.value, room.capacity)
        for room in (
            await db.scalars(
                sa_select(models.Room)
                .where(
                    models.Room.organization_id == organization_id,
                    models.Room.is_archived.is_(False),
                )
                .order_by(models.Room.id)
            )
        ).all()
    ]
    constraint_rows = (
        await db.scalars(
            sa_select(models.Constraint).where(models.Constraint.organization_id == organization_id)
        )
    ).all()
    parsed = SchoolConstraintPolicy.parse(constraint_rows)
    specific_rooms = parsed.policy.specific_rooms if parsed.policy is not None else {}

    rows = (
        await db.execute(
            sa_select(
                models.Class.id.label("class_id"),
                models.Class.name.label("class_name"),
                models.Class.size.label("class_size"),
                models.Class.is_archived.label("is_archived"),
                models.Class.course_id.label("course_id"),
                models.Subject.id.label("subject_id"),
                models.Subject.name.label("subject_name"),
                models.Subject.required_room_type.label("required_room_type"),
                models.joint_lesson_group_member.c.group_id.label("joint_group_id"),
            )
            .select_from(models.ClassSubjectLink)
            .join(models.Class, models.Class.id == models.ClassSubjectLink.class_id)
            .join(models.Subject, models.Subject.id == models.ClassSubjectLink.subject_id)
            .outerjoin(
                models.joint_lesson_group_member,
                and_(
                    models.joint_lesson_group_member.c.class_subject_link_id
                    == models.ClassSubjectLink.id,
                    models.joint_lesson_group_member.c.organization_id == organization_id,
                ),
            )
            .where(
                models.ClassSubjectLink.organization_id == organization_id,
                models.Class.organization_id == organization_id,
                models.Subject.organization_id == organization_id,
                models.Class.is_archived.is_(False),
                models.ClassSubjectLink.teacher_id.is_not(None),
                models.ClassSubjectLink.grade_level == models.Class.grade_level,
            )
            .order_by(
                models.Class.name,
                models.Subject.name,
                models.Class.id,
                models.Subject.id,
            )
        )
    ).all()

    issues: list[schemas.PreflightIssue] = []
    for row in rows:
        eligibility = assess_room_eligibility(
            rooms,
            required_room_type=row.required_room_type.value,
            required_capacity=row.class_size,
            allowed_room_ids=specific_rooms.get((row.class_id, row.subject_id)),
        )
        if eligibility.reason is None:
            continue
        context = {
            "class_id": row.class_id,
            "class_name": row.class_name,
            "subject_id": row.subject_id,
            "subject_name": row.subject_name,
            "required_room_type": row.required_room_type.value,
            "required_capacity": row.class_size,
            "max_available_capacity": eligibility.max_available_capacity,
            "reason": eligibility.reason.value,
        }
        issues.append(
            schemas.PreflightIssue(
                code="NO_ELIGIBLE_ROOM",
                severity="BLOCKER",
                message=_room_issue_message(context),
                route="/rooms",
                context=context,
            )
        )
    issues.extend(_joint_requirements_from_rows(rows, rooms, specific_rooms))
    return issues


def _joint_room_message(subject_name, class_names, room_type, required_capacity) -> str:
    classes = ", ".join(class_names)
    return (
        f"A aula conjunta de {subject_name} ({classes}) precisa de uma sala de "
        f"{room_type} com pelo menos {required_capacity} lugares."
    )


def _joint_requirements_from_rows(
    rows,
    rooms: list[tuple[int, str, int]],
    specific_rooms: dict,
) -> list[schemas.PreflightIssue]:
    """Joint group diagnosis reusing the class/subject rows already loaded."""
    groups: dict[int, list] = {}
    for row in rows:
        if row.joint_group_id is None:
            continue
        groups.setdefault(row.joint_group_id, []).append(row)

    issues: list[schemas.PreflightIssue] = []
    for members in groups.values():
        active = [member for member in members if not member.is_archived]
        first = members[0]
        subject_name = first.subject_name
        if len(active) < 2:
            issues.append(
                schemas.PreflightIssue(
                    code="JOINT_GROUP_INCOMPLETE",
                    severity="BLOCKER",
                    message=(
                        f"A aula conjunta de {subject_name} tem menos de duas turmas ativas. "
                        "Edite ou desfaça a junção."
                    ),
                    route=_joint_group_route(active or members),
                )
            )
            continue
        required_capacity = sum(member.class_size for member in active)
        subject_id = first.subject_id
        restricted = [
            specific_rooms[(member.class_id, subject_id)]
            for member in active
            if (member.class_id, subject_id) in specific_rooms
        ]
        allowed_room_ids = None
        if restricted:
            allowed = set(restricted[0])
            for room_ids in restricted[1:]:
                allowed &= set(room_ids)
            allowed_room_ids = allowed
        eligibility = assess_room_eligibility(
            rooms,
            required_room_type=first.required_room_type.value,
            required_capacity=required_capacity,
            allowed_room_ids=allowed_room_ids,
        )
        if eligibility.reason is None:
            continue
        issues.append(
            schemas.PreflightIssue(
                code="JOINT_ROOM_CAPACITY",
                severity="BLOCKER",
                message=_joint_room_message(
                    subject_name,
                    [member.class_name for member in active],
                    first.required_room_type.value,
                    required_capacity,
                ),
                route="/rooms",
            )
        )
    return issues


def _joint_group_route(members) -> str:
    if not members:
        return "/courses"
    member = members[0]
    return f"/courses/{member.course_id}/classes/{member.class_id}/subjects"


class PreflightService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def evaluate(
        self,
        *,
        organization_id: int,
        school_year_id: int | None = None,
        strategy: models.ScheduleGenerationStrategy = models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
        resolve_fingerprint: bool = True,
    ) -> schemas.PreflightReport:
        issues: list[schemas.PreflightIssue] = []

        if school_year_id is None:
            active_school_year = await SchedulerStateService(self.db).get_active_school_year(
                organization_id
            )
            school_year_id = active_school_year.id if active_school_year is not None else None
        if school_year_id is None:
            issues.append(
                schemas.PreflightIssue(
                    code="ACTIVE_SCHOOL_YEAR_REQUIRED",
                    severity="BLOCKER",
                    message="Defina o ano letivo ativo antes de gerar.",
                    route=CONFIG_ROUTE,
                )
            )

        org_settings = await _get_latest_settings_with_dates(self.db, organization_id)
        if org_settings is None:
            issues.append(
                schemas.PreflightIssue(
                    code="MISSING_CALENDAR",
                    severity="BLOCKER",
                    message="Datas do ano letivo não configuradas.",
                    route=CONFIG_ROUTE,
                )
            )

        # Resolve the visible grid once: it answers both "is there a grid?" and
        # the teacher/class availability checks below.
        resolved_grid = await grid_version_service.resolve_grid(
            self.db,
            organization_id,
            await grid_version_service.school_today(self.db, organization_id),
        )
        timeslot_ids = {slot.id for slot in resolved_grid.blocks}
        if not timeslot_ids:
            issues.append(
                schemas.PreflightIssue(
                    code="MISSING_TIMESLOTS",
                    severity="BLOCKER",
                    message="Nenhum bloco de horário configurado.",
                    route=CONFIG_ROUTE,
                )
            )

        teacher_count = (
            await self.db.scalar(
                sa_select(func.count(models.Teacher.id))
                .join(
                    models.OrganizationMembership,
                    models.OrganizationMembership.id == models.Teacher.organization_membership_id,
                )
                .where(
                    models.Teacher.organization_id == organization_id,
                    models.OrganizationMembership.organization_id == organization_id,
                    models.OrganizationMembership.lifecycle_status
                    == models.MembershipLifecycleStatus.active,
                    models.OrganizationMembership.can_teach.is_(True),
                )
            )
            or 0
        )
        if teacher_count == 0:
            issues.append(
                schemas.PreflightIssue(
                    code="MISSING_TEACHERS",
                    severity="BLOCKER",
                    message="Nenhum professor registado.",
                    route="/members",
                )
            )

        class_count = (
            await self.db.scalar(
                sa_select(func.count(models.Class.id)).where(
                    models.Class.organization_id == organization_id,
                    models.Class.is_archived.is_(False),
                )
            )
            or 0
        )
        if class_count == 0:
            issues.append(
                schemas.PreflightIssue(
                    code="MISSING_CLASSES",
                    severity="BLOCKER",
                    message="Nenhuma turma ativa registada.",
                    route="/courses",
                )
            )

        room_count = (
            await self.db.scalar(
                sa_select(func.count(models.Room.id)).where(
                    models.Room.organization_id == organization_id
                )
            )
            or 0
        )
        if room_count == 0:
            issues.append(
                schemas.PreflightIssue(
                    code="MISSING_ROOMS",
                    severity="BLOCKER",
                    message="Nenhuma sala configurada.",
                    route="/rooms",
                )
            )

        class_subject_count, lesson_count = await _get_generation_workload_counts(
            self.db, organization_id
        )
        allocations_ready = (class_subject_count > 0) or (lesson_count > 0)
        if not allocations_ready:
            issues.append(
                schemas.PreflightIssue(
                    code="MISSING_ALLOCATIONS",
                    severity="BLOCKER",
                    message="Nenhuma disciplina atribuída a turmas/professores.",
                    route="/courses",
                )
            )
        else:
            subject_ids = await _collect_generation_subject_ids(self.db, organization_id)
            subject_errors = await _validate_subject_requirements(
                self.db, organization_id, subject_ids
            )
            for s_err in subject_errors:
                issues.append(
                    schemas.PreflightIssue(
                        code="INVALID_SUBJECT_REQUIREMENTS",
                        severity="BLOCKER",
                        message=s_err,
                        route="/subjects",
                    )
                )

            issues.extend(await _validate_room_requirements(self.db, organization_id))

            # One row per live link drives both assignment blockers: an invalid
            # teacher and a class/subject link with no selected module. Keeping
            # both in a single statement preserves the dashboard query budget.
            teacher_invalid = or_(
                models.ClassSubjectLink.teacher_id.is_(None),
                models.Teacher.id.is_(None),
                models.OrganizationMembership.id.is_(None),
                models.Teacher.organization_id != organization_id,
                models.OrganizationMembership.organization_id != organization_id,
                models.OrganizationMembership.lifecycle_status
                != models.MembershipLifecycleStatus.active,
                models.OrganizationMembership.can_teach.is_(False),
                ~sa_select(1)
                .select_from(models.teacher_subject_link)
                .where(
                    models.teacher_subject_link.c.organization_id == organization_id,
                    models.teacher_subject_link.c.teacher_id == models.ClassSubjectLink.teacher_id,
                    models.teacher_subject_link.c.subject_id == models.ClassSubjectLink.subject_id,
                )
                .exists(),
            )
            has_selected_module = (
                sa_select(1)
                .select_from(models.class_subject_module)
                .where(
                    models.class_subject_module.c.organization_id == organization_id,
                    models.class_subject_module.c.class_subject_link_id
                    == models.ClassSubjectLink.id,
                )
                .exists()
            )
            assignment_rows = (
                await self.db.execute(
                    sa_select(
                        models.Class.course_id,
                        models.Class.id.label("class_id"),
                        models.Class.name.label("class_name"),
                        models.Subject.name.label("subject_name"),
                        models.Teacher.name.label("teacher_name"),
                        teacher_invalid.label("teacher_invalid"),
                        has_selected_module.label("has_selected_module"),
                    )
                    .select_from(models.ClassSubjectLink)
                    .join(models.Class, models.Class.id == models.ClassSubjectLink.class_id)
                    .join(models.Subject, models.Subject.id == models.ClassSubjectLink.subject_id)
                    .outerjoin(
                        models.Teacher,
                        and_(
                            models.Teacher.id == models.ClassSubjectLink.teacher_id,
                            models.Teacher.organization_id == organization_id,
                        ),
                    )
                    .outerjoin(
                        models.OrganizationMembership,
                        and_(
                            models.OrganizationMembership.id
                            == models.Teacher.organization_membership_id,
                            models.OrganizationMembership.organization_id == organization_id,
                        ),
                    )
                    .where(
                        models.ClassSubjectLink.organization_id == organization_id,
                        models.Class.organization_id == organization_id,
                        models.Subject.organization_id == organization_id,
                        models.Class.is_archived.is_(False),
                        models.ClassSubjectLink.grade_level == models.Class.grade_level,
                    )
                    .order_by(models.Class.name, models.Subject.name)
                )
            ).all()

            for row in assignment_rows:
                route = f"/courses/{row.course_id}/classes/{row.class_id}/subjects"
                if row.teacher_invalid:
                    if row.teacher_name is None:
                        message = (
                            f"Atribuição inválida: a turma {row.class_name} "
                            f"({row.subject_name}) não tem professor atribuído."
                        )
                    else:
                        message = (
                            f"Atribuição inválida: o professor {row.teacher_name} na turma "
                            f"{row.class_name} ({row.subject_name}) não está ativo ou não "
                            "tem qualificação na disciplina."
                        )
                    issues.append(
                        schemas.PreflightIssue(
                            code="INVALID_TEACHER_ASSIGNMENT",
                            severity="BLOCKER",
                            message=message,
                            route=route,
                        )
                    )
                if not row.has_selected_module:
                    issues.append(
                        schemas.PreflightIssue(
                            code="CLASS_SUBJECT_WITHOUT_MODULES",
                            severity="BLOCKER",
                            message=(
                                f"A turma {row.class_name} tem a disciplina "
                                f"{row.subject_name} sem módulos selecionados. Remova a "
                                "disciplina ou selecione pelo menos um módulo."
                            ),
                            route=route,
                        )
                    )

        pending_conditions = [
            SchedulerProposalV1.organization_id == organization_id,
            SchedulerProposalV1.status == "PENDING",
        ]
        if school_year_id is not None:
            pending_conditions.append(SchedulerProposalV1.school_year_id == school_year_id)
        has_pending = (
            await self.db.scalar(
                sa_select(func.count(SchedulerProposalV1.id)).where(*pending_conditions)
            )
            or 0
        )
        if has_pending > 0:
            issues.append(
                schemas.PreflightIssue(
                    code="PENDING_DRAFT",
                    severity="WARNING",
                    message="Existe um rascunho de horário pendente de aprovação.",
                    route="/schedules",
                )
            )

        teacher_ids = await _collect_generation_teacher_ids(self.db, organization_id)
        teacher_error = await _validate_teacher_availabilities(
            self.db,
            organization_id,
            teacher_ids,
            timeslot_ids,
        )
        if teacher_error:
            issues.append(
                schemas.PreflightIssue(
                    code="MISSING_TEACHER_AVAILABILITY",
                    severity="BLOCKER",
                    message=teacher_error,
                    route="/members",
                )
            )

        issues.extend(await _validate_class_availability(self.db, organization_id, timeslot_ids))

        if (
            strategy
            in (
                models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR,
                models.ScheduleGenerationStrategy.GRID_CHANGE,
            )
            and org_settings is not None
            and school_year_id is not None
            and timeslot_ids
        ):
            policy = await SchedulerFingerprintService(self.db).repair_policy_snapshot(
                organization_id,
                school_year_id,
            )
            hard_end_date = org_settings.school_hard_end_date
            if hard_end_date is not None and hard_end_date < policy.editable_start_date:
                issues.append(
                    schemas.PreflightIssue(
                        code="REPAIR_WINDOW_INFEASIBLE",
                        severity="BLOCKER",
                        message=(
                            "Reparacao adaptativa bloqueada: nao existe horizonte fora da janela "
                            f"de estabilidade (até {policy.editable_start_date.isoformat()}) antes "
                            f"do hard end date ({hard_end_date.isoformat()})."
                        ),
                        route="/schedules",
                    )
                )

        has_blocker = any(i.severity == "BLOCKER" for i in issues)
        has_warning = any(i.severity == "WARNING" for i in issues)
        if has_blocker:
            status = "BLOCKED"
        elif has_warning:
            status = "READY_WITH_WARNINGS"
        else:
            status = "READY"

        fingerprint = None
        if school_year_id is not None and resolve_fingerprint:
            fp_result = await SchedulerFingerprintService(self.db).generation_input_fingerprint(
                organization_id=organization_id,
                school_year_id=school_year_id,
                strategy=strategy,
            )
            fingerprint = fp_result.value

        return schemas.PreflightReport(
            status=status,
            fingerprint=fingerprint,
            issues=issues,
        )
