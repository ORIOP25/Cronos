"""Read-only analysis and proposal lifecycle for weekly-grid changes (W03/W04)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, time

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.core.task_keys import DEFAULT_REPAIR_WINDOW_DAYS, resolve_repair_window_days
from app.scheduler.domain.calendar import first_editable_grid_date
from app.scheduler.domain.timetable import BreakOverride, build_daily_slots
from app.services import grid_version_service, settings_service
from app.services.scheduler_complete_demand import CompleteDemandLedgerBuilder
from app.services.scheduler_fingerprint_service import (
    SchedulerFingerprintError,
    SchedulerFingerprintService,
)
from app.services.scheduler_generation_service import (
    GenerationConfigurationError,
    GenerationSelectionError,
    SchedulerGenerationService,
)
from app.services.scheduler_job_service import SchedulerJobError, SchedulerJobService
from app.services.scheduler_serialization import canonical_json_value, sha256_json

ProposedSignature = tuple[int, time, time]


class GridChangeError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class GridChangeAnalysis:
    first_editable_date: date
    current_configuration: dict | None
    proposed_configuration: dict
    daily: tuple[dict, ...]
    affected_availabilities: tuple[dict, ...]
    affected_constraints: tuple[dict, ...]
    lessons_without_closure: tuple[dict, ...]
    minutes_completed: int
    minutes_protected: int
    minutes_planned_after_boundary: int
    minutes_remaining: int
    fingerprint: str
    pending_grid_version_id: int | None
    can_propose: bool
    blockers: tuple[str, ...]

    def to_schema(self) -> schemas.GridChangePreviewResponse:
        return schemas.GridChangePreviewResponse(
            first_editable_date=self.first_editable_date,
            current_configuration=self.current_configuration,
            proposed_configuration=self.proposed_configuration,
            daily=list(self.daily),
            affected_availabilities=list(self.affected_availabilities),
            affected_constraints=list(self.affected_constraints),
            lessons_without_closure=list(self.lessons_without_closure),
            minutes_completed=self.minutes_completed,
            minutes_protected=self.minutes_protected,
            minutes_planned_after_boundary=self.minutes_planned_after_boundary,
            minutes_remaining=self.minutes_remaining,
            fingerprint=self.fingerprint,
            pending_grid_version_id=self.pending_grid_version_id,
            can_propose=self.can_propose,
            blockers=list(self.blockers),
        )


def _minute_of_day(value: time) -> int:
    return value.hour * 60 + value.minute


def _proposed_signatures(
    settings: schemas.TimeslotBulkCreate,
) -> tuple[ProposedSignature, ...]:
    return tuple(
        (day, slot.start, slot.end)
        for day in sorted(settings.days_of_week)
        for slot in build_daily_slots(
            opening_time=settings.start_time,
            closing_time=settings.end_time,
            slot_duration_minutes=settings.slot_duration_minutes,
            break_duration_minutes=settings.break_duration_minutes,
            break_overrides=tuple(
                BreakOverride(
                    after_slot=override.after_slot,
                    duration_minutes=override.duration_minutes,
                )
                for override in settings.break_overrides
            ),
        )
    )


def _minutes(start: time, end: time) -> int:
    return _minute_of_day(end) - _minute_of_day(start)


def _classify(
    block,
    proposed_by_signature: dict[ProposedSignature, ProposedSignature],
) -> tuple[str, ProposedSignature | None, bool]:
    """Deterministic match between a current block and the proposed grid."""
    signature = (block.day_of_week, block.start_time, block.end_time)
    if signature in proposed_by_signature:
        return "EXACT", signature, False

    same_day = [
        candidate for candidate in proposed_by_signature if candidate[0] == block.day_of_week
    ]
    if not same_day:
        return "REMOVED", None, False

    same_start = [candidate for candidate in same_day if candidate[1] == block.start_time]
    candidates = sorted(
        same_start or same_day,
        key=lambda candidate: (
            abs(_minute_of_day(candidate[1]) - _minute_of_day(block.start_time)),
            _minute_of_day(candidate[1]),
            _minute_of_day(candidate[2]),
        ),
    )
    best = candidates[0]
    ambiguous = len(candidates) > 1 and (
        abs(_minute_of_day(candidates[1][1]) - _minute_of_day(block.start_time))
        == abs(_minute_of_day(best[1]) - _minute_of_day(block.start_time))
    )
    return "MOVED", best, ambiguous


async def _canonical_minutes(
    db: AsyncSession,
    organization_id: int,
    *,
    first_editable: date,
    school_today: date,
) -> tuple[int, int, int, int] | None:
    """Completed/protected/after-boundary/remaining from the canonical demand ledger."""
    school_year_id = await db.scalar(
        select(models.SchedulerSchoolYear.id).where(
            models.SchedulerSchoolYear.organization_id == organization_id,
            models.SchedulerSchoolYear.is_active.is_(True),
        )
    )
    if school_year_id is None:
        return None
    try:
        snapshot = await SchedulerFingerprintService(db).generation_input_snapshot(
            organization_id,
            school_year_id,
            models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
        )
    except SchedulerFingerprintError:
        return None

    ledger = CompleteDemandLedgerBuilder().build(snapshot)
    required_by_module = {
        row["id"]: row.get("required_minutes", 0) for row in snapshot.get("module_accounting", [])
    }
    progress_by_key = {
        (row.get("class_id"), row.get("module_id")): max(0, int(row.get("completed_minutes", 0)))
        for row in snapshot.get("class_progress", [])
    }
    completed_credited = sum(
        min(
            progress_by_key.get((item.class_id, module.module_id), 0),
            required_by_module.get(module.module_id, 0),
        )
        for item in ledger.items
        for module in item.modules
    )
    remaining = ledger.required_minutes

    block_rows = (
        await db.execute(
            select(
                models.ActiveScheduleBlock.date,
                models.Timeslot.start_time,
                models.Timeslot.end_time,
            )
            .join(
                models.Timeslot,
                models.Timeslot.id == models.ActiveScheduleBlock.timeslot_id,
            )
            .where(
                models.ActiveScheduleBlock.organization_id == organization_id,
                models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
            )
        )
    ).all()
    protected = sum(
        _minutes(row.start_time, row.end_time)
        for row in block_rows
        if school_today <= row.date < first_editable
    )
    after_boundary = sum(
        _minutes(row.start_time, row.end_time) for row in block_rows if row.date >= first_editable
    )
    return completed_credited, protected, after_boundary, remaining


async def _fallback_minutes(
    db: AsyncSession,
    organization_id: int,
    *,
    first_editable: date,
    school_today: date,
) -> tuple[int, int, int, int]:
    requirement_rows = (
        await db.execute(
            select(
                models.ClassSubjectLink.class_id,
                models.Module.id,
                models.Module.required_minutes,
            )
            .join(models.Subject, models.Subject.id == models.ClassSubjectLink.subject_id)
            .join(models.Module, models.Module.subject_id == models.Subject.id)
            .where(
                models.ClassSubjectLink.organization_id == organization_id,
                models.Module.organization_id == organization_id,
            )
            .distinct()
        )
    ).all()
    progress_rows = (
        await db.execute(
            select(
                models.ProgressLedgerEntry.class_id,
                models.ProgressLedgerEntry.module_id,
                func.sum(models.ProgressLedgerEntry.completed_minutes_delta),
            )
            .where(models.ProgressLedgerEntry.organization_id == organization_id)
            .group_by(
                models.ProgressLedgerEntry.class_id,
                models.ProgressLedgerEntry.module_id,
            )
        )
    ).all()
    progress_by_key = {
        (row.class_id, row.module_id): max(0, int(row[2] or 0)) for row in progress_rows
    }
    completed = sum(
        min(progress_by_key.get((row.class_id, row.id), 0), row.required_minutes)
        for row in requirement_rows
    )
    required = sum(row.required_minutes for row in requirement_rows)
    remaining = max(0, required - completed)

    block_rows = (
        await db.execute(
            select(
                models.ActiveScheduleBlock.date,
                models.Timeslot.start_time,
                models.Timeslot.end_time,
            )
            .join(
                models.Timeslot,
                models.Timeslot.id == models.ActiveScheduleBlock.timeslot_id,
            )
            .where(
                models.ActiveScheduleBlock.organization_id == organization_id,
                models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
            )
        )
    ).all()
    protected = sum(
        _minutes(row.start_time, row.end_time)
        for row in block_rows
        if school_today <= row.date < first_editable
    )
    after_boundary = sum(
        _minutes(row.start_time, row.end_time) for row in block_rows if row.date >= first_editable
    )
    return completed, protected, after_boundary, remaining


async def analyze_grid_change(
    db: AsyncSession,
    organization_id: int,
    settings: schemas.TimeslotBulkCreate,
) -> GridChangeAnalysis:
    org_settings = await settings_service.get_settings(db, organization_id)
    school_today = await grid_version_service.school_today(db, organization_id)
    window_days = (
        resolve_repair_window_days(org_settings)
        if org_settings is not None
        else DEFAULT_REPAIR_WINDOW_DAYS
    )
    current = await grid_version_service.resolve_grid(db, organization_id, school_today)
    current_by_id = {block.id: block for block in current.blocks}
    weekdays = {block.day_of_week for block in current.blocks} or set(settings.days_of_week)
    first_editable = first_editable_grid_date(
        school_today,
        org_settings.school_start_date if org_settings else school_today,
        weekdays,
        window_days,
    )

    proposed_configuration = grid_version_service.configuration_from_bulk(settings)
    proposed_signatures = _proposed_signatures(settings)
    proposed_by_signature = {signature: signature for signature in proposed_signatures}
    current_by_day: dict[int, list[tuple[time, time]]] = {}
    for block in current.blocks:
        current_by_day.setdefault(block.day_of_week, []).append((block.start_time, block.end_time))

    daily: list[dict] = []
    for day in range(7):
        current_count = len(current_by_day.get(day, ()))
        proposed_count = sum(1 for signature in proposed_signatures if signature[0] == day)
        daily.append(
            {
                "day_of_week": day,
                "current_lessons": current_count,
                "proposed_lessons": proposed_count,
                "delta": proposed_count - current_count,
            }
        )

    availability_rows = (
        (
            await db.execute(
                select(
                    models.Availability.teacher_id,
                    models.Availability.score,
                    models.Availability.timeslot_id,
                ).where(
                    models.Availability.organization_id == organization_id,
                    models.Availability.timeslot_id.in_(current_by_id.keys()),
                )
            )
        ).all()
        if current_by_id
        else []
    )
    affected_availabilities: dict[int, dict] = {}
    for row in availability_rows:
        block = current_by_id[row.timeslot_id]
        entry = affected_availabilities.get(block.id)
        if entry is None:
            match, proposed, ambiguous = _classify(block, proposed_by_signature)
            entry = {
                "current_timeslot_id": block.id,
                "current": {
                    "day_of_week": block.day_of_week,
                    "start_time": block.start_time,
                    "end_time": block.end_time,
                },
                "proposed": None
                if proposed is None
                else {
                    "day_of_week": proposed[0],
                    "start_time": proposed[1],
                    "end_time": proposed[2],
                },
                "match": match,
                "ambiguous": ambiguous,
                "requires_decision": match != "EXACT",
                "teachers": [],
            }
            affected_availabilities[block.id] = entry
        entry["teachers"].append({"teacher_id": row.teacher_id, "score": row.score})

    constraint_rows = (
        (
            await db.execute(
                select(models.Constraint).where(
                    models.Constraint.organization_id == organization_id,
                    models.Constraint.timeslot_id.in_(current_by_id.keys()),
                )
            )
        )
        .scalars()
        .all()
        if current_by_id
        else []
    )
    affected_constraints: list[dict] = []
    for constraint in constraint_rows:
        block = current_by_id.get(constraint.timeslot_id)
        if block is None:
            continue
        match, proposed, ambiguous = _classify(block, proposed_by_signature)
        affected_constraints.append(
            {
                "constraint_id": constraint.id,
                "current_timeslot_id": block.id,
                "rule_type": constraint.rule_type.value,
                "rule_payload": constraint.rule_payload,
                "proposed": None
                if proposed is None
                else {
                    "day_of_week": proposed[0],
                    "start_time": proposed[1],
                    "end_time": proposed[2],
                },
                "proposed_timeslot_id": None,
                "match": match,
                "ambiguous": ambiguous,
                "requires_decision": match != "EXACT",
            }
        )

    pending_lessons = (
        await db.execute(
            select(
                models.LessonOccurrence.id,
                models.LessonOccurrence.date,
                models.LessonOccurrence.class_id,
                models.LessonOccurrence.subject_id,
            ).where(
                models.LessonOccurrence.organization_id == organization_id,
                models.LessonOccurrence.is_active.is_(True),
                models.LessonOccurrence.revoked_at.is_(None),
                models.LessonOccurrence.status.is_(None),
                models.LessonOccurrence.date < school_today,
            )
        )
    ).all()

    canonical = await _canonical_minutes(
        db,
        organization_id,
        first_editable=first_editable,
        school_today=school_today,
    )
    minutes_completed, minutes_protected, minutes_after, minutes_remaining = (
        canonical
        if canonical is not None
        else await _fallback_minutes(
            db,
            organization_id,
            first_editable=first_editable,
            school_today=school_today,
        )
    )
    minutes_to_place = max(0, minutes_remaining - minutes_protected)

    pending_version = next(
        (
            version
            for version in await grid_version_service.list_grid_versions(db, organization_id)
            if version.state == models.GridVersionState.PENDING
        ),
        None,
    )
    blockers: list[str] = []
    if pending_lessons:
        blockers.append("Existem aulas passadas sem decisão final.")
    if pending_version is not None:
        blockers.append("Já existe uma proposta de grelha pendente.")

    fingerprint_snapshot = canonical_json_value(
        {
            "first_editable_date": first_editable,
            "school_today": school_today,
            "current_version_id": current.version.id if current.version is not None else None,
            "current_blocks": sorted(
                (block.id, block.day_of_week, block.start_time, block.end_time)
                for block in current.blocks
            ),
            "current_configuration": current.version.configuration_json
            if current.version is not None
            else None,
            "proposed_configuration": proposed_configuration,
            "availabilities": sorted(
                (
                    row.timeslot_id,
                    row.teacher_id,
                    row.score,
                )
                for row in availability_rows
            ),
            "constraints": sorted(
                (
                    constraint.id,
                    constraint.rule_type.value,
                    canonical_json_value(constraint.rule_payload),
                )
                for constraint in constraint_rows
            ),
            "minutes_completed": minutes_completed,
            "minutes_protected": minutes_protected,
            "minutes_planned_after_boundary": minutes_after,
            "minutes_remaining": minutes_remaining,
            "lessons_without_closure": sorted(row.id for row in pending_lessons),
        }
    )
    return GridChangeAnalysis(
        first_editable_date=first_editable,
        current_configuration=current.version.configuration_json
        if current.version is not None
        else None,
        proposed_configuration=proposed_configuration,
        daily=tuple(daily),
        affected_availabilities=tuple(affected_availabilities.values()),
        affected_constraints=tuple(affected_constraints),
        lessons_without_closure=tuple(
            {
                "occurrence_id": row.id,
                "date": row.date,
                "class_id": row.class_id,
                "subject_id": row.subject_id,
            }
            for row in pending_lessons
        ),
        minutes_completed=minutes_completed,
        minutes_protected=minutes_protected,
        minutes_planned_after_boundary=minutes_after,
        minutes_remaining=minutes_to_place,
        fingerprint=sha256_json(fingerprint_snapshot),
        pending_grid_version_id=None if pending_version is None else pending_version.id,
        can_propose=not blockers,
        blockers=tuple(blockers),
    )


async def preview_grid_change(
    db: AsyncSession,
    organization_id: int,
    payload: schemas.GridChangePreviewRequest,
) -> schemas.GridChangePreviewResponse:
    analysis = await analyze_grid_change(db, organization_id, payload.timeslots)
    return analysis.to_schema()


async def _idempotent_proposal(
    db: AsyncSession,
    organization_id: int,
    idempotency_key: str | None,
) -> schemas.GridChangeProposalResponse | None:
    if idempotency_key is None:
        return None
    job = await db.scalar(
        select(models.ScheduleGenerationJob).where(
            models.ScheduleGenerationJob.organization_id == organization_id,
            models.ScheduleGenerationJob.idempotency_key == idempotency_key,
        )
    )
    if job is None or job.grid_version_id is None:
        return None
    version = await grid_version_service.get_grid_version(db, organization_id, job.grid_version_id)
    if version is None:
        return None
    return schemas.GridChangeProposalResponse(
        grid_version_id=version.id,
        job_id=job.id,
        strategy="GRID_CHANGE",
        effective_date=version.effective_date,
        first_editable_date=version.effective_date,
        status=job.job_status.value,
        created=False,
    )


def _copy_target(
    entry: dict,
    signature_to_id: dict[ProposedSignature, int],
) -> int | None:
    proposed = entry.get("proposed")
    if proposed is None:
        return None
    return signature_to_id.get(
        (proposed["day_of_week"], proposed["start_time"], proposed["end_time"])
    )


async def propose_grid_change(
    db: AsyncSession,
    organization_id: int,
    payload: schemas.GridChangeProposeRequest,
    *,
    membership_id: int,
) -> schemas.GridChangeProposalResponse:
    existing = await _idempotent_proposal(db, organization_id, payload.idempotency_key)
    if existing is not None:
        return existing

    analysis = await analyze_grid_change(db, organization_id, payload.timeslots)
    if payload.fingerprint != analysis.fingerprint:
        raise GridChangeError(
            "GRID_CHANGE_STALE",
            "A análise mudou desde a pré-visualização. Repita a pré-visualização.",
        )
    if not analysis.can_propose:
        raise GridChangeError(
            "GRID_CHANGE_BLOCKED",
            " ".join(analysis.blockers) or "A alteração da grelha não pode ser proposta.",
        )

    availability_entries = {
        entry["current_timeslot_id"]: entry for entry in analysis.affected_availabilities
    }
    constraint_entries = list(analysis.affected_constraints)
    affected_ids = set(availability_entries) | {
        entry["current_timeslot_id"] for entry in constraint_entries
    }
    decisions: dict[int, str] = {}
    for decision in payload.decisions:
        if decision.current_timeslot_id in decisions:
            raise GridChangeError(
                "GRID_CHANGE_DECISION_DUPLICATE",
                f"Existe mais de uma decisão para o bloco {decision.current_timeslot_id}.",
            )
        decisions[decision.current_timeslot_id] = decision.action

    required_ids = {
        entry["current_timeslot_id"]
        for entry in availability_entries.values()
        if entry["requires_decision"]
    } | {entry["current_timeslot_id"] for entry in constraint_entries if entry["requires_decision"]}
    missing = sorted(required_ids - set(decisions))
    if missing:
        raise GridChangeError(
            "GRID_CHANGE_DECISION_REQUIRED",
            "Faltam decisões para os blocos afetados: "
            + ", ".join(str(value) for value in missing)
            + ".",
        )
    unknown = sorted(set(decisions) - affected_ids)
    if unknown:
        raise GridChangeError(
            "GRID_CHANGE_DECISION_UNKNOWN",
            "Existem decisões para blocos que não estão afetados: "
            + ", ".join(str(value) for value in unknown)
            + ".",
        )

    version = models.GridVersion(
        organization_id=organization_id,
        effective_date=analysis.first_editable_date,
        state=models.GridVersionState.PENDING,
        configuration_json=analysis.proposed_configuration,
    )
    db.add(version)
    await db.flush()

    signature_to_id: dict[ProposedSignature, int] = {}
    for day, start, end in _proposed_signatures(payload.timeslots):
        slot = models.Timeslot(
            organization_id=organization_id,
            grid_version_id=version.id,
            day_of_week=day,
            start_time=start,
            end_time=end,
        )
        db.add(slot)
        await db.flush()
        signature_to_id[(day, start, end)] = slot.id

    for timeslot_id, entry in availability_entries.items():
        if entry["match"] != "EXACT" and decisions.get(timeslot_id) != "COPY":
            continue
        target_id = _copy_target(entry, signature_to_id)
        if target_id is None:
            raise GridChangeError(
                "GRID_CHANGE_DECISION_INVALID",
                f"O bloco {timeslot_id} não tem destino na grelha proposta.",
            )
        for teacher in entry["teachers"]:
            db.add(
                models.Availability(
                    organization_id=organization_id,
                    teacher_id=teacher["teacher_id"],
                    timeslot_id=target_id,
                    score=teacher["score"],
                )
            )

    for entry in constraint_entries:
        timeslot_id = entry["current_timeslot_id"]
        if entry["match"] != "EXACT" and decisions.get(timeslot_id) != "COPY":
            continue
        target_id = _copy_target(entry, signature_to_id)
        if target_id is None:
            raise GridChangeError(
                "GRID_CHANGE_DECISION_INVALID",
                f"A regra {entry['constraint_id']} não tem destino na grelha proposta.",
            )
        rule = entry["rule_payload"]
        db.add(
            models.Constraint(
                organization_id=organization_id,
                rule_type=models.ConstraintType(entry["rule_type"]),
                class_id=rule.get("class_id"),
                subject_id=rule.get("subject_id"),
                teacher_id=rule.get("teacher_id"),
                room_id=rule.get("room_id"),
                timeslot_id=target_id,
                constraint_date=None,
                day_of_week=None,
            )
        )
    await db.flush()

    generation = SchedulerGenerationService(db)
    try:
        selection = await generation.select_grid_change_strategy(organization_id)
    except (GenerationConfigurationError, GenerationSelectionError) as exc:
        raise GridChangeError(exc.code, str(exc)) from exc
    selection = replace(selection, grid_version_id=version.id)

    try:
        handle = await SchedulerJobService(db).create_or_get_job(
            selection,
            requested_by_membership_id=membership_id,
            idempotency_key=payload.idempotency_key,
        )
    except SchedulerJobError as exc:
        raise GridChangeError(exc.code, str(exc)) from exc

    return schemas.GridChangeProposalResponse(
        grid_version_id=version.id,
        job_id=handle.job.id,
        strategy="GRID_CHANGE",
        effective_date=version.effective_date,
        first_editable_date=analysis.first_editable_date,
        status=handle.job.job_status.value,
        created=handle.created,
    )


async def pending_grid_change(
    db: AsyncSession,
    organization_id: int,
) -> schemas.GridChangePendingResponse | None:
    versions = await grid_version_service.list_grid_versions(db, organization_id)
    pending = next(
        (version for version in versions if version.state == models.GridVersionState.PENDING),
        None,
    )
    if pending is None:
        return None
    blocks = await grid_version_service.get_version_blocks(db, organization_id, pending.id)
    job = await db.scalar(
        select(models.ScheduleGenerationJob)
        .where(
            models.ScheduleGenerationJob.organization_id == organization_id,
            models.ScheduleGenerationJob.grid_version_id == pending.id,
        )
        .order_by(models.ScheduleGenerationJob.id.desc())
        .limit(1)
    )
    return schemas.GridChangePendingResponse(
        grid_version_id=pending.id,
        effective_date=pending.effective_date,
        configuration=pending.configuration_json,
        job_id=None if job is None else job.id,
        job_status=None if job is None else job.job_status.value,
        blocks=[
            schemas.GridBlockRead(
                id=block.id,
                day_of_week=block.day_of_week,
                start_time=block.start_time,
                end_time=block.end_time,
            )
            for block in blocks
        ],
    )
