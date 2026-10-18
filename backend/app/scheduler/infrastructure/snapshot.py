"""Build the immutable planning snapshot from persisted school data.

The builder is the only production reader that turns relational records into
domain values. It resolves the active school year, the joint room eligibility,
the executed ledger, the open debt, the published baseline and the physical
unavailability. It never writes and never consults a global clock: the caller
injects ``school_today`` and ``now_utc``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence, Set
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time
from types import MappingProxyType
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Row, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.scheduler.domain.calendar import (
    INTERNSHIP_FLOW_EVENT_TYPE,
    Period,
    blocked_dates_by_class,
    event_dates,
    grid_dates,
    is_physically_protected,
    normalize_period,
    protected_grid_dates,
)
from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    GridSlot,
    HomeRoom,
    LunchRule,
    PlanningSnapshot,
    ScheduledLesson,
    SchedulingStrategy,
    TeacherPresenceRule,
    Unavailability,
    UnavailableResource,
    split_consumed_lessons,
)
from app.scheduler.domain.constraint_policy import (
    SchoolConstraintPolicy,
    assess_room_eligibility,
)
from app.scheduler.domain.debt import RecoveryAllocation
from app.scheduler.domain.grid_versions import (
    GridVersionRef,
    select_effective_grid_version,
)
from app.scheduler.domain.projection import (
    FutureLesson,
    ModuleRequirement,
    ModuleSlice,
    project_module_slices,
)
from app.scheduler.domain.recovery import RecoveryPolicy
from app.scheduler.domain.serialization import payload_digest, period_to_dict, snapshot_to_dict
from app.scheduler.domain.teaching_units import (
    AssignmentPlan,
    JointGroupPlan,
    JointTeacherMismatch,
    TeachingUnitPlan,
    build_teaching_units,
)
from app.scheduler.infrastructure.models import (
    CurricularAssignment,
    CurricularRequirement,
    SchedulerLessonLogV1,
    SchedulerLessonSliceV1,
    SchedulerLessonV1,
    SchedulerRecoveryReservationV1,
    SchedulerVersionV1,
)
from app.scheduler.infrastructure.progress import load_open_debt, load_planning_requirements


class SnapshotConfigurationError(ValueError):
    """The persisted configuration cannot produce a valid planning snapshot."""

    def __init__(
        self,
        code: str,
        message: str,
        public_context: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.public_context = dict(public_context or {})


def recovery_policy(snapshot: PlanningSnapshot) -> RecoveryPolicy:
    """Explicit experimental policy; calibration is W11 work.

    The coefficients are versioned and stored with every proposal. They are not
    a silent production default: W11 either confirms or replaces this policy.
    """
    days = max(1, (snapshot.preferred_end_date - snapshot.origin).days)
    return RecoveryPolicy(
        version="v1-uncalibrated",
        daily_slopes=tuple(range(1, days + 1)),
        disruption_weight=1,
        move_cost=10,
        insert_cost=12,
        remove_cost=15,
        room_change_cost=3,
        urgency_horizon_days=10,
        urgency_slope=1,
        recurrence_penalty=1,
    )


@dataclass(frozen=True)
class SnapshotBundle:
    """Snapshot, concrete periods and the revisions observed while loading."""

    snapshot: PlanningSnapshot
    periods: tuple[Period, ...]
    base_version_id: int | None
    base_lesson_ids: Mapping[int, int]  # Stable domain identity -> database lesson ID.
    input_revision: int
    planning_revision: int
    digest: str
    policy: RecoveryPolicy | None
    # Teaching-unit keys and their accounting (per class) assignment ids. The
    # domain ``assignment_id`` is a unit id; persistence maps it back to the
    # real per-class assignment FKs through ``unit_accounting`` (WBS 3.2.1/3.8.1).
    unit_keys: Mapping[str, int] = field(default_factory=dict)
    unit_accounting: Mapping[int, tuple[int, ...]] = field(default_factory=dict)
    # Accounting (per-class) assignment id -> class id, and per logical lesson
    # the database row id of each class sibling. Persistence maps every written
    # row back to a real assignment FK and links each sister to its own source.
    accounting_classes: Mapping[int, int] = field(default_factory=dict)
    base_lesson_classes: Mapping[int, Mapping[int, int]] = field(default_factory=dict)

    @property
    def baseline(self) -> CandidateSchedule | None:
        if self.base_version_id is None:
            return None
        return CandidateSchedule(self.snapshot.baseline_lessons)


@dataclass(frozen=True)
class _CalendarData:
    grid_slots: tuple[GridSlot, ...]
    periods: tuple[Period, ...]
    blocked_dates: frozenset[date]
    class_blocked_dates: Mapping[int, frozenset[date]]
    periods_by_signature: Mapping[tuple[int, time, time], tuple[Period, ...]]
    periods_by_date: Mapping[date, tuple[Period, ...]]
    signature_by_timeslot: Mapping[int, tuple[int, time, time]]
    timeslots_by_signature: Mapping[tuple[int, time, time], frozenset[int]]


async def load_snapshot(
    db: AsyncSession,
    organization_id: int,
    *,
    strategy: SchedulingStrategy,
    now_utc: datetime,
    school_year_id: int | None = None,
    grid_version_id: int | None = None,
) -> SnapshotBundle:
    """Read the current school state into a planning snapshot.

    ``grid_version_id`` pins a pending grid version (grid-change proposals);
    without it the active version for the current school date applies.
    """
    if type(strategy) is not SchedulingStrategy:
        raise SnapshotConfigurationError("INVALID_STRATEGY", "Estratégia de geração inválida.")
    if type(now_utc) is not datetime or now_utc.utcoffset() is None:
        raise SnapshotConfigurationError("INVALID_CLOCK", "Relógio de planeamento inválido.")
    year = await db.scalar(
        select(models.SchedulerSchoolYear).where(
            models.SchedulerSchoolYear.organization_id == organization_id,
            (
                models.SchedulerSchoolYear.id == school_year_id
                if school_year_id is not None
                else models.SchedulerSchoolYear.is_active.is_(True)
            ),
        )
    )
    if year is None:
        raise SnapshotConfigurationError(
            "SCHOOL_YEAR_NOT_CONFIGURED", "O ano letivo ativo não está configurado."
        )
    if year.preferred_end_date is None:
        raise SnapshotConfigurationError(
            "PREFERRED_END_DATE_NOT_CONFIGURED",
            "A data preferencial de conclusão do ano letivo não está definida.",
        )
    state = await db.scalar(
        select(models.SchedulerSchoolYearState).where(
            models.SchedulerSchoolYearState.organization_id == organization_id,
            models.SchedulerSchoolYearState.school_year_id == year.id,
        )
    )
    if state is None:
        raise SnapshotConfigurationError(
            "SCHOOL_YEAR_NOT_CONFIGURED", "O estado de planeamento do ano letivo não existe."
        )
    try:
        zone = ZoneInfo(year.timezone)
    except (ZoneInfoNotFoundError, TypeError, ValueError) as exc:
        raise SnapshotConfigurationError(
            "INVALID_TIMEZONE", "O fuso horário da escola é inválido."
        ) from exc

    calendar = await _load_calendar(
        db,
        organization_id,
        year,
        strategy=strategy,
        school_today=now_utc.astimezone(zone).date(),
        grid_version_id=grid_version_id,
    )
    assignments, requirements, executed = await _load_assignments(db, organization_id, year.id)
    constraints = await _load_constraint_policy(db, organization_id)
    active_version = await db.scalar(
        select(SchedulerVersionV1).where(
            SchedulerVersionV1.organization_id == organization_id,
            SchedulerVersionV1.school_year_id == year.id,
            SchedulerVersionV1.status == "ACTIVE",
        )
    )
    if strategy is SchedulingStrategy.ADAPTIVE_RECOVERY and active_version is None:
        raise SnapshotConfigurationError(
            "ACTIVE_VERSION_REQUIRED", "Não existe horário publicado para reparar."
        )
    if (
        strategy is SchedulingStrategy.COMPLETE_GENERATION
        and active_version is not None
        and grid_version_id is None
    ):
        raise SnapshotConfigurationError(
            "ACTIVE_VERSION_PUBLISHED",
            "Já existe um horário publicado. A primeira geração não o pode substituir.",
        )
    operational_unavailable, operational_demand = await _load_operational_reservations(
        db, organization_id, year.id, year.timezone
    )
    executed = _apply_operational_demand(executed, requirements, operational_demand)
    groups = await _load_joint_groups(
        db, organization_id, _assignment_ids_by_class_subject(assignments)
    )
    published_unit_keys = await _load_published_unit_keys(
        db, organization_id, year.id, active_version
    )
    domain_assignments, unit_plan, executed, home_rooms = await _build_assignments(
        db,
        organization_id,
        assignments,
        requirements,
        executed,
        groups,
        published_unit_keys,
        constraints=constraints,
    )
    unit_accounting = {
        unit_id: tuple(payers) for unit_id, payers in unit_plan.accounting_assignments.items()
    }
    unavailable, soft_unavailable = await _load_unavailability(
        db,
        organization_id,
        constraints=constraints,
        calendar=calendar,
    )
    unavailable = (*unavailable, *operational_unavailable)
    open_debt, raw_claim_assignments = await load_open_debt(
        db, organization_id, [row.id for row in assignments]
    )
    joint_mode = any(len(row.class_ids) > 1 for row in domain_assignments)
    claim_assignments, claim_classes = _map_claim_units(
        unit_plan, assignments, open_debt, raw_claim_assignments
    )
    school_today = now_utc.astimezone(zone).date()
    lunch_rule = await _load_lunch_rule(db, organization_id)
    teacher_presence = await _load_teacher_presence(
        db, organization_id, {row.teacher_id for row in domain_assignments}
    )
    # The stability window protects only a schedule that is already published.
    # A first generation has no published lessons to preserve, so it must not
    # lose future days to a window that protects nothing.
    protected_dates = (
        _stability_protected_dates(
            year, calendar, school_today, await _stability_window(db, organization_id)
        )
        if active_version is not None
        else frozenset()
    )
    class_ids_by_unit = {unit.unit_id: unit.class_ids for unit in unit_plan.units}
    accounting_classes = {row.id: row.class_id for row in assignments}
    (
        baseline_lessons,
        protected_lessons,
        reservations,
        base_lesson_ids,
        history_unavailable,
        base_lesson_classes,
    ) = await _load_baseline(
        db,
        organization_id,
        year.id,
        zone,
        active_version=active_version,
        now_utc=now_utc,
        protected_dates=protected_dates,
        assignments={row.assignment_id: row for row in domain_assignments},
        executed=executed,
        unit_keys=unit_plan.unit_ids,
        class_ids_by_unit=class_ids_by_unit,
        accounting_classes=accounting_classes,
    )
    try:
        snapshot = PlanningSnapshot(
            strategy=strategy,
            origin=year.start_date,
            preferred_end_date=year.preferred_end_date,
            hard_end_date=year.hard_end_date,
            timezone_name=year.timezone,
            grid_slots=calendar.grid_slots,
            assignments=domain_assignments,
            executed_minutes=executed,
            blocked_dates=calendar.blocked_dates,
            class_blocked_dates=calendar.class_blocked_dates,
            unavailable=(*unavailable, *history_unavailable),
            soft_unavailable=soft_unavailable,
            protected_lessons=protected_lessons,
            baseline_lessons=baseline_lessons,
            protected_dates=protected_dates,
            now_utc=now_utc,
            reservations=tuple(row for row in reservations if row.claim_id in open_debt),
            open_debt_minutes=open_debt,
            claim_assignments=claim_assignments,
            claim_classes=claim_classes if joint_mode else {},
            precedences=unit_plan.precedences,
            active_version_id=active_version.id if active_version is not None else None,
            lunch_rule=lunch_rule,
            teacher_presence=teacher_presence,
            home_rooms=home_rooms,
            reserved_lesson_ids=frozenset(base_lesson_ids).difference(
                lesson.lesson_id for lesson in baseline_lessons
            ),
        )
    except ValueError as exc:
        raise SnapshotConfigurationError(
            "INVALID_PROTECTED_STATE",
            "O horário publicado é inconsistente com o progresso registado.",
        ) from exc
    digest_payload = snapshot_to_dict(snapshot)
    # The clock and the derived windows are search parameters, not data: the
    # digest must stay stable between queueing and claiming the same revisions.
    digest_payload.pop("now_utc", None)
    digest_payload.pop("protected_dates", None)
    digest_payload.pop("protected_lessons", None)
    digest = payload_digest(
        {
            "snapshot": digest_payload,
            "periods": sorted(period_to_dict(period) for period in calendar.periods),
            "base_version_id": active_version.id if active_version is not None else None,
        }
    )
    policy = recovery_policy(snapshot) if strategy is SchedulingStrategy.ADAPTIVE_RECOVERY else None
    return SnapshotBundle(
        snapshot=snapshot,
        periods=calendar.periods,
        base_version_id=active_version.id if active_version is not None else None,
        base_lesson_ids=base_lesson_ids,
        input_revision=state.input_revision,
        planning_revision=state.planning_revision,
        digest=digest,
        policy=policy,
        unit_keys=MappingProxyType(dict(unit_plan.unit_ids)),
        unit_accounting=MappingProxyType(dict(unit_accounting)),
        accounting_classes=MappingProxyType(dict(accounting_classes)),
        base_lesson_classes=MappingProxyType(
            {
                identity: MappingProxyType(dict(rows))
                for identity, rows in base_lesson_classes.items()
            }
        ),
    )


async def _load_operational_reservations(
    db: AsyncSession,
    organization_id: int,
    school_year_id: int,
    timezone_name: str,
) -> tuple[list[Unavailability], dict[int, dict[int, int]]]:
    """Active v1 substitute blocks as physical reservations and planned demand.

    A planned substitution occupies the teacher, the room and the class in its
    period. Its minutes consume the substitute subject demand without entering
    the execution ledger.
    """
    rows = (
        await db.execute(
            select(
                models.OperationalScheduleBlock,
                models.Timeslot.start_time,
                models.Timeslot.end_time,
                SchedulerLessonV1.credit_minutes,
            )
            .join(
                SchedulerLessonLogV1,
                (
                    SchedulerLessonLogV1.organization_id
                    == models.OperationalScheduleBlock.organization_id
                )
                & (
                    SchedulerLessonLogV1.id
                    == models.OperationalScheduleBlock.source_v1_lesson_log_id
                ),
            )
            .join(
                SchedulerLessonV1,
                (SchedulerLessonV1.organization_id == SchedulerLessonLogV1.organization_id)
                & (SchedulerLessonV1.school_year_id == SchedulerLessonLogV1.school_year_id)
                & (SchedulerLessonV1.id == SchedulerLessonLogV1.lesson_id),
            )
            .join(
                models.Timeslot,
                (models.Timeslot.organization_id == models.OperationalScheduleBlock.organization_id)
                & (models.Timeslot.id == models.OperationalScheduleBlock.timeslot_id),
            )
            .where(
                models.OperationalScheduleBlock.organization_id == organization_id,
                models.OperationalScheduleBlock.origin_kind == models.OperationalBlockOrigin.V1,
                models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
                SchedulerLessonLogV1.school_year_id == school_year_id,
            )
        )
    ).all()
    unavailable: list[Unavailability] = []
    demand: dict[int, dict[int, int]] = defaultdict(dict)
    for block, start_time, end_time, credit_minutes in rows:
        period = normalize_period(block.date, start_time, end_time, timezone_name)
        for resource_type, resource_id in (
            (UnavailableResource.TEACHER, block.teacher_id),
            (UnavailableResource.ROOM, block.room_id),
            (UnavailableResource.CLASS, block.class_id),
        ):
            if resource_id:
                unavailable.append(Unavailability(resource_type, int(resource_id), period))
        if block.execution_status == models.OperationalBlockExecutionStatus.COMPLETED:
            continue
        assignment_id = block.substitute_curricular_assignment_id
        if assignment_id is None or block.module_id is None:
            continue
        demand[assignment_id][block.module_id] = (
            demand[assignment_id].get(block.module_id, 0) + credit_minutes
        )
    return unavailable, {key: dict(value) for key, value in demand.items()}


def _apply_operational_demand(
    executed: Mapping[int, Mapping[int, int]],
    requirements: Mapping[int, tuple[ModuleRequirement, ...]],
    demand: Mapping[int, Mapping[int, int]],
) -> dict[int, dict[int, int]]:
    """Fold planned substitution minutes into the consumed demand.

    The frontier is capped per module by the curricular requirement: an
    out-of-date plan can never push the snapshot outside its required minutes.
    ponytail: per-module cap; upgrade to a sequential frontier if a block ever
    needs capacity from several modules.
    """
    result: dict[int, dict[int, int]] = {
        assignment_id: dict(modules) for assignment_id, modules in executed.items()
    }
    for assignment_id, modules in demand.items():
        required_modules = requirements.get(assignment_id)
        if not required_modules:
            continue
        required = {module.module_id: module.required_minutes for module in required_modules}
        for module_id, minutes in modules.items():
            if module_id not in required:
                continue
            current = result.setdefault(assignment_id, {}).get(module_id, 0)
            capacity = required[module_id] - current
            if capacity <= 0:
                continue
            result[assignment_id][module_id] = current + min(minutes, capacity)
    return result


async def _load_lunch_rule(db: AsyncSession, organization_id: int) -> LunchRule | None:
    """Read the mandatory lunch rule, or fail loudly on a partial configuration.

    A school without a grid-settings row never configured a lunch window, so the
    rule is absent. A row with some but not all fields is an incomplete
    configuration and is reported instead of silently ignored.
    """
    settings = await db.scalar(
        select(models.OrganizationGridSettings).where(
            models.OrganizationGridSettings.organization_id == organization_id
        )
    )
    if settings is None:
        return None
    values = (
        settings.lunch_window_start,
        settings.lunch_window_end,
        settings.lunch_min_duration_minutes,
    )
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise SnapshotConfigurationError(
            "LUNCH_CONFIGURATION_INCOMPLETE",
            "A configuração de almoço da escola está incompleta.",
        )
    try:
        return LunchRule(values[0], values[1], values[2])
    except ValueError as exc:
        raise SnapshotConfigurationError(
            "INVALID_LUNCH_RULE", "A configuração de almoço da escola é inválida."
        ) from exc


async def _load_teacher_presence(
    db: AsyncSession,
    organization_id: int,
    teacher_ids: Set[int],
) -> tuple[TeacherPresenceRule, ...]:
    """Read the non-default presence rules of the assignment teachers.

    Uses the same filter as the readiness fingerprint (I05): an active member
    with teaching capability, present in the assignments. Only rules that differ
    from the default travel in the snapshot, ordered by teacher id (I04).
    """
    if not teacher_ids:
        return ()
    rows = (
        await db.execute(
            select(
                models.Teacher.id,
                models.Teacher.lunch_required,
                models.Teacher.minimum_presence_hours,
                models.Teacher.maximum_presence_gap_hours,
            )
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
                models.Teacher.id.in_(teacher_ids),
                or_(
                    models.Teacher.lunch_required.is_(False),
                    models.Teacher.minimum_presence_hours.is_not(None),
                ),
            )
            .order_by(models.Teacher.id)
        )
    ).all()
    return tuple(
        TeacherPresenceRule(
            teacher_id=row.id,
            lunch_required=row.lunch_required,
            minimum_minutes=(
                None if row.minimum_presence_hours is None else row.minimum_presence_hours * 60
            ),
            max_gap_minutes=(
                None
                if row.maximum_presence_gap_hours is None
                else row.maximum_presence_gap_hours * 60
            ),
        )
        for row in rows
    )


async def _stability_window(db: AsyncSession, organization_id: int) -> int:
    settings = await db.scalar(
        select(models.OrganizationSettings).where(
            models.OrganizationSettings.organization_id == organization_id
        )
    )
    if settings is None or settings.repair_stability_window_days is None:
        return 0
    if settings.repair_stability_window_days < 0:
        raise SnapshotConfigurationError(
            "INVALID_STABILITY_WINDOW", "A janela de estabilidade é inválida."
        )
    return settings.repair_stability_window_days


def _stability_protected_dates(
    year: models.SchedulerSchoolYear,
    calendar: _CalendarData,
    school_today: date,
    window: int,
) -> frozenset[date]:
    dates = grid_dates(
        year.start_date,
        year.hard_end_date,
        {slot.day_of_week for slot in calendar.grid_slots},
    )
    return frozenset(protected_grid_dates(dates, school_today, window))


async def _load_calendar(
    db: AsyncSession,
    organization_id: int,
    year: models.SchedulerSchoolYear,
    *,
    strategy: SchedulingStrategy,
    school_today: date,
    grid_version_id: int | None = None,
) -> _CalendarData:
    timeslots = await _resolve_grid_blocks(
        db,
        organization_id,
        school_today=school_today,
        pinned_version_id=grid_version_id,
    )
    if not timeslots:
        raise SnapshotConfigurationError(
            "GRID_NOT_CONFIGURED", "A grelha semanal da escola não está configurada."
        )
    _reject_overlapping_slots(timeslots)
    slots = tuple(GridSlot(row.day_of_week, row.start_time, row.end_time) for row in timeslots)
    blocked, class_blocked = await _load_blocked_dates(db, organization_id)
    limit = (
        year.preferred_end_date
        if strategy is SchedulingStrategy.COMPLETE_GENERATION
        else year.hard_end_date
    )
    if limit is None:
        raise SnapshotConfigurationError(
            "PREFERRED_END_DATE_NOT_CONFIGURED",
            "A data preferencial de conclusão do ano letivo não está definida.",
        )
    dates = grid_dates(year.start_date, limit, {slot.day_of_week for slot in slots})
    periods = [
        normalize_period(day, slot.start_local, slot.end_local, year.timezone)
        for day in dates
        if day not in blocked
        for slot in slots
    ]
    by_signature: dict[tuple[int, time, time], list[Period]] = defaultdict(list)
    by_date: dict[date, list[Period]] = defaultdict(list)
    signature_by_timeslot: dict[int, tuple[int, time, time]] = {}
    timeslots_by_signature: dict[tuple[int, time, time], set[int]] = defaultdict(set)
    for row in timeslots:
        signature = (row.day_of_week, row.start_time, row.end_time)
        signature_by_timeslot[row.id] = signature
        timeslots_by_signature[signature].add(row.id)
    for period in periods:
        signature = (period.school_date.weekday(), period.start_local, period.end_local)
        by_signature[signature].append(period)
        by_date[period.school_date].append(period)
    return _CalendarData(
        grid_slots=slots,
        periods=tuple(periods),
        blocked_dates=blocked,
        class_blocked_dates=class_blocked,
        periods_by_signature=MappingProxyType(
            {key: tuple(value) for key, value in by_signature.items()}
        ),
        periods_by_date=MappingProxyType({key: tuple(value) for key, value in by_date.items()}),
        signature_by_timeslot=MappingProxyType(signature_by_timeslot),
        timeslots_by_signature=MappingProxyType(
            {key: frozenset(value) for key, value in timeslots_by_signature.items()}
        ),
    )


async def _resolve_grid_blocks(
    db: AsyncSession,
    organization_id: int,
    *,
    school_today: date,
    pinned_version_id: int | None,
) -> list[models.Timeslot]:
    """Resolve the weekly blocks of the pinned pending version or the active one.

    A pinned version that is no longer pending invalidates the snapshot: the
    proposal behind it was rejected or activated elsewhere. Without a pin, the
    active version effective on the school date applies, falling back to the
    unversioned legacy blocks.
    """
    if pinned_version_id is not None:
        version = await db.scalar(
            select(models.GridVersion).where(
                models.GridVersion.organization_id == organization_id,
                models.GridVersion.id == pinned_version_id,
            )
        )
        if version is None or version.state != models.GridVersionState.PENDING:
            raise SnapshotConfigurationError(
                "GRID_VERSION_CHANGED",
                "A proposta de alteração da grelha já não está pendente.",
            )
        blocks = await _version_blocks(db, organization_id, version.id)
        if not blocks:
            raise SnapshotConfigurationError(
                "GRID_VERSION_EMPTY", "A grelha proposta não tem períodos definidos."
            )
        return blocks
    versions = (
        await db.scalars(
            select(models.GridVersion)
            .where(models.GridVersion.organization_id == organization_id)
            .order_by(models.GridVersion.effective_date, models.GridVersion.id)
        )
    ).all()
    references = [
        GridVersionRef(
            id=version.id,
            effective_date=version.effective_date,
            state=version.state.value,
        )
        for version in versions
    ]
    selected_id = select_effective_grid_version(references, school_today)
    if selected_id is not None:
        blocks = await _version_blocks(db, organization_id, selected_id)
        if blocks:
            return blocks
    return await _unversioned_blocks(db, organization_id)


async def _version_blocks(
    db: AsyncSession, organization_id: int, version_id: int
) -> list[models.Timeslot]:
    return list(
        (
            await db.scalars(
                select(models.Timeslot)
                .where(
                    models.Timeslot.organization_id == organization_id,
                    models.Timeslot.grid_version_id == version_id,
                )
                .order_by(models.Timeslot.day_of_week, models.Timeslot.start_time)
            )
        ).all()
    )


async def _unversioned_blocks(db: AsyncSession, organization_id: int) -> list[models.Timeslot]:
    return list(
        (
            await db.scalars(
                select(models.Timeslot)
                .where(
                    models.Timeslot.organization_id == organization_id,
                    models.Timeslot.grid_version_id.is_(None),
                )
                .order_by(models.Timeslot.day_of_week, models.Timeslot.start_time)
            )
        ).all()
    )


def _reject_overlapping_slots(timeslots: Sequence[models.Timeslot]) -> None:
    by_day: dict[int, list[tuple[time, time]]] = defaultdict(list)
    for row in timeslots:
        by_day[row.day_of_week].append((row.start_time, row.end_time))
    for weekday, intervals in by_day.items():
        ordered = sorted(intervals)
        for (_, first_end), (second_start, _) in zip(ordered, ordered[1:], strict=False):
            if second_start < first_end:
                raise SnapshotConfigurationError(
                    "OVERLAPPING_GRID_SLOTS",
                    f"A grelha de {weekday} tem períodos sobrepostos.",
                )


async def _load_blocked_dates(
    db: AsyncSession, organization_id: int
) -> tuple[frozenset[date], Mapping[int, frozenset[date]]]:
    """Split calendar events into school-wide blocks and per-class flow blocks."""
    events = (
        await db.scalars(
            select(models.SchoolCalendarEvent).where(
                models.SchoolCalendarEvent.organization_id == organization_id
            )
        )
    ).all()
    rows: list[dict] = []
    for event in events:
        if event.end_date < event.start_date:
            raise SnapshotConfigurationError(
                "INVALID_CALENDAR_EVENT",
                "Existe um evento de calendário com datas inválidas.",
            )
        rows.append(
            {
                "event_type": event.event_type,
                "start_date": event.start_date,
                "end_date": event.end_date,
                "class_ids": tuple(event.class_ids or ()),
            }
        )
    blocked: set[date] = set()
    flows: list[dict] = []
    for row in rows:
        if str(getattr(row["event_type"], "value", row["event_type"])) == (
            INTERNSHIP_FLOW_EVENT_TYPE
        ):
            flows.append(row)
        else:
            blocked.update(event_dates(row))
    flow_classes = sorted({class_id for row in flows for class_id in row["class_ids"]})
    by_class = blocked_dates_by_class(flows, flow_classes)
    return (
        frozenset(blocked),
        MappingProxyType(
            {class_id: frozenset(days) for class_id, days in by_class.items() if days}
        ),
    )


async def _load_assignments(
    db: AsyncSession,
    organization_id: int,
    school_year_id: int,
) -> tuple[
    list[CurricularAssignment],
    dict[int, tuple[ModuleRequirement, ...]],
    dict[int, dict[int, int]],
]:
    assignments = (
        await db.scalars(
            select(CurricularAssignment)
            .where(
                CurricularAssignment.organization_id == organization_id,
                CurricularAssignment.school_year_id == school_year_id,
            )
            .order_by(CurricularAssignment.id)
        )
    ).all()
    if not assignments:
        raise SnapshotConfigurationError(
            "NO_CURRICULAR_ASSIGNMENTS",
            "Não existem atribuições curriculares configuradas para o ano letivo.",
        )
    requirement_rows = (
        await db.execute(
            select(CurricularRequirement).where(
                CurricularRequirement.organization_id == organization_id,
                CurricularRequirement.assignment_id.in_([row.id for row in assignments]),
            )
        )
    ).scalars()
    requirements: dict[int, list[ModuleRequirement]] = defaultdict(list)
    for row in requirement_rows:
        requirements[row.assignment_id].append(
            ModuleRequirement(row.module_id, row.sequence, row.required_minutes)
        )
    for assignment in assignments:
        modules = requirements.get(assignment.id)
        if not modules:
            raise SnapshotConfigurationError(
                "ASSIGNMENT_WITHOUT_REQUIREMENTS",
                "Existem disciplinas atribuídas sem módulos com minutos definidos.",
            )
    # Planning view: a retired module is closed at its executed minutes and
    # never receives new credit. The executed minutes cover only the modules
    # that remain in the planning order.
    planning, executed = await load_planning_requirements(
        db, organization_id, [row.id for row in assignments]
    )
    return list(assignments), planning, executed


def _assignment_ids_by_class_subject(
    assignments: Sequence[CurricularAssignment],
) -> dict[tuple[int, int], int]:
    return {(row.class_id, row.subject_id): row.id for row in assignments}


async def _load_joint_groups(
    db: AsyncSession,
    organization_id: int,
    assignment_id_by_key: Mapping[tuple[int, int], int],
) -> tuple[JointGroupPlan, ...]:
    """Active joint groups over the current curricular projection (WBS 3.2.1)."""
    groups = (
        await db.execute(
            select(models.JointLessonGroup.id, models.JointLessonGroup.subject_id)
            .where(models.JointLessonGroup.organization_id == organization_id)
            .order_by(models.JointLessonGroup.id)
        )
    ).all()
    if not groups:
        return ()
    group_ids = [group_id for group_id, _subject_id in groups]
    member_rows = (
        await db.execute(
            select(
                models.joint_lesson_group_member.c.group_id,
                models.ClassSubjectLink.class_id,
                models.ClassSubjectLink.subject_id,
            )
            .join(
                models.ClassSubjectLink,
                (
                    models.ClassSubjectLink.organization_id
                    == models.joint_lesson_group_member.c.organization_id
                )
                & (
                    models.ClassSubjectLink.id
                    == models.joint_lesson_group_member.c.class_subject_link_id
                ),
            )
            .where(
                models.joint_lesson_group_member.c.organization_id == organization_id,
                models.joint_lesson_group_member.c.group_id.in_(group_ids),
            )
        )
    ).all()
    module_rows = (
        await db.execute(
            select(
                models.joint_lesson_group_module.c.group_id,
                models.joint_lesson_group_module.c.module_id,
            )
            .where(
                models.joint_lesson_group_module.c.organization_id == organization_id,
                models.joint_lesson_group_module.c.group_id.in_(group_ids),
            )
            .order_by(models.joint_lesson_group_module.c.module_id)
        )
    ).all()
    members: dict[int, list[int]] = defaultdict(list)
    for group_id, class_id, subject_id in member_rows:
        assignment_id = assignment_id_by_key.get((class_id, subject_id))
        if assignment_id is not None:
            members[group_id].append(assignment_id)
    modules: dict[int, list[int]] = defaultdict(list)
    for group_id, module_id in module_rows:
        modules[group_id].append(module_id)
    plans: list[JointGroupPlan] = []
    for group_id, subject_id in groups:
        member_ids = tuple(sorted(set(members.get(group_id, ()))))
        joint_modules = tuple(modules.get(group_id, ()))
        if len(member_ids) < 2 or not joint_modules:
            raise SnapshotConfigurationError(
                "JOINT_GROUP_INCOMPLETE",
                "Existem aulas conjuntas com menos de duas turmas ativas ou sem módulos. "
                "Edite ou desfaça a junção.",
            )
        plans.append(JointGroupPlan(group_id, subject_id, member_ids, joint_modules))
    return tuple(plans)


async def _retired_modules(
    db: AsyncSession, organization_id: int, assignment_ids: Set[int]
) -> dict[int, set[int]]:
    """Retired (``planned = false``) modules per assignment, for joint grouping only."""
    if not assignment_ids:
        return {}
    rows = (
        await db.execute(
            select(CurricularRequirement.assignment_id, CurricularRequirement.module_id).where(
                CurricularRequirement.organization_id == organization_id,
                CurricularRequirement.assignment_id.in_(assignment_ids),
                CurricularRequirement.planned.is_(False),
            )
        )
    ).all()
    retired: dict[int, set[int]] = defaultdict(set)
    for assignment_id, module_id in rows:
        retired[assignment_id].add(module_id)
    return retired


async def _load_published_unit_keys(
    db: AsyncSession,
    organization_id: int,
    school_year_id: int,
    active_version: SchedulerVersionV1 | None,
) -> frozenset[str]:
    if active_version is None:
        return frozenset()
    rows = (
        await db.scalars(
            select(SchedulerLessonV1.teaching_unit_key)
            .where(
                SchedulerLessonV1.organization_id == organization_id,
                SchedulerLessonV1.school_year_id == school_year_id,
                SchedulerLessonV1.version_id == active_version.id,
            )
            .distinct()
        )
    ).all()
    return frozenset(rows)


_CLAIM_UNIT_RANK = {"D": 0, "J": 1, "S": 2, "A": 3}


def _map_claim_units(
    unit_plan: TeachingUnitPlan,
    assignments: Sequence[CurricularAssignment],
    open_debt: Mapping[int, int],
    raw_claim_assignments: Mapping[int, int],
) -> tuple[dict[int, int], dict[int, int]]:
    """Map every open debt claim to a teaching unit and its class (WBS 3.2.4).

    The debt's accounting assignment names the class; the unit is the deficit
    (``D``) unit of that class when it still has residual minutes, otherwise the
    joint unit, then the separate/assignment units. The class map is always
    derived from the accounting assignment, never from a unit's first class.
    """
    units_by_id = {unit.unit_id: unit for unit in unit_plan.units}
    class_by_assignment = {row.id: row.class_id for row in assignments}
    accounting_to_units: dict[int, list[int]] = defaultdict(list)
    for unit_id, payers in unit_plan.accounting_assignments.items():
        for payer in payers:
            accounting_to_units[payer].append(unit_id)

    def rank(unit_id: int) -> tuple[int, int]:
        prefix = units_by_id[unit_id].key.split(":", 1)[0]
        return (_CLAIM_UNIT_RANK.get(prefix, 4), unit_id)

    claim_assignments: dict[int, int] = {}
    claim_classes: dict[int, int] = {}
    for claim_id in open_debt:
        accounting = raw_claim_assignments.get(claim_id)
        if accounting is None:
            continue
        candidates = accounting_to_units.get(accounting, [])
        if not candidates:
            continue
        claim_class = class_by_assignment.get(accounting)
        if claim_class is not None:
            claim_classes[claim_id] = claim_class
        matching = [
            unit_id
            for unit_id in candidates
            if claim_class in units_by_id[unit_id].class_ids
            and units_by_id[unit_id].residual_minutes > 0
        ]
        claim_assignments[claim_id] = min(matching or candidates, key=rank)
    return claim_assignments, claim_classes


async def _build_assignments(
    db: AsyncSession,
    organization_id: int,
    assignments: Sequence[CurricularAssignment],
    requirements: Mapping[int, tuple[ModuleRequirement, ...]],
    executed: Mapping[int, Mapping[int, int]],
    groups: Sequence[JointGroupPlan],
    published_unit_keys: Set[str],
    *,
    constraints: SchoolConstraintPolicy,
) -> tuple[
    tuple[Assignment, ...], TeachingUnitPlan, dict[int, dict[int, int]], tuple[HomeRoom, ...]
]:
    """Build one domain unit per ``build_teaching_units`` unit (WBS 3.2.1-3.2.2)."""
    class_rows = (
        await db.execute(
            select(
                models.Class.id,
                models.Class.size,
                models.Class.name,
                models.Class.home_room_id,
            ).where(
                models.Class.organization_id == organization_id,
                models.Class.id.in_({row.class_id for row in assignments}),
            )
        )
    ).all()
    class_sizes = {class_id: (size, name) for class_id, size, name, _home in class_rows}
    home_room_by_class = {
        class_id: home_room_id
        for class_id, _size, _name, home_room_id in class_rows
        if home_room_id is not None
    }
    subject_types = {
        subject_id: (room_type_id, room_type_name, name, is_normal)
        for subject_id, room_type_id, room_type_name, name, is_normal in (
            await db.execute(
                select(
                    models.Subject.id,
                    models.Subject.room_type_id,
                    models.SchoolRoomType.name,
                    models.Subject.name,
                    models.SchoolRoomType.is_normal,
                )
                .join(models.Subject.room_type)
                .where(
                    models.Subject.organization_id == organization_id,
                    models.Subject.id.in_({row.subject_id for row in assignments}),
                )
            )
        ).all()
    }
    rooms = [
        (room.id, room.room_type_id, room.capacity)
        for room in (
            await db.execute(
                select(models.Room)
                .where(
                    models.Room.organization_id == organization_id,
                    models.Room.is_archived.is_(False),
                )
                .order_by(models.Room.id)
            )
        )
        .scalars()
        .all()
    ]
    grouped_ids = {member for group in groups for member in group.member_assignment_ids}
    retired = await _retired_modules(db, organization_id, grouped_ids)
    plans: list[AssignmentPlan] = []
    for row in assignments:
        kept = requirements[row.id]
        if row.id in grouped_ids and retired.get(row.id):
            dropped = retired[row.id]
            kept = tuple(module for module in kept if module.module_id not in dropped)
        if not kept:
            if row.id in grouped_ids:
                raise SnapshotConfigurationError(
                    "JOINT_GROUP_INCOMPLETE",
                    "Existem aulas conjuntas sem módulos conjuntos. Edite ou desfaça a junção.",
                )
            raise SnapshotConfigurationError(
                "ASSIGNMENT_WITHOUT_REQUIREMENTS",
                "Existem disciplinas atribuídas sem módulos com minutos definidos.",
            )
        kept_ids = {module.module_id for module in kept}
        plans.append(
            AssignmentPlan(
                assignment_id=row.id,
                class_id=row.class_id,
                subject_id=row.subject_id,
                teacher_id=row.teacher_id,
                student_count=class_sizes.get(row.class_id, (0, ""))[0],
                modules=kept,
                executed_minutes={
                    module_id: minutes
                    for module_id, minutes in executed.get(row.id, {}).items()
                    if module_id in kept_ids
                },
            )
        )
    try:
        plan = build_teaching_units(plans, groups, set(published_unit_keys))
    except JointTeacherMismatch as exc:
        raise SnapshotConfigurationError(
            "JOINT_TEACHER_MISMATCH",
            "As turmas de uma aula conjunta têm professores diferentes.",
        ) from exc
    except ValueError as exc:
        raise SnapshotConfigurationError(
            "JOINT_GROUP_INCOMPLETE",
            "Uma aula conjunta é inconsistente com os módulos marcados nas turmas.",
        ) from exc

    result: list[Assignment] = []
    room_issues: list[dict[str, object]] = []
    for unit in plan.units:
        subject = subject_types.get(unit.subject_id)
        if subject is None:
            raise SnapshotConfigurationError(
                "UNKNOWN_SUBJECT", "Uma atribuição curricular refere uma disciplina desconhecida."
            )
        required_type_id, required_type_name, subject_name, subject_is_normal = subject
        if any(class_id not in class_sizes for class_id in unit.class_ids):
            raise SnapshotConfigurationError(
                "UNKNOWN_CLASS", "Uma atribuição curricular refere uma turma desconhecida."
            )
        names = [class_sizes[class_id][1] for class_id in unit.class_ids]
        required_capacity = sum(class_sizes[class_id][0] for class_id in unit.class_ids)
        restricted = [
            constraints.specific_rooms[(class_id, unit.subject_id)]
            for class_id in unit.class_ids
            if (class_id, unit.subject_id) in constraints.specific_rooms
        ]
        allowed = (
            frozenset.intersection(*(frozenset(value) for value in restricted))
            if restricted
            else None
        )
        eligibility = assess_room_eligibility(
            rooms,
            required_room_type=required_type_id,
            required_capacity=required_capacity,
            allowed_room_ids=allowed,
            home_room_ids=[
                home_room_by_class[class_id]
                for class_id in unit.class_ids
                if class_id in home_room_by_class
            ],
            subject_is_normal=subject_is_normal,
        )
        if eligibility.reason is not None:
            issue: dict[str, object] = {
                "class_id": unit.class_ids[0],
                "class_name": ", ".join(name for name in names if name),
                "subject_id": unit.subject_id,
                "subject_name": subject_name,
                "required_room_type_name": required_type_name,
                "required_capacity": required_capacity,
                "max_available_capacity": eligibility.max_available_capacity,
                "reason": eligibility.reason.value,
            }
            if len(unit.class_ids) > 1:
                issue["class_ids"] = list(unit.class_ids)
            room_issues.append(issue)
            continue
        result.append(
            Assignment(
                assignment_id=unit.unit_id,
                class_ids=unit.class_ids,
                subject_id=unit.subject_id,
                teacher_id=unit.teacher_id,
                eligible_room_ids=eligibility.eligible_room_ids,
                modules=unit.modules,
                needs_special_room=not subject_is_normal,
            )
        )
    if room_issues:
        raise SnapshotConfigurationError(
            "NO_ELIGIBLE_ROOM",
            "Existem disciplinas sem sala compatível com o tipo e a lotação das turmas.",
            public_context={"room_issues": room_issues},
        )
    unit_executed = {unit.unit_id: dict(unit.executed_minutes) for unit in plan.units}
    return (
        tuple(result),
        plan,
        unit_executed,
        _valid_home_rooms(home_room_by_class, class_sizes, rooms),
    )


def _valid_home_rooms(
    home_room_by_class: Mapping[int, int],
    class_sizes: Mapping[int, tuple[int, str]],
    rooms: Sequence[tuple[int, int | None, int]],
) -> tuple[HomeRoom, ...]:
    """Home rooms that are active and seat their class (D13); the others are ignored."""
    capacity_by_room = {room_id: capacity for room_id, _type_id, capacity in rooms}
    return tuple(
        HomeRoom(class_id=class_id, room_id=room_id)
        for class_id, room_id in sorted(home_room_by_class.items())
        if class_id in class_sizes and capacity_by_room.get(room_id, 0) >= class_sizes[class_id][0]
    )


async def _load_constraint_policy(db: AsyncSession, organization_id: int) -> SchoolConstraintPolicy:
    rows = (
        await db.scalars(
            select(models.Constraint).where(models.Constraint.organization_id == organization_id)
        )
    ).all()
    if any(str(getattr(row, "rule_type", "")) == "lock_time" for row in rows):
        raise SnapshotConfigurationError(
            "LOCKED_TIMESLOT_UNSUPPORTED",
            "Existem regras de horário fixo que a nova geração ainda não suporta. "
            "Remova-as e volte a tentar.",
        )
    parsed = SchoolConstraintPolicy.parse(rows)
    if not parsed.is_valid:
        message = (
            parsed.configuration_violations[0].message if parsed.configuration_violations else ""
        )
        raise SnapshotConfigurationError(
            "INVALID_CONSTRAINTS",
            f"Existem regras de horário inválidas para a nova geração. {message}".strip(),
        )
    policy = parsed.policy
    if policy is None:
        raise SnapshotConfigurationError(
            "INVALID_CONSTRAINTS", "Existem regras de horário inválidas para a nova geração."
        )
    return policy


async def _load_unavailability(
    db: AsyncSession,
    organization_id: int,
    *,
    constraints: SchoolConstraintPolicy,
    calendar: _CalendarData,
) -> tuple[tuple[Unavailability, ...], tuple[Unavailability, ...]]:
    availability_rows = (
        await db.scalars(
            select(models.Availability).where(
                models.Availability.organization_id == organization_id
            )
        )
    ).all()
    class_rows = (
        await db.execute(
            select(
                models.ClassAvailability.class_id,
                models.ClassAvailability.timeslot_id,
                models.ClassAvailability.score,
            )
            .join(
                models.Class,
                (models.Class.organization_id == models.ClassAvailability.organization_id)
                & (models.Class.id == models.ClassAvailability.class_id),
            )
            .where(
                models.ClassAvailability.organization_id == organization_id,
                models.Class.is_archived.is_(False),
            )
        )
    ).all()
    teacher_hard, teacher_soft = _preference_unavailability(
        UnavailableResource.TEACHER,
        ((row.teacher_id, row.timeslot_id, row.score) for row in availability_rows),
        calendar,
        extra_preferred=constraints.teacher_preferred_timeslots,
    )
    class_hard, class_soft = _preference_unavailability(
        UnavailableResource.CLASS,
        ((row.class_id, row.timeslot_id, row.score) for row in class_rows),
        calendar,
    )
    hard: list[Unavailability] = [*teacher_hard, *class_hard]
    soft: list[Unavailability] = [*teacher_soft, *class_soft]
    for row in constraints.teacher_unavailable_timeslots:
        teacher_id, timeslot_id = row
        signature = calendar.signature_by_timeslot.get(timeslot_id)
        if signature is not None:
            hard.extend(
                Unavailability(UnavailableResource.TEACHER, teacher_id, period)
                for period in calendar.periods_by_signature.get(signature, ())
            )
    for teacher_id, weekday in constraints.teacher_unavailable_days:
        hard.extend(
            Unavailability(UnavailableResource.TEACHER, teacher_id, period)
            for period in calendar.periods
            if period.school_date.weekday() == weekday
        )
    for teacher_id, blocked_date in constraints.teacher_unavailable_dates:
        hard.extend(
            Unavailability(UnavailableResource.TEACHER, teacher_id, period)
            for period in calendar.periods_by_date.get(blocked_date, ())
        )
    for teacher_id, blocked_date, timeslot_id in constraints.teacher_unavailable_date_slots:
        signature = calendar.signature_by_timeslot.get(timeslot_id)
        if signature is not None:
            hard.extend(
                Unavailability(UnavailableResource.TEACHER, teacher_id, period)
                for period in calendar.periods_by_signature.get(signature, ())
                if period.school_date == blocked_date
            )
    return tuple(hard), tuple(soft)


def _preference_unavailability(
    resource_type: UnavailableResource,
    scores: Iterable[tuple[int, int, int]],
    calendar: _CalendarData,
    extra_preferred: Iterable[tuple[int, int]] = (),
) -> tuple[list[Unavailability], list[Unavailability]]:
    """Weekly preference rows become hard and soft unavailability.

    One impossible block is hard for every period with its signature; an avoid
    block is soft. A resource with at least one preferred block gets soft
    unavailability on every period its preferred blocks do not cover.
    ``extra_preferred`` adds constraint-derived ``(resource_id, timeslot_id)``
    preferred blocks, keeping the teacher behaviour unchanged.
    """
    rows = tuple(scores)
    preferred: dict[int, set[int]] = defaultdict(set)
    for resource_id, timeslot_id, score in rows:
        if score == models.PreferenceLevel.PREFERRED.value:
            preferred[resource_id].add(timeslot_id)
    for resource_id, timeslot_id in extra_preferred:
        preferred[resource_id].add(timeslot_id)
    hard: list[Unavailability] = []
    soft: list[Unavailability] = []
    for resource_id, timeslot_id, score in rows:
        signature = calendar.signature_by_timeslot.get(timeslot_id)
        if signature is None:
            continue
        if score == models.PreferenceLevel.IMPOSSIBLE.value:
            hard.extend(
                Unavailability(resource_type, resource_id, period)
                for period in calendar.periods_by_signature.get(signature, ())
            )
        elif score == models.PreferenceLevel.AVOID.value:
            soft.extend(
                Unavailability(resource_type, resource_id, period)
                for period in calendar.periods_by_signature.get(signature, ())
            )
    for resource_id, timeslot_ids in sorted(preferred.items()):
        for period in calendar.periods:
            signature = (period.school_date.weekday(), period.start_local, period.end_local)
            matching = calendar.timeslots_by_signature.get(signature)
            if matching and matching.isdisjoint(timeslot_ids):
                soft.append(Unavailability(resource_type, resource_id, period))
    return hard, soft


async def _load_baseline(
    db: AsyncSession,
    organization_id: int,
    school_year_id: int,
    zone: ZoneInfo,
    *,
    active_version: SchedulerVersionV1 | None,
    now_utc: datetime,
    protected_dates: frozenset[date],
    assignments: Mapping[int, Assignment] | None = None,
    executed: Mapping[int, Mapping[int, int]] | None = None,
    unit_keys: Mapping[str, int] | None = None,
    class_ids_by_unit: Mapping[int, tuple[int, ...]] | None = None,
    accounting_classes: Mapping[int, int] | None = None,
) -> tuple[
    tuple[ScheduledLesson, ...],
    tuple[ScheduledLesson, ...],
    tuple[RecoveryAllocation, ...],
    Mapping[int, int],
    tuple[Unavailability, ...],
    Mapping[int, Mapping[int, int]],
]:
    if active_version is None:
        empty: Mapping = MappingProxyType({})
        return (), (), (), empty, (), empty
    version_lessons = await load_version_lessons(
        db,
        organization_id,
        school_year_id,
        active_version,
        zone,
        unit_keys=unit_keys,
        class_ids_by_unit=class_ids_by_unit,
        accounting_classes=accounting_classes,
    )
    identity_by_db_id = version_lessons.identity_by_db_id
    baseline = tuple(
        lesson
        for lesson in version_lessons.lessons
        if lesson.lesson_id not in version_lessons.unresolved_identities
    )
    for lesson in version_lessons.lessons:
        if lesson.lesson_id not in version_lessons.unresolved_identities:
            continue
        if lesson.period.start_utc <= now_utc or lesson.period.school_date in protected_dates:
            raise SnapshotConfigurationError(
                "JOINT_PUBLISHED_LESSONS_CONFLICT",
                "Uma aula conjunta publicada usa uma unidade que já não existe. "
                "Gere um novo horário.",
            )
    history_unavailable: list[Unavailability] = []
    if assignments is not None and executed is not None:
        try:
            history, baseline = await split_version_history(
                db,
                organization_id,
                school_year_id,
                active_version,
                baseline,
                assignments,
                executed,
                now_utc=now_utc,
            )
        except ValueError as exc:
            raise SnapshotConfigurationError(
                "EXECUTION_OVERLAPS_PROTECTED",
                "O progresso registado sobrepõe-se a meio de uma aula publicada.",
            ) from exc
        # History is copied into the proposal after search. Its future physical
        # intervals must remain unavailable even though it earns no planned credit.
        for lesson in history:
            if lesson.period.end_utc <= now_utc:
                continue
            assignment = assignments[lesson.assignment_id]
            for resource_type, resource_id in (
                *((UnavailableResource.CLASS, class_id) for class_id in assignment.class_ids),
                (UnavailableResource.TEACHER, lesson.teacher_id or assignment.teacher_id),
                (UnavailableResource.ROOM, lesson.room_id),
            ):
                history_unavailable.append(
                    Unavailability(resource_type, resource_id, lesson.period)
                )
        baseline = _reproject_baseline(
            baseline,
            assignments,
            executed,
            now_utc=now_utc,
            protected_dates=protected_dates,
        )
    protected = [
        lesson
        for lesson in baseline
        if lesson.period.start_utc <= now_utc or lesson.period.school_date in protected_dates
    ]
    reservations = (
        await db.scalars(
            select(SchedulerRecoveryReservationV1).where(
                SchedulerRecoveryReservationV1.organization_id == organization_id,
                SchedulerRecoveryReservationV1.school_year_id == school_year_id,
                SchedulerRecoveryReservationV1.version_id == active_version.id,
            )
        )
    ).all()
    allocations = tuple(
        RecoveryAllocation(
            row.version_id,
            identity_by_db_id[row.lesson_id],
            row.debt_id,
            row.minutes,
        )
        for row in reservations
    )
    return (
        tuple(baseline),
        tuple(protected),
        allocations,
        MappingProxyType({identity: db_id for db_id, identity in identity_by_db_id.items()}),
        tuple(history_unavailable),
        version_lessons.db_ids_by_identity_class,
    )


async def split_version_history(
    db: AsyncSession,
    organization_id: int,
    school_year_id: int,
    version: SchedulerVersionV1,
    lessons: Sequence[ScheduledLesson],
    assignments: Mapping[int, Assignment],
    executed: Mapping[int, Mapping[int, int]],
    *,
    now_utc: datetime,
) -> tuple[tuple[ScheduledLesson, ...], tuple[ScheduledLesson, ...]]:
    """Separate logged history, including missed lessons, from planned credit.

    Candidate history still points to the previous version's operational log.
    Completed lessons are history even when another earlier lesson was missed.
    """
    logged = set(
        (
            await db.scalars(
                select(SchedulerLessonV1.stable_key)
                .join(
                    SchedulerLessonLogV1,
                    or_(
                        SchedulerLessonLogV1.lesson_id == SchedulerLessonV1.id,
                        SchedulerLessonLogV1.lesson_id == SchedulerLessonV1.source_lesson_id,
                    ),
                )
                .where(
                    SchedulerLessonV1.organization_id == organization_id,
                    SchedulerLessonV1.school_year_id == school_year_id,
                    SchedulerLessonV1.version_id == version.id,
                    SchedulerLessonLogV1.organization_id == organization_id,
                    SchedulerLessonLogV1.school_year_id == school_year_id,
                    SchedulerLessonLogV1.status.in_(("COMPLETED", "OCCURRENCE")),
                )
            )
        ).all()
    )
    history = tuple(row for row in lessons if str(row.lesson_id) in logged)
    unlogged = tuple(row for row in lessons if str(row.lesson_id) not in logged)
    past = tuple(row for row in unlogged if row.period.start_utc <= now_utc)
    future = tuple(row for row in unlogged if row.period.start_utc > now_utc)
    consumed, protected = split_consumed_lessons(past, assignments, executed)
    # Manual ledger corrections change future demand. A hypothetical future
    # lesson covered by those minutes was never operational history.
    return (*history, *consumed), (*protected, *future)


def _reproject_baseline(
    lessons: Sequence[ScheduledLesson],
    assignments: Mapping[int, Assignment],
    executed: Mapping[int, Mapping[int, int]],
    *,
    now_utc: datetime,
    protected_dates: frozenset[date],
) -> tuple[ScheduledLesson, ...]:
    """Reproject movable lessons onto the current planning modules.

    A retired or shortened module shrinks the residual demand. Past lessons are
    never removed. Future lessons inside the stability window are removed only
    when this assignment's curriculum changed (a slice references a module that
    left the selection, or its required minutes no longer hold); an unchanged
    assignment keeps its full stability. Genuinely movable excess outside the
    window is always released. When the fixed credit alone cannot fit, the
    snapshot fails explicitly instead of deleting a protected position.
    """
    by_assignment: dict[int, list[ScheduledLesson]] = defaultdict(list)
    for lesson in lessons:
        by_assignment[lesson.assignment_id].append(lesson)
    revised: dict[int, ScheduledLesson] = {}
    dropped: set[int] = set()
    for identity, rows in by_assignment.items():
        assignment = assignments[identity]
        completed = executed.get(identity, {})
        residual = sum(module.required_minutes for module in assignment.modules) - sum(
            completed.values()
        )
        ordered = sorted(
            rows, key=lambda row: (row.period.school_date, row.period.start_utc, row.lesson_id)
        )
        planning = {module.module_id: module for module in assignment.modules}
        changed = any(
            slice_.module_id not in planning
            or slice_.offset_minutes + slice_.credit_minutes
            > planning[slice_.module_id].required_minutes
            for row in ordered
            for slice_ in row.slices
        )
        releasable = [
            row
            for row in ordered
            if row.period.start_utc > now_utc
            and (changed or not is_physically_protected(row.period, now_utc, protected_dates))
        ]
        releasable_ids = {row.lesson_id for row in releasable}
        fixed_credit = sum(
            row.credit_minutes for row in ordered if row.lesson_id not in releasable_ids
        )
        if fixed_credit > residual:
            raise SnapshotConfigurationError(
                "PROTECTED_LESSON_EXCEEDS_CURRICULUM",
                "Existem aulas passadas que não cabem no currículo selecionado.",
            )
        fitted = [row for row in ordered if row.lesson_id not in releasable_ids]
        credit = fixed_credit
        for row in releasable:
            if credit + row.credit_minutes > residual:
                dropped.add(row.lesson_id)
                continue
            fitted.append(row)
            credit += row.credit_minutes
        if not fitted:
            continue
        fitted.sort(key=lambda row: (row.period.school_date, row.period.start_utc, row.lesson_id))
        slices = project_module_slices(
            assignment.modules,
            completed_minutes=completed,
            lessons=tuple(
                FutureLesson(
                    row.lesson_id,
                    row.period.school_date,
                    row.period.start_local.hour * 60 + row.period.start_local.minute,
                    row.period.duration_minutes,
                    row.credit_minutes,
                )
                for row in fitted
            ),
            require_complete=False,
        )
        by_lesson: dict[int, list[ModuleSlice]] = defaultdict(list)
        for slice_ in slices:
            by_lesson[slice_.lesson_id].append(slice_)
        for row in fitted:
            revised[row.lesson_id] = replace(row, slices=tuple(by_lesson[row.lesson_id]))
    return tuple(revised.get(row.lesson_id, row) for row in lessons if row.lesson_id not in dropped)


@dataclass(frozen=True)
class VersionLessons:
    """One version's lessons as domain values, with sibling-aware identity maps."""

    lessons: tuple[ScheduledLesson, ...]
    identity_by_db_id: Mapping[int, int]
    db_id_by_identity: Mapping[int, int]
    db_ids_by_identity_class: Mapping[int, Mapping[int, int]]
    unresolved_identities: frozenset[int]


