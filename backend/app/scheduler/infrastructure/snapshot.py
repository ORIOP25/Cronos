"""Build the immutable planning snapshot from persisted school data.

The builder is the only production reader that turns relational records into
domain values. It resolves the active school year, the joint room eligibility,
the executed ledger, the open debt, the published baseline and the physical
unavailability. It never writes and never consults a global clock: the caller
injects ``school_today`` and ``now_utc``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from types import MappingProxyType
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.scheduler.domain.calendar import (
    Period,
    grid_dates,
    normalize_period,
    protected_grid_dates,
)
from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    GridSlot,
    PlanningSnapshot,
    ScheduledLesson,
    SchedulingStrategy,
    Unavailability,
    UnavailableResource,
    split_consumed_lessons,
)
from app.scheduler.domain.constraint_policy import SchoolConstraintPolicy
from app.scheduler.domain.debt import RecoveryAllocation
from app.scheduler.domain.projection import ModuleRequirement, ModuleSlice
from app.scheduler.domain.recovery import RecoveryPolicy
from app.scheduler.domain.serialization import payload_digest, period_to_dict, snapshot_to_dict
from app.scheduler.infrastructure.models import (
    CurricularAssignment,
    CurricularRequirement,
    SchedulerLessonSliceV1,
    SchedulerLessonV1,
    SchedulerRecoveryReservationV1,
    SchedulerVersionV1,
)
from app.scheduler.infrastructure.progress import load_executed_minutes, load_open_debt


class SnapshotConfigurationError(ValueError):
    """The persisted configuration cannot produce a valid planning snapshot."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


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
    base_lesson_ids: Mapping[int, int]
    input_revision: int
    planning_revision: int
    digest: str
    policy: RecoveryPolicy | None

    @property
    def baseline(self) -> CandidateSchedule | None:
        if not self.snapshot.baseline_lessons:
            return None
        return CandidateSchedule(self.snapshot.baseline_lessons)


@dataclass(frozen=True)
class _CalendarData:
    grid_slots: tuple[GridSlot, ...]
    periods: tuple[Period, ...]
    blocked_dates: frozenset[date]
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
) -> SnapshotBundle:
    """Read the current school state into a planning snapshot."""
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

    calendar = await _load_calendar(db, organization_id, year, strategy=strategy)
    assignments, requirements = await _load_assignments(db, organization_id, year.id)
    constraints = await _load_constraint_policy(db, organization_id)
    domain_assignments = await _build_assignments(
        db,
        organization_id,
        assignments,
        requirements,
        constraints=constraints,
    )
    unavailable, soft_unavailable = await _load_unavailability(
        db,
        organization_id,
        constraints=constraints,
        calendar=calendar,
    )
    executed = await load_executed_minutes(
        db, organization_id, [row.assignment_id for row in domain_assignments]
    )
    open_debt, claim_assignments = await load_open_debt(
        db, organization_id, [row.assignment_id for row in domain_assignments]
    )
    school_today = now_utc.astimezone(zone).date()
    protected_dates = _stability_protected_dates(
        year, calendar, school_today, await _stability_window(db, organization_id)
    )
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
    baseline_lessons, protected_lessons, reservations, base_lesson_ids = await _load_baseline(
        db,
        organization_id,
        year.id,
        zone,
        active_version=active_version,
        now_utc=now_utc,
        protected_dates=protected_dates,
        assignments={row.assignment_id: row for row in domain_assignments},
        executed=executed,
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
            unavailable=unavailable,
            soft_unavailable=soft_unavailable,
            protected_lessons=protected_lessons,
            baseline_lessons=baseline_lessons,
            protected_dates=protected_dates,
            now_utc=now_utc,
            reservations=reservations,
            open_debt_minutes=open_debt,
            claim_assignments=claim_assignments,
            active_version_id=active_version.id if active_version is not None else None,
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
) -> _CalendarData:
    timeslots = (
        await db.scalars(
            select(models.Timeslot)
            .where(models.Timeslot.organization_id == organization_id)
            .order_by(models.Timeslot.day_of_week, models.Timeslot.start_time)
        )
    ).all()
    if not timeslots:
        raise SnapshotConfigurationError(
            "GRID_NOT_CONFIGURED", "A grelha semanal da escola não está configurada."
        )
    _reject_overlapping_slots(timeslots)
    slots = tuple(GridSlot(row.day_of_week, row.start_time, row.end_time) for row in timeslots)
    blocked = await _load_blocked_dates(db, organization_id)
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
        periods_by_signature=MappingProxyType(
            {key: tuple(value) for key, value in by_signature.items()}
        ),
        periods_by_date=MappingProxyType({key: tuple(value) for key, value in by_date.items()}),
        signature_by_timeslot=MappingProxyType(signature_by_timeslot),
        timeslots_by_signature=MappingProxyType(
            {key: frozenset(value) for key, value in timeslots_by_signature.items()}
        ),
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


