from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.core.task_keys import resolve_repair_window_days
from app.scheduler.domain.calendar import first_editable_grid_date
from app.services import grid_version_service
from app.services.scheduler_serialization import (
    canonical_json_bytes,
    canonical_json_value,
    sha256_json,
)


class SchedulerFingerprintError(RuntimeError):
    pass


def _constraint_payload(row) -> dict:
    values = {
        "class_id": row.class_id,
        "subject_id": row.subject_id,
        "teacher_id": row.teacher_id,
        "room_id": row.room_id,
        "timeslot_id": row.timeslot_id,
        "date": row.constraint_date,
        "day_of_week": row.day_of_week,
    }
    return {key: value for key, value in values.items() if value is not None}


@dataclass(frozen=True)
class SchedulerFingerprint:
    value: str
    snapshot: dict


@dataclass(frozen=True)
class DebtBasisFingerprint:
    value: str
    snapshot: dict
    unresolved_debt_minutes: int


@dataclass(frozen=True)
class RepairPolicySnapshot:
    value: str
    snapshot: dict
    editable_start_date: date


class SchedulerFingerprintService:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def repair_policy_snapshot(
        self,
        organization_id: int,
        school_year_id: int,
        *,
        now: datetime | None = None,
    ) -> RepairPolicySnapshot:
        school_year = await self._db.scalar(
            select(models.SchedulerSchoolYear).where(
                models.SchedulerSchoolYear.id == school_year_id,
                models.SchedulerSchoolYear.organization_id == organization_id,
            )
        )
        settings = await self._db.scalar(
            select(models.OrganizationSettings).where(
                models.OrganizationSettings.organization_id == organization_id
            )
        )
        if school_year is None:
            raise SchedulerFingerprintError("Scheduler school year was not found.")
        if settings is None:
            raise SchedulerFingerprintError("Organization scheduler settings were not found.")

        instant = now or datetime.now(UTC)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SchedulerFingerprintError("Repair policy snapshot time must be timezone-aware.")
        try:
            school_timezone = ZoneInfo(school_year.timezone)
        except ZoneInfoNotFoundError as exc:
            raise SchedulerFingerprintError(
                f"Unknown school timezone: {school_year.timezone}"
            ) from exc

        if (
            settings.repair_stability_window_days is not None
            and settings.repair_stability_window_days < 0
        ):
            raise SchedulerFingerprintError("Repair stability window cannot be negative.")
        stability_window_days = resolve_repair_window_days(settings)
        school_today = instant.astimezone(school_timezone).date()
        resolved_grid = await grid_version_service.resolve_grid(
            self._db, organization_id, school_today
        )
        grid_days = sorted({block.day_of_week for block in resolved_grid.blocks})
        editable_start_date = first_editable_grid_date(
            school_today,
            school_year.start_date,
            set(grid_days),
            stability_window_days,
        )
        snapshot = canonical_json_value(
            {
                "repair_stability_window_days": stability_window_days,
                "school_timezone": school_year.timezone,
                "school_today": school_today,
                "grid_days": grid_days,
                "editable_start_date": editable_start_date,
            }
        )
        return RepairPolicySnapshot(
            value=sha256_json(snapshot),
            snapshot=snapshot,
            editable_start_date=editable_start_date,
        )

    async def generation_input_fingerprint(
        self,
        organization_id: int,
        school_year_id: int,
        strategy: models.ScheduleGenerationStrategy,
        grid_version_id: int | None = None,
    ) -> SchedulerFingerprint:
        snapshot = await self.generation_input_snapshot(
            organization_id,
            school_year_id,
            strategy,
            grid_version_id=grid_version_id,
        )
        return SchedulerFingerprint(value=sha256_json(snapshot), snapshot=snapshot)

    async def generation_input_snapshot(
        self,
        organization_id: int,
        school_year_id: int,
        strategy: models.ScheduleGenerationStrategy,
        grid_version_id: int | None = None,
    ) -> dict:
        school_year = await self._db.scalar(
            select(models.SchedulerSchoolYear).where(
                models.SchedulerSchoolYear.id == school_year_id,
                models.SchedulerSchoolYear.organization_id == organization_id,
            )
        )
        state = await self._db.scalar(
            select(models.SchedulerSchoolYearState).where(
                models.SchedulerSchoolYearState.school_year_id == school_year_id,
                models.SchedulerSchoolYearState.organization_id == organization_id,
            )
        )
        if school_year is None or state is None:
            raise SchedulerFingerprintError("Scheduler school-year state was not found.")

        class_rows = (
            await self._db.execute(
                select(
                    models.Class.id,
                    models.Class.size,
                    models.Class.grade_level,
                    models.Class.start_year,
                    models.Class.end_year,
                    models.Class.course_id,
                ).where(
                    models.Class.organization_id == organization_id,
                    models.Class.is_archived.is_(False),
                )
            )
        ).all()
        class_ids = {row.id for row in class_rows}

        assignment_rows = (
            (
                await self._db.execute(
                    select(
                        models.ClassSubjectLink.id,
                        models.ClassSubjectLink.class_id,
                        models.ClassSubjectLink.subject_id,
                        models.ClassSubjectLink.grade_level,
                        models.ClassSubjectLink.teacher_id,
                    ).where(
                        models.ClassSubjectLink.organization_id == organization_id,
                        models.ClassSubjectLink.class_id.in_(class_ids),
                    )
                )
            ).all()
            if class_ids
            else []
        )
        subject_ids = {row.subject_id for row in assignment_rows}
        teacher_ids = {row.teacher_id for row in assignment_rows if row.teacher_id is not None}
        teacher_rows = (
            (
                await self._db.execute(
                    select(models.Teacher.id)
                    .join(
                        models.OrganizationMembership,
                        models.OrganizationMembership.id
                        == models.Teacher.organization_membership_id,
                    )
                    .where(
                        models.Teacher.organization_id == organization_id,
                        models.OrganizationMembership.organization_id == organization_id,
                        models.OrganizationMembership.lifecycle_status
                        == models.MembershipLifecycleStatus.active,
                        models.OrganizationMembership.can_teach.is_(True),
                        models.Teacher.id.in_(teacher_ids),
                    )
                )
            ).all()
            if teacher_ids
            else []
        )
        eligible_teacher_ids = {row.id for row in teacher_rows}
        qualification_rows = (
            (
                await self._db.execute(
                    select(
                        models.teacher_subject_link.c.teacher_id,
                        models.teacher_subject_link.c.subject_id,
                    ).where(
                        models.teacher_subject_link.c.organization_id == organization_id,
                        models.teacher_subject_link.c.teacher_id.in_(eligible_teacher_ids),
                        models.teacher_subject_link.c.subject_id.in_(subject_ids),
                    )
                )
            ).all()
            if eligible_teacher_ids and subject_ids
            else []
        )

        subject_rows = (
            (
                await self._db.execute(
                    select(models.Subject.id, models.Subject.required_room_type).where(
                        models.Subject.organization_id == organization_id,
                        models.Subject.is_archived.is_(False),
                        models.Subject.id.in_(subject_ids),
                    )
                )
            ).all()
            if subject_ids
            else []
        )
        module_rows = (
            (
                await self._db.execute(
                    select(
                        models.Module.id,
                        models.Module.subject_id,
                        models.Module.required_minutes,
                        models.Module.order,
                    ).where(
                        models.Module.organization_id == organization_id,
                        models.Module.subject_id.in_(subject_ids),
                    )
                )
            ).all()
            if subject_ids
            else []
        )
        module_ids = {row.id for row in module_rows}
        progress_rows = (
            (
                await self._db.execute(
                    select(
                        models.ProgressLedgerEntry.class_id,
                        models.ProgressLedgerEntry.module_id,
                        func.sum(models.ProgressLedgerEntry.completed_minutes_delta).label(
                            "completed_minutes"
                        ),
                    )
                    .where(
                        models.ProgressLedgerEntry.organization_id == organization_id,
                        models.ProgressLedgerEntry.class_id.in_(class_ids),
                        models.ProgressLedgerEntry.module_id.in_(module_ids),
                    )
                    .group_by(
                        models.ProgressLedgerEntry.class_id,
                        models.ProgressLedgerEntry.module_id,
                    )
                )
            ).all()
            if class_ids and module_ids
            else []
        )

        versions = await grid_version_service.list_grid_versions(self._db, organization_id)
        included = [
            version
            for version in versions
            if version.state == models.GridVersionState.ACTIVE
            or (grid_version_id is not None and version.id == grid_version_id)
        ]
        if grid_version_id is not None and all(
            version.id != grid_version_id for version in included
        ):
            raise SchedulerFingerprintError("Grid version was not found.")
        included.sort(key=lambda version: (version.effective_date, version.id))

        grid_rows: list[dict] = []
        for index, version in enumerate(included):
            next_effective = (
                included[index + 1].effective_date if index + 1 < len(included) else None
            )
            valid_to = (
                (next_effective - timedelta(days=1)).isoformat()
                if next_effective is not None
                else None
            )
            blocks = await grid_version_service.get_version_blocks(
                self._db, organization_id, version.id
            )
            for block in blocks:
                grid_rows.append(
                    {
                        "id": block.id,
                        "day_of_week": block.day_of_week,
                        "start_time": block.start_time,
                        "end_time": block.end_time,
                        "grid_version_id": version.id,
                        "valid_from": version.effective_date.isoformat(),
                        "valid_to": valid_to,
                    }
                )
        if not grid_rows and grid_version_id is None:
            # ponytail: legacy orgs without versioned blocks keep the flat grid.
            resolved = await grid_version_service.resolve_grid(
                self._db, organization_id, school_year.start_date
            )
            grid_version = resolved.version
            grid_rows = [
                {
                    "id": block.id,
                    "day_of_week": block.day_of_week,
                    "start_time": block.start_time,
                    "end_time": block.end_time,
                    "grid_version_id": None,
                    "valid_from": None,
                    "valid_to": None,
                }
                for block in resolved.blocks
            ]
        elif grid_version_id is not None:
            grid_version = next(version for version in included if version.id == grid_version_id)
        else:
            grid_version = await grid_version_service.resolve_grid_version(
                self._db,
                organization_id,
                await grid_version_service.school_today(self._db, organization_id),
            )
        availability_rows = (
            (
                await self._db.execute(
                    select(
                        models.Availability.teacher_id,
                        models.Availability.timeslot_id,
                        models.Availability.score,
                    ).where(
                        models.Availability.organization_id == organization_id,
                        models.Availability.teacher_id.in_(eligible_teacher_ids),
                    )
                )
            ).all()
            if eligible_teacher_ids
            else []
        )
        room_rows = (
            await self._db.execute(
                select(
                    models.Room.id,
                    models.Room.capacity,
                    models.Room.type,
                ).where(
                    models.Room.organization_id == organization_id,
                    models.Room.is_archived.is_(False),
                )
            )
        ).all()
        event_rows = (
            await self._db.execute(
                select(
                    models.SchoolCalendarEvent.id,
                    models.SchoolCalendarEvent.start_date,
                    models.SchoolCalendarEvent.end_date,
                    models.SchoolCalendarEvent.event_type,
                    models.SchoolCalendarEvent.source,
                    models.SchoolCalendarEvent.school_year_start_year,
                ).where(
                    models.SchoolCalendarEvent.organization_id == organization_id,
                    models.SchoolCalendarEvent.end_date >= school_year.start_date,
                    models.SchoolCalendarEvent.start_date <= school_year.hard_end_date,
                    or_(
                        models.SchoolCalendarEvent.school_year_start_year.is_(None),
                        models.SchoolCalendarEvent.school_year_start_year
                        == school_year.start_date.year,
                    ),
                )
            )
        ).all()
        event_class_rows = []
        if event_rows:
            event_class_rows = (
                await self._db.execute(
                    select(
                        models.SchoolCalendarEventClass.calendar_event_id,
                        models.SchoolCalendarEventClass.class_id,
                    )
                    .where(
                        models.SchoolCalendarEventClass.organization_id == organization_id,
                        models.SchoolCalendarEventClass.calendar_event_id.in_(
                            [row.id for row in event_rows]
                        ),
                    )
                    .order_by(
                        models.SchoolCalendarEventClass.calendar_event_id,
                        models.SchoolCalendarEventClass.class_id,
                    )
                )
            ).all()
        class_ids_by_event: dict[int, list[int]] = {}
        for link in event_class_rows:
            class_ids_by_event.setdefault(link.calendar_event_id, []).append(link.class_id)
        constraint_rows = (
            await self._db.execute(
                select(
                    models.Constraint.id,
                    models.Constraint.rule_type,
                    models.Constraint.class_id,
                    models.Constraint.subject_id,
                    models.Constraint.teacher_id,
                    models.Constraint.room_id,
                    models.Constraint.timeslot_id,
                    models.Constraint.constraint_date,
                    models.Constraint.day_of_week,
                ).where(models.Constraint.organization_id == organization_id)
            )
        ).all()
        grid_settings = await self._db.scalar(
            select(models.OrganizationGridSettings).where(
                models.OrganizationGridSettings.organization_id == organization_id
            )
        )

        snapshot = {
            "organization_id": organization_id,
            "school_year_id": school_year_id,
            "strategy": strategy,
            "quality_policy_version": "baseline-v1",
            "timezone": school_year.timezone,
            "start_date": school_year.start_date,
            "hard_end_date": school_year.hard_end_date,
            "scheduler_state_version": state.scheduler_state_version,
            "approved_scheduler_state_version": state.approved_scheduler_state_version,
            "timetable_grid": [dict(row) for row in sorted(grid_rows, key=lambda row: row["id"])],
            "grid_versions": [
                {
                    "id": version.id,
                    "effective_date": version.effective_date,
                    "state": version.state.value,
                }
                for version in included
            ],
            "grid_version": None
            if grid_version is None
            else {
                "id": grid_version.id,
                "effective_date": grid_version.effective_date,
                "state": grid_version.state.value,
            },
            "calendar_events": [
                {
                    "start_date": row.start_date,
                    "end_date": row.end_date,
                    "event_type": row.event_type,
                    "source": row.source,
                    "school_year_start_year": row.school_year_start_year,
                    "class_ids": class_ids_by_event.get(row.id, []),
                }
                for row in sorted(
                    event_rows,
                    key=lambda row: (
                        row.start_date,
                        row.end_date,
                        row.event_type.value,
                        row.source.value,
                        tuple(class_ids_by_event.get(row.id, [])),
                    ),
                )
            ],
            "constraints": [
                {
                    "rule_type": row.rule_type,
                    "rule_payload": _constraint_payload(row),
                }
                for row in sorted(
                    constraint_rows,
                    key=lambda row: (
                        row.rule_type.value,
                        canonical_json_bytes(_constraint_payload(row)),
                    ),
                )
            ],
            "lunch_rules": None
            if grid_settings is None
            else {
                "window_start": grid_settings.lunch_window_start,
                "window_end": grid_settings.lunch_window_end,
                "minimum_minutes": grid_settings.lunch_min_duration_minutes,
            },
            "classes": [
                {
                    "id": row.id,
                    "size": row.size,
                    "grade_level": row.grade_level,
                    "start_year": row.start_year,
                    "end_year": row.end_year,
                    "course_id": row.course_id,
                }
                for row in sorted(class_rows, key=lambda row: row.id)
            ],
            "subjects": [
                {"id": row.id, "required_room_type": row.required_room_type}
                for row in sorted(subject_rows, key=lambda row: row.id)
            ],
            "teachers": [{"id": row.id} for row in sorted(teacher_rows, key=lambda row: row.id)],
            "teacher_subject_eligibility": [
                {
                    "teacher_id": row.teacher_id,
                    "subject_id": row.subject_id,
                }
                for row in sorted(
                    qualification_rows,
                    key=lambda row: (row.teacher_id, row.subject_id),
                )
            ],
            "class_subject_requirements": [
                {
                    "class_id": row.class_id,
                    "subject_id": row.subject_id,
                    "grade_level": row.grade_level,
                    "teacher_id": row.teacher_id,
                }
                for row in sorted(
                    assignment_rows,
                    key=lambda row: (
                        row.class_id,
                        row.subject_id,
                        row.grade_level,
                        -1 if row.teacher_id is None else row.teacher_id,
                    ),
                )
            ],
            "teacher_availability": [
                {
                    "teacher_id": row.teacher_id,
                    "timeslot_id": row.timeslot_id,
                    "score": row.score,
                }
                for row in sorted(
                    availability_rows,
                    key=lambda row: (row.teacher_id, row.timeslot_id),
                )
            ],
            "rooms": [
                {"id": row.id, "capacity": row.capacity, "type": row.type}
                for row in sorted(room_rows, key=lambda row: row.id)
            ],
            "module_accounting": [
                {
                    "id": row.id,
                    "subject_id": row.subject_id,
                    "required_minutes": row.required_minutes,
                    "sequence": row.order,
                }
                for row in sorted(module_rows, key=lambda row: row.id)
            ],
            "class_progress": [
                {
                    "class_id": row.class_id,
                    "module_id": row.module_id,
                    "completed_minutes": row.completed_minutes,
                }
                for row in sorted(
                    progress_rows,
                    key=lambda row: (row.class_id, row.module_id),
                )
            ],
        }

        if strategy in (
            models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR,
            models.ScheduleGenerationStrategy.GRID_CHANGE,
        ):
            active_rows = (
                await self._db.execute(
                    select(
                        models.ActiveScheduleBlock,
                        models.ScheduleDraftBlock.module_sequence_index.label(
                            "module_sequence_index"
                        ),
                        models.LessonLog.status.label("lesson_log_status"),
                        models.PlannedRecoveryLink.debt_occurrence_id,
                        models.PlannedRecoveryLink.debt_occurrence_revision,
                    )
                    .join(
                        models.ScheduleDraftBlock,
                        and_(
                            models.ScheduleDraftBlock.id
                            == models.ActiveScheduleBlock.source_draft_block_id,
                            models.ScheduleDraftBlock.organization_id
                            == models.ActiveScheduleBlock.organization_id,
                            models.ScheduleDraftBlock.school_year_id
                            == models.ActiveScheduleBlock.school_year_id,
                        ),
                    )
                    .outerjoin(
                        models.LessonLog,
                        and_(
                            models.LessonLog.active_schedule_block_id
                            == models.ActiveScheduleBlock.id,
                            models.LessonLog.organization_id
                            == models.ActiveScheduleBlock.organization_id,
                        ),
                    )
                    .outerjoin(
                        models.PlannedRecoveryLink,
                        and_(
                            models.PlannedRecoveryLink.planned_active_block_id
                            == models.ActiveScheduleBlock.id,
                            models.PlannedRecoveryLink.organization_id
                            == models.ActiveScheduleBlock.organization_id,
                            models.PlannedRecoveryLink.school_year_id
                            == models.ActiveScheduleBlock.school_year_id,
                        ),
                    )
                    .where(
                        models.ActiveScheduleBlock.organization_id == organization_id,
                        models.ActiveScheduleBlock.school_year_id == school_year_id,
                        models.ActiveScheduleBlock.status
                        == (models.ActiveScheduleBlockStatus.ACTIVE),
                    )
                )
            ).all()
            snapshot["active_schedule"] = [
                {
                    "id": row.id,
                    "schedule_version_id": row.schedule_version_id,
                    "stable_block_key": row.stable_block_key,
                    "class_id": row.class_id,
                    "subject_id": row.subject_id,
                    "teacher_id": row.teacher_id,
                    "room_id": row.room_id,
                    "date": row.date,
                    "timeslot_id": row.timeslot_id,
                    "duration_minutes": row.duration_minutes,
                    "module_sequence_index": module_sequence_index,
                    "is_recovery_block": row.is_recovery_block,
                    "recovery_source_occurrence_id": debt_occurrence_id,
                    "recovery_source_occurrence_revision": debt_occurrence_revision,
                    "lesson_log_status": lesson_log_status,
                }
                for (
                    row,
                    module_sequence_index,
                    lesson_log_status,
                    debt_occurrence_id,
                    debt_occurrence_revision,
                ) in sorted(
                    active_rows,
                    key=lambda pair: pair[0].id,
                )
            ]

        return canonical_json_value(snapshot)

    async def debt_basis_fingerprint(
        self,
        organization_id: int,
        school_year_id: int,
    ) -> DebtBasisFingerprint | None:
        snapshot = await self.debt_basis_snapshot(organization_id, school_year_id)
        unresolved = sum(item["unresolved_debt_minutes"] for item in snapshot["items"])
        if unresolved <= 0:
            return None
        return DebtBasisFingerprint(
            value=sha256_json(snapshot),
            snapshot=snapshot,
            unresolved_debt_minutes=unresolved,
        )

    async def debt_basis_snapshot(
        self,
        organization_id: int,
        school_year_id: int,
    ) -> dict:
        school_year = await self._db.scalar(
            select(models.SchedulerSchoolYear).where(
                models.SchedulerSchoolYear.id == school_year_id,
                models.SchedulerSchoolYear.organization_id == organization_id,
            )
        )
        if school_year is None:
            raise SchedulerFingerprintError("Scheduler school year was not found.")

        debt_rows = (
            await self._db.execute(
                select(
                    models.LessonOccurrence,
                    models.LessonOccurrence.planned_timeslot_id.label("source_timeslot_id"),
                    models.Timeslot.start_time.label("source_start_time"),
                    models.Timeslot.end_time.label("source_end_time"),
                    models.LessonOccurrence.class_id.label("source_class_id"),
                    models.LessonOccurrence.subject_id.label("source_subject_id"),
                    models.LessonOccurrence.planned_teacher_id.label("source_teacher_id"),
                )
                .outerjoin(
                    models.Timeslot,
                    and_(
                        models.Timeslot.id == models.LessonOccurrence.planned_timeslot_id,
                        models.Timeslot.organization_id == models.LessonOccurrence.organization_id,
                    ),
                )
                .where(
                    models.LessonOccurrence.organization_id == organization_id,
                    models.LessonOccurrence.is_active.is_(True),
                    models.LessonOccurrence.status.in_(
                        (
                            models.LessonOccurrenceStatus.GAP,
                            models.LessonOccurrenceStatus.SUBSTITUTED,
                        )
                    ),
                    models.LessonOccurrence.date >= school_year.start_date,
                    models.LessonOccurrence.date <= school_year.hard_end_date,
                )
            )
        ).all()
        occurrence_ids = [row.LessonOccurrence.id for row in debt_rows]

        links = []
        if occurrence_ids:
            links = (
                await self._db.execute(
                    select(
                        models.PlannedRecoveryLink,
                        models.ActiveScheduleBlock.status.label("active_block_status"),
                    )
                    .outerjoin(
                        models.ActiveScheduleBlock,
                        and_(
                            models.ActiveScheduleBlock.id
                            == models.PlannedRecoveryLink.planned_active_block_id,
                            models.ActiveScheduleBlock.organization_id
                            == models.PlannedRecoveryLink.organization_id,
                            models.ActiveScheduleBlock.school_year_id
                            == models.PlannedRecoveryLink.school_year_id,
                        ),
                    )
                    .where(
                        models.PlannedRecoveryLink.organization_id == organization_id,
                        models.PlannedRecoveryLink.school_year_id == school_year_id,
                        models.PlannedRecoveryLink.debt_occurrence_id.in_(occurrence_ids),
                    )
                )
            ).all()

        links_by_occurrence: dict[int, list] = {}
        for link, active_block_status in links:
            links_by_occurrence.setdefault(link.debt_occurrence_id, []).append(
                (link, active_block_status)
            )

        items = []
        for row in sorted(debt_rows, key=lambda item: item.LessonOccurrence.id):
            occurrence = row.LessonOccurrence
            if occurrence.planned_hours > 0:
                declared_minutes = max(0, int(round(float(occurrence.planned_hours) * 60)))
            elif row.source_start_time is not None and row.source_end_time is not None:
                start_minutes = row.source_start_time.hour * 60 + row.source_start_time.minute
                end_minutes = row.source_end_time.hour * 60 + row.source_end_time.minute
                declared_minutes = max(0, end_minutes - start_minutes)
            else:
                declared_minutes = max(0, int(round(float(occurrence.hours_given or 0) * 60)))
            delivered_minutes = 0
            active_planned_minutes = 0
            ordered_links = sorted(
                links_by_occurrence.get(occurrence.id, []),
                key=lambda pair: (
                    pair[0].status.value,
                    -1
                    if pair[0].planned_active_block_id is None
                    else pair[0].planned_active_block_id,
                    -1
                    if pair[0].planned_draft_block_id is None
                    else pair[0].planned_draft_block_id,
                    pair[0].planned_recovery_minutes,
                ),
            )
            for link, active_block_status in ordered_links:
                if link.status == models.PlannedRecoveryLinkStatus.DELIVERED:
                    delivered_minutes += link.delivered_recovery_minutes
                elif (
                    link.status == models.PlannedRecoveryLinkStatus.PLANNED
                    and link.planned_active_block_id is not None
                    and active_block_status == models.ActiveScheduleBlockStatus.ACTIVE
                ):
                    active_planned_minutes += link.planned_recovery_minutes

            unresolved_minutes = max(
                0,
                declared_minutes - delivered_minutes - active_planned_minutes,
            )
            items.append(
                {
                    "occurrence_id": occurrence.id,
                    "occurrence_revision": occurrence.revision,
                    "debt_status": occurrence.status,
                    "source_planned_block_id": occurrence.active_schedule_block_id,
                    "class_id": occurrence.class_id or row.source_class_id,
                    "subject_id": occurrence.subject_id or row.source_subject_id,
                    "teacher_id": occurrence.planned_teacher_id or row.source_teacher_id,
                    "original_planned_date": occurrence.date,
                    "original_timeslot_id": (
                        occurrence.planned_timeslot_id or row.source_timeslot_id
                    ),
                    "declared_debt_minutes": declared_minutes,
                    "delivered_recovery_minutes": delivered_minutes,
                    "active_planned_recovery_minutes": active_planned_minutes,
                    "unresolved_debt_minutes": unresolved_minutes,
                }
            )

        return canonical_json_value(
            {
                "organization_id": organization_id,
                "school_year_id": school_year_id,
                "items": items,
            }
        )
