import structlog
from sqlalchemy import and_, func, or_
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.services.availability_matrix_service import AvailabilityMatrixInspector
from app.services.scheduler_fingerprint_service import SchedulerFingerprintService
from app.services.scheduler_state_service import SchedulerStateService

logger = structlog.get_logger(__name__)


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
    class_subject_teacher_ids = {row[0] for row in class_subject_teacher_rows.all()}

    return class_subject_teacher_ids


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
    class_subject_ids = {row[0] for row in class_subject_subject_rows.all()}

    return class_subject_ids


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
        "Professores sem disponibilidade configurada: "
        f"{', '.join(missing_names)}. "
        "Configure em Professores > Disponibilidade."
    )


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

    room_exists = sa_select(models.Room.id).where(
        models.Room.organization_id == organization_id,
        models.Room.type == models.Subject.required_room_type,
        models.Room.capacity >= models.Class.size,
    )
    incompatible_rows = await db.execute(
        sa_select(models.Class.name, models.Subject.name, models.Class.size)
        .select_from(models.ClassSubjectLink)
        .join(models.Class, models.Class.id == models.ClassSubjectLink.class_id)
        .join(models.Subject, models.Subject.id == models.ClassSubjectLink.subject_id)
        .where(
            models.ClassSubjectLink.organization_id == organization_id,
            models.Class.organization_id == organization_id,
            models.Subject.organization_id == organization_id,
            models.Class.is_archived.is_(False),
            models.ClassSubjectLink.teacher_id.is_not(None),
            models.ClassSubjectLink.grade_level == models.Class.grade_level,
            models.ClassSubjectLink.subject_id.in_(subject_ids),
            ~room_exists.where(models.Room.organization_id == organization_id)
            .correlate(models.Class, models.Subject)
            .exists(),
        )
        .order_by(models.Class.name, models.Subject.name)
    )
    incompatible = incompatible_rows.all()
    if incompatible:
        errors.append(
            "Turmas sem sala compatível (tipo e lotação): "
            + ", ".join(
                f"{class_name} / {subject_name} ({size} lugares)"
                for class_name, subject_name, size in incompatible
            )
            + ". Adicione salas compatíveis em Salas."
        )

    return errors


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
                    route="/config",
                )
            )

        org_settings = await _get_latest_settings_with_dates(self.db, organization_id)
        if org_settings is None:
            issues.append(
                schemas.PreflightIssue(
                    code="MISSING_CALENDAR",
                    severity="BLOCKER",
                    message="Datas do ano letivo não configuradas.",
                    route="/config",
                )
            )

        ts_count = (
            await self.db.scalar(
                sa_select(func.count(models.Timeslot.id)).where(
                    models.Timeslot.organization_id == organization_id
                )
            )
            or 0
        )
        if ts_count == 0:
            issues.append(
                schemas.PreflightIssue(
                    code="MISSING_TIMESLOTS",
                    severity="BLOCKER",
                    message="Nenhum bloco de horário configurado.",
                    route="/config",
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

            invalid_assignment_rows = (
                await self.db.execute(
                    sa_select(
                        models.Class.course_id,
                        models.Class.id.label("class_id"),
                        models.Class.name.label("class_name"),
                        models.Subject.name.label("subject_name"),
                        models.Teacher.name.label("teacher_name"),
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
                        or_(
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
                                models.teacher_subject_link.c.teacher_id
                                == models.ClassSubjectLink.teacher_id,
                                models.teacher_subject_link.c.subject_id
                                == models.ClassSubjectLink.subject_id,
                            )
                            .exists(),
                        ),
                    )
                    .order_by(models.Class.name, models.Subject.name)
                )
            ).all()

            for inv in invalid_assignment_rows:
                if inv.teacher_name is None:
                    message = (
                        f"Atribuição inválida: a turma {inv.class_name} ({inv.subject_name}) "
                        "não tem professor atribuído."
                    )
                else:
                    message = (
                        f"Atribuição inválida: o professor {inv.teacher_name} na turma "
                        f"{inv.class_name} ({inv.subject_name}) não está ativo ou não tem "
                        "qualificação na disciplina."
                    )
                issues.append(
                    schemas.PreflightIssue(
                        code="INVALID_TEACHER_ASSIGNMENT",
                        severity="BLOCKER",
                        message=message,
                        route=f"/courses/{inv.course_id}/classes/{inv.class_id}/subjects",
                    )
                )

        pending_conditions = [
            models.ScheduleDraft.organization_id == organization_id,
            models.ScheduleDraft.draft_state == models.ScheduleDraftState.PENDING,
        ]
        if school_year_id is not None:
            pending_conditions.append(models.ScheduleDraft.school_year_id == school_year_id)
        has_pending = (
            await self.db.scalar(
                sa_select(func.count(models.ScheduleDraft.id)).where(*pending_conditions)
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
        timeslot_rows = await self.db.execute(
            sa_select(models.Timeslot.id).where(models.Timeslot.organization_id == organization_id)
        )
        timeslot_ids = set(timeslot_rows.scalars().all())
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

        if (
            strategy == models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR
            and org_settings is not None
            and school_year_id is not None
            and ts_count > 0
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