async def _load_blocked_dates(db: AsyncSession, organization_id: int) -> frozenset[date]:
    events = (
        await db.scalars(
            select(models.SchoolCalendarEvent).where(
                models.SchoolCalendarEvent.organization_id == organization_id
            )
        )
    ).all()
    blocked: set[date] = set()
    for event in events:
        if event.end_date < event.start_date:
            raise SnapshotConfigurationError(
                "INVALID_CALENDAR_EVENT",
                "Existe um evento de calendário com datas inválidas.",
            )
        day = event.start_date
        while day <= event.end_date:
            blocked.add(day)
            day += timedelta(days=1)
    return frozenset(blocked)


async def _load_assignments(
    db: AsyncSession,
    organization_id: int,
    school_year_id: int,
) -> tuple[list[CurricularAssignment], dict[int, tuple[ModuleRequirement, ...]]]:
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
        modules.sort(key=lambda module: module.sequence)
    return list(assignments), {key: tuple(value) for key, value in requirements.items()}


async def _build_assignments(
    db: AsyncSession,
    organization_id: int,
    assignments: Sequence[CurricularAssignment],
    requirements: Mapping[int, tuple[ModuleRequirement, ...]],
    *,
    constraints: SchoolConstraintPolicy,
) -> tuple[Assignment, ...]:
    class_sizes = dict(
        (
            await db.execute(
                select(models.Class.id, models.Class.size).where(
                    models.Class.organization_id == organization_id,
                    models.Class.id.in_({row.class_id for row in assignments}),
                )
            )
        ).all()
    )
    subject_types = dict(
        (
            await db.execute(
                select(models.Subject.id, models.Subject.required_room_type).where(
                    models.Subject.organization_id == organization_id,
                    models.Subject.id.in_({row.subject_id for row in assignments}),
                )
            )
        ).all()
    )
    rooms = (
        await db.scalars(
            select(models.Room)
            .where(models.Room.organization_id == organization_id)
            .order_by(models.Room.id)
        )
    ).all()
    rooms_by_type: dict[str, list[models.Room]] = defaultdict(list)
    for room in rooms:
        rooms_by_type[room.type.value].append(room)
    result: list[Assignment] = []
    for row in assignments:
        required_type = subject_types.get(row.subject_id)
        if required_type is None:
            raise SnapshotConfigurationError(
                "UNKNOWN_SUBJECT", "Uma atribuição curricular refere uma disciplina desconhecida."
            )
        class_size = class_sizes.get(row.class_id)
        if class_size is None:
            raise SnapshotConfigurationError(
                "UNKNOWN_CLASS", "Uma atribuição curricular refere uma turma desconhecida."
            )
        candidate_rooms = tuple(
            room.id
            for room in rooms_by_type.get(required_type.value, ())
            if room.capacity >= class_size
        )
        specific = constraints.specific_rooms.get((row.class_id, row.subject_id))
        if specific is not None:
            candidate_rooms = tuple(room_id for room_id in candidate_rooms if room_id in specific)
        if not candidate_rooms:
            raise SnapshotConfigurationError(
                "NO_ELIGIBLE_ROOM",
                "Existem disciplinas sem sala compatível com o tipo e a lotação da turma.",
            )
        result.append(
            Assignment(
                assignment_id=row.id,
                class_id=row.class_id,
                subject_id=row.subject_id,
                teacher_id=row.teacher_id,
                eligible_room_ids=frozenset(candidate_rooms),
                modules=requirements[row.id],
            )
        )
    return tuple(result)


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
    hard: list[Unavailability] = []
    soft: list[Unavailability] = []
    availability_rows = (
        await db.scalars(
            select(models.Availability).where(
                models.Availability.organization_id == organization_id
            )
        )
    ).all()
    preferred_slots: dict[int, set[int]] = defaultdict(set)
    for row in availability_rows:
        if row.score == models.PreferenceLevel.PREFERRED.value:
            preferred_slots[row.teacher_id].add(row.timeslot_id)
    for teacher_id, timeslot_id in constraints.teacher_preferred_timeslots:
        preferred_slots[teacher_id].add(timeslot_id)
    for row in availability_rows:
        signature = calendar.signature_by_timeslot.get(row.timeslot_id)
        if signature is None:
            continue
        if row.score == models.PreferenceLevel.IMPOSSIBLE.value:
            hard.extend(
                Unavailability(UnavailableResource.TEACHER, row.teacher_id, period)
                for period in calendar.periods_by_signature.get(signature, ())
            )
        elif row.score == models.PreferenceLevel.AVOID.value:
            soft.extend(
                Unavailability(UnavailableResource.TEACHER, row.teacher_id, period)
                for period in calendar.periods_by_signature.get(signature, ())
            )
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
    for teacher_id, timeslot_ids in sorted(preferred_slots.items()):
        for period in calendar.periods:
            signature = (
                period.school_date.weekday(),
                period.start_local,
                period.end_local,
            )
            matching = calendar.timeslots_by_signature.get(signature)
            if matching and matching.isdisjoint(timeslot_ids):
                soft.append(Unavailability(UnavailableResource.TEACHER, teacher_id, period))
    return tuple(hard), tuple(soft)


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
) -> tuple[
    tuple[ScheduledLesson, ...],
    tuple[ScheduledLesson, ...],
    tuple[RecoveryAllocation, ...],
    Mapping[int, int],
]:
    if active_version is None:
        return (), (), (), MappingProxyType({})
    baseline, identity_by_db_id, _ = await load_version_lessons(
        db, organization_id, school_year_id, active_version, zone
    )
    if assignments is not None and executed is not None:
        try:
            _, baseline = split_consumed_lessons(baseline, assignments, executed)
        except ValueError as exc:
            raise SnapshotConfigurationError(
                "EXECUTION_OVERLAPS_PROTECTED",
                "O progresso registado sobrepõe-se a meio de uma aula publicada.",
            ) from exc
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
        MappingProxyType(dict(identity_by_db_id)),
    )