def _sibling_rows_are_consistent(first: Row, group: Sequence[Row]) -> bool:
    physical = (
        first.teaching_unit_key,
        first.school_date,
        first.starts_at,
        first.ends_at,
        first.room_id,
        first.physical_minutes,
        first.credit_minutes,
    )
    for other in group[1:]:
        if (
            other.teaching_unit_key,
            other.school_date,
            other.starts_at,
            other.ends_at,
            other.room_id,
            other.physical_minutes,
            other.credit_minutes,
        ) != physical:
            return False
    return True


async def load_version_lessons(
    db: AsyncSession,
    organization_id: int,
    school_year_id: int,
    version: SchedulerVersionV1,
    zone: ZoneInfo,
    *,
    unit_keys: Mapping[str, int] | None = None,
    class_ids_by_unit: Mapping[int, tuple[int, ...]] | None = None,
    accounting_classes: Mapping[int, int] | None = None,
) -> VersionLessons:
    """Lessons of one version grouped into logical lessons (WBS 3.2.3).

    Sister rows of a joint lesson share ``stable_key``; they collapse into one
    domain ``ScheduledLesson`` carrying every member class and the unit id
    resolved from ``teaching_unit_key``. Physical metadata, slices and the unit
    key must match across sisters (``JOINT_LESSON_INCONSISTENT``). A protected
    sister whose key has no current unit is rejected earlier; an editable
    future lesson without a unit only pairs identities.
    """
    rows = (
        await db.execute(
            select(
                SchedulerLessonV1.id,
                SchedulerLessonV1.assignment_id,
                SchedulerLessonV1.stable_key,
                SchedulerLessonV1.school_date,
                SchedulerLessonV1.starts_at,
                SchedulerLessonV1.ends_at,
                SchedulerLessonV1.room_id,
                SchedulerLessonV1.physical_minutes,
                SchedulerLessonV1.credit_minutes,
                SchedulerLessonV1.source_lesson_id,
                SchedulerLessonV1.teaching_unit_key,
            )
            .where(
                SchedulerLessonV1.organization_id == organization_id,
                SchedulerLessonV1.school_year_id == school_year_id,
                SchedulerLessonV1.version_id == version.id,
                SchedulerLessonV1.id.not_in(
                    select(SchedulerLessonLogV1.lesson_id).where(
                        SchedulerLessonLogV1.organization_id == organization_id,
                        SchedulerLessonLogV1.withdrawn_at.is_not(None),
                    )
                ),
            )
            .order_by(SchedulerLessonV1.id)
        )
    ).all()
    if not rows:
        empty: Mapping = MappingProxyType({})
        return VersionLessons((), empty, empty, empty, frozenset())
    row_identity = {row.id: _identity(row.stable_key) for row in rows}
    slice_rows = (
        await db.execute(
            select(
                SchedulerLessonSliceV1.lesson_id,
                SchedulerLessonSliceV1.module_id,
                SchedulerLessonSliceV1.offset_minutes,
                SchedulerLessonSliceV1.minutes,
            )
            .where(
                SchedulerLessonSliceV1.organization_id == organization_id,
                SchedulerLessonSliceV1.school_year_id == school_year_id,
                SchedulerLessonSliceV1.lesson_id.in_([row.id for row in rows]),
            )
            .order_by(SchedulerLessonSliceV1.id)
        )
    ).all()
    slices_by_db_id: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    for slice_row in slice_rows:
        slices_by_db_id[slice_row.lesson_id].append(
            (slice_row.module_id, slice_row.offset_minutes, slice_row.minutes)
        )

    known_unit_keys = dict(unit_keys or {})
    unit_class_ids = dict(class_ids_by_unit or {})
    accounting_class = dict(accounting_classes or {})
    groups: dict[str, list[Row]] = defaultdict(list)
    for row in rows:
        groups[row.stable_key].append(row)

    lessons: list[ScheduledLesson] = []
    identity_by_db_id: dict[int, int] = {}
    db_id_by_identity: dict[int, int] = {}
    db_ids_by_identity_class: dict[int, dict[int, int]] = {}
    unresolved: set[int] = set()
    for stable_key, group in sorted(
        groups.items(), key=lambda pair: min(row.id for row in pair[1])
    ):
        identity = _identity(stable_key)
        first = group[0]
        if not _sibling_rows_are_consistent(first, group):
            raise SnapshotConfigurationError(
                "JOINT_LESSON_INCONSISTENT",
                "As aulas irmãs de uma aula conjunta não são idênticas. Gere um novo horário.",
            )
        base_slices = sorted(slices_by_db_id.get(first.id, ()))
        if any(sorted(slices_by_db_id.get(row.id, ())) != base_slices for row in group[1:]):
            raise SnapshotConfigurationError(
                "JOINT_LESSON_INCONSISTENT",
                "As aulas irmãs de uma aula conjunta não partilham os mesmos módulos.",
            )
        unit_id = known_unit_keys.get(first.teaching_unit_key)
        expected_classes = unit_class_ids.get(unit_id) if unit_id is not None else None
        class_ids: tuple[int, ...] | None = None
        if expected_classes is not None:
            row_classes = {accounting_class.get(row.assignment_id) for row in group}
            if None in row_classes or set(row_classes) != set(expected_classes):
                raise SnapshotConfigurationError(
                    "JOINT_LESSON_INCONSISTENT",
                    "Uma aula conjunta publicada não tem exatamente as aulas irmãs das suas turmas.",
                )
            class_ids = tuple(expected_classes)
        elif len(group) > 1:
            raise SnapshotConfigurationError(
                "JOINT_PUBLISHED_LESSONS_CONFLICT",
                "Uma aula conjunta publicada usa uma unidade que já não existe. Gere um novo horário.",
            )
        else:
            unresolved.add(identity)
        local_start = first.starts_at.astimezone(zone)
        local_end = first.ends_at.astimezone(zone)
        lessons.append(
            ScheduledLesson(
                lesson_id=identity,
                assignment_id=unit_id if unit_id is not None else first.assignment_id,
                period=normalize_period(
                    first.school_date,
                    time(local_start.hour, local_start.minute),
                    time(local_end.hour, local_end.minute),
                    zone.key,
                ),
                room_id=first.room_id,
                credit_minutes=first.credit_minutes,
                slices=tuple(
                    ModuleSlice(identity, module_id, offset, credit)
                    for module_id, offset, credit in sorted(base_slices)
                ),
                source_lesson_id=(
                    row_identity.get(first.source_lesson_id)
                    if first.source_lesson_id is not None
                    else None
                ),
                class_ids=class_ids,
            )
        )
        for row in group:
            identity_by_db_id[row.id] = identity
            class_id = accounting_class.get(row.assignment_id)
            if class_id is not None:
                db_ids_by_identity_class.setdefault(identity, {})[class_id] = row.id
        db_id_by_identity[identity] = min(row.id for row in group)
    return VersionLessons(
        tuple(lessons),
        MappingProxyType(identity_by_db_id),
        MappingProxyType(db_id_by_identity),
        MappingProxyType(
            {
                identity: MappingProxyType(rows)
                for identity, rows in db_ids_by_identity_class.items()
            }
        ),
        frozenset(unresolved),
    )


def _identity(stable_key: str) -> int:
    try:
        value = int(stable_key)
    except (TypeError, ValueError) as exc:
        raise SnapshotConfigurationError(
            "BASELINE_IDENTITY_INVALID",
            "O horário publicado não foi criado pela nova geração.",
        ) from exc
    if value <= 0:
        raise SnapshotConfigurationError(
            "BASELINE_IDENTITY_INVALID",
            "O horário publicado não foi criado pela nova geração.",
        )
    return value
