from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.core.task_keys import resolve_repair_window_days
from app.services.scheduler_serialization import (
    canonical_json_bytes,
    canonical_json_value,
    sha256_json,
)


class SchedulerFingerprintError(RuntimeError):
    pass


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

        instant = now or datetime.now(timezone.utc)
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
            raise SchedulerFingerprintError(
                "Repair stability window cannot be negative."
            )
        stability_window_days = resolve_repair_window_days(settings)
        school_today = instant.astimezone(school_timezone).date()
        editable_start_date = max(
            school_year.start_date,
            school_today + timedelta(days=stability_window_days),
        )
        snapshot = canonical_json_value(
            {
                "repair_stability_window_days": stability_window_days,
                "school_timezone": school_year.timezone,
                "school_today": school_today,
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
    ) -> SchedulerFingerprint:
        snapshot = await self.generation_input_snapshot(
            organization_id,
            school_year_id,
            strategy,
        )
        return SchedulerFingerprint(value=sha256_json(snapshot), snapshot=snapshot)

    async def generation_input_snapshot(
        self,
        organization_id: int,
        school_year_id: int,
        strategy: models.ScheduleGenerationStrategy,
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
        ).all() if class_ids else []
        subject_ids = {row.subject_id for row in assignment_rows}
        teacher_ids = {
            row.teacher_id for row in assignment_rows if row.teacher_id is not None
        }
        teacher_rows = (
            await self._db.execute(
                select(models.Teacher.id).where(
                    models.Teacher.organization_id == organization_id,
                    models.Teacher.id.in_(teacher_ids),
                )
            )
        ).all() if teacher_ids else []
        qualification_rows = (
            await self._db.execute(
                select(
                    models.teacher_subject_link.c.teacher_id,
                    models.teacher_subject_link.c.subject_id,
                ).where(
                    models.teacher_subject_link.c.organization_id == organization_id,
                    models.teacher_subject_link.c.teacher_id.in_(teacher_ids),
                    models.teacher_subject_link.c.subject_id.in_(subject_ids),
                )
            )
        ).all() if teacher_ids and subject_ids else []

        subject_rows = (
            await self._db.execute(
                select(models.Subject.id, models.Subject.required_room_type).where(
                    models.Subject.organization_id == organization_id,
                    models.Subject.id.in_(subject_ids),
                )
            )
        ).all() if subject_ids else []
        module_rows = (
            await self._db.execute(
                select(
                    models.Module.id,
                    models.Module.subject_id,
                    models.Module.hours_total,
                    models.Module.order,
                ).where(
                    models.Module.organization_id == organization_id,
                    models.Module.subject_id.in_(subject_ids),
                )
            )
        ).all() if subject_ids else []
        module_ids = {row.id for row in module_rows}
        progress_rows = (
            await self._db.execute(
                select(
                    models.ClassProgress.class_id,
                    models.ClassProgress.module_id,
                    models.ClassProgress.hours_completed,
                ).where(
                    models.ClassProgress.organization_id == organization_id,
                    models.ClassProgress.class_id.in_(class_ids),
                    models.ClassProgress.module_id.in_(module_ids),
                )
            )
        ).all() if class_ids and module_ids else []

        timeslot_rows = (
            await self._db.execute(
                select(
                    models.Timeslot.id,
                    models.Timeslot.day_of_week,
                    models.Timeslot.start_time,
                    models.Timeslot.end_time,
                ).where(models.Timeslot.organization_id == organization_id)
            )
        ).all()
        availability_rows = (
            await self._db.execute(
                select(
                    models.Availability.teacher_id,
                    models.Availability.timeslot_id,
                    models.Availability.score,
                ).where(
                    models.Availability.organization_id == organization_id,
                    models.Availability.teacher_id.in_(teacher_ids),
                )
            )
        ).all() if teacher_ids else []
        room_rows = (
            await self._db.execute(
                select(
                    models.Room.id,
                    models.Room.capacity,
                    models.Room.type,
                ).where(models.Room.organization_id == organization_id)
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
                ).where(
                    models.SchoolCalendarEvent.organization_id == organization_id,
                    models.SchoolCalendarEvent.end_date >= school_year.start_date,
                    models.SchoolCalendarEvent.start_date <= school_year.hard_end_date,
                )
            )
        ).all()
        constraint_rows = (
            await self._db.execute(
                select(
                    models.Constraint.id,
                    models.Constraint.rule_type,
                    models.Constraint.rule_payload,
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
            "timetable_grid": [
                {
                    "id": row.id,
                    "day_of_week": row.day_of_week,
                    "start_time": row.start_time,
                    "end_time": row.end_time,
                }
                for row in sorted(timeslot_rows, key=lambda row: row.id)
            ],
            "calendar_events": [
                {
                    "start_date": row.start_date,
                    "end_date": row.end_date,
                    "event_type": row.event_type,
                    "source": row.source,
                }
                for row in sorted(
                    event_rows,
                    key=lambda row: (
                        row.start_date,
                        row.end_date,
                        row.event_type.value,
                        row.source.value,
                    ),
                )
            ],
            "constraints": [
                {
                    "rule_type": row.rule_type,
                    "rule_payload": row.rule_payload,
                }
                for row in sorted(
                    constraint_rows,
                    key=lambda row: (
                        row.rule_type.value,
                        canonical_json_bytes(row.rule_payload),
                    ),
                )
            ],
            "lunch_rules": None if grid_settings is None else {
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
            "teachers": [
                {"id": row.id}
                for row in sorted(teacher_rows, key=lambda row: row.id)
            ],
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
                        row.class_id, row.subject_id, row.grade_level,
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
                    "hours_total": row.hours_total,
                    "sequence": row.order,
                }
                for row in sorted(module_rows, key=lambda row: row.id)
            ],
            "class_progress": [
                {
                    "class_id": row.class_id,
                    "module_id": row.module_id,
                    "hours_completed": row.hours_completed,
                }
                for row in sorted(
                    progress_rows,
                    key=lambda row: (row.class_id, row.module_id),
                )
            ],
        }

        if strategy == models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR:
            active_rows = (
                await self._db.execute(
                    select(
                        models.ActiveScheduleBlock,
                        models.LessonLog.status.label("lesson_log_status"),
                        models.PlannedRecoveryLink.debt_occurrence_id,
                        models.PlannedRecoveryLink.debt_occurrence_revision,
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
                        models.ActiveScheduleBlock.status == (
                            models.ActiveScheduleBlockStatus.ACTIVE
                        ),
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
                    "is_recovery_block": row.is_recovery_block,
                    "recovery_source_occurrence_id": debt_occurrence_id,
                    "recovery_source_occurrence_revision": debt_occurrence_revision,
                    "lesson_log_status": lesson_log_status,
                }
                for (
                    row,
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
                    models.ScheduleOutput.timeslot_id.label("source_timeslot_id"),
                    models.Timeslot.start_time.label("source_start_time"),
                    models.Timeslot.end_time.label("source_end_time"),
                    models.Lesson.class_id.label("source_class_id"),
                    models.Lesson.subject_id.label("source_subject_id"),
                    models.Lesson.teacher_id.label("source_teacher_id"),
                )
                .outerjoin(
                    models.ScheduleOutput,
                    and_(
                        models.ScheduleOutput.id
                        == models.LessonOccurrence.schedule_output_id,
                        models.ScheduleOutput.organization_id
                        == models.LessonOccurrence.organization_id,
                    ),
                )
                .outerjoin(
                    models.Timeslot,
                    and_(
                        models.Timeslot.id == models.ScheduleOutput.timeslot_id,
                        models.Timeslot.organization_id
                        == models.LessonOccurrence.organization_id,
                    ),
                )
                .outerjoin(
                    models.Lesson,
                    and_(
                        models.Lesson.id == models.ScheduleOutput.lesson_id,
                        models.Lesson.organization_id
                        == models.LessonOccurrence.organization_id,
                    ),
                )
                .where(
                    models.LessonOccurrence.organization_id == organization_id,
                    models.LessonOccurrence.is_active.is_(True),
                    models.LessonOccurrence.status.in_((
                        models.LessonOccurrenceStatus.GAP,
                        models.LessonOccurrenceStatus.SUBSTITUTED,
                    )),
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
                declared_minutes = max(
                    0, int(round(float(occurrence.planned_hours) * 60))
                )
            elif row.source_start_time is not None and row.source_end_time is not None:
                start_minutes = row.source_start_time.hour * 60 + row.source_start_time.minute
                end_minutes = row.source_end_time.hour * 60 + row.source_end_time.minute
                declared_minutes = max(0, end_minutes - start_minutes)
            else:
                declared_minutes = max(
                    0, int(round(float(occurrence.hours_given or 0) * 60))
                )
            delivered_minutes = 0
            active_planned_minutes = 0
            ordered_links = sorted(
                links_by_occurrence.get(occurrence.id, []),
                key=lambda pair: (
                    pair[0].status.value,
                    -1 if pair[0].planned_active_block_id is None else pair[0].planned_active_block_id,
                    -1 if pair[0].planned_draft_block_id is None else pair[0].planned_draft_block_id,
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
                    "source_planned_block_id": occurrence.schedule_output_id,
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