async def load_version_lessons(
    db: AsyncSession,
    organization_id: int,
    school_year_id: int,
    version: SchedulerVersionV1,
    zone: ZoneInfo,
) -> tuple[tuple[ScheduledLesson, ...], Mapping[int, int], Mapping[int, int]]:
    """Lessons of one version as domain values, with both identity maps.

    The returned mappings translate between database lesson IDs and the stable
    domain identities used by the search and the validator.
    """
    lessons = (
        await db.scalars(
            select(SchedulerLessonV1)
            .where(
                SchedulerLessonV1.organization_id == organization_id,
                SchedulerLessonV1.school_year_id == school_year_id,
                SchedulerLessonV1.version_id == version.id,
            )
            .order_by(SchedulerLessonV1.id)
        )
    ).all()
    lesson_ids = [row.id for row in lessons]
    identity_by_db_id = {row.id: _identity(row.stable_key) for row in lessons}
    db_id_by_identity = {identity: row_id for row_id, identity in identity_by_db_id.items()}
    slices_by_lesson: dict[int, list[ModuleSlice]] = defaultdict(list)
    if lesson_ids:
        slice_rows = (
            await db.scalars(
                select(SchedulerLessonSliceV1)
                .where(
                    SchedulerLessonSliceV1.organization_id == organization_id,
                    SchedulerLessonSliceV1.school_year_id == school_year_id,
                    SchedulerLessonSliceV1.lesson_id.in_(lesson_ids),
                )
                .order_by(SchedulerLessonSliceV1.id)
            )
        ).all()
        for row in slice_rows:
            slices_by_lesson[row.lesson_id].append(
                ModuleSlice(
                    identity_by_db_id[row.lesson_id],
                    row.module_id,
                    row.offset_minutes,
                    row.minutes,
                )
            )
    result: list[ScheduledLesson] = []
    for row in lessons:
        local_start = row.starts_at.astimezone(zone)
        local_end = row.ends_at.astimezone(zone)
        result.append(
            ScheduledLesson(
                lesson_id=identity_by_db_id[row.id],
                assignment_id=row.assignment_id,
                period=normalize_period(
                    row.school_date,
                    time(local_start.hour, local_start.minute),
                    time(local_end.hour, local_end.minute),
                    zone.key,
                ),
                room_id=row.room_id,
                credit_minutes=row.credit_minutes,
                slices=tuple(
                    sorted(
                        slices_by_lesson.get(row.id, ()),
                        key=lambda slice_: (slice_.offset_minutes, slice_.module_id),
                    )
                ),
                source_lesson_id=(
                    identity_by_db_id.get(row.source_lesson_id)
                    if row.source_lesson_id is not None
                    else None
                ),
            )
        )
    return tuple(result), MappingProxyType(identity_by_db_id), MappingProxyType(db_id_by_identity)


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
