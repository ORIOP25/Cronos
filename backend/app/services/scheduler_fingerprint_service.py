from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.core.task_keys import resolve_repair_window_days
from app.scheduler.domain.calendar import first_editable_grid_date
from app.scheduler.domain.priorities import school_priority_weights
from app.scheduler.domain.serialization import (
    canonical_json,
    canonical_json_value,
    payload_digest,
)
from app.services import grid_version_service


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


def _teacher_snapshot(row) -> dict:
    """Serialize one eligible teacher, adding the presence rule only when it differs.

    The default rule (lunch required, no minimum) keeps the legacy ``{"id": ...}``
    shape, so a schedule input without presence rules has the same digest as before.
    """
    entry: dict = {"id": row.id}
    if not row.lunch_required or row.minimum_presence_hours is not None:
        entry.update(
            {
                "lunch_required": row.lunch_required,
                "minimum_presence_hours": row.minimum_presence_hours,
                "maximum_presence_gap_hours": row.maximum_presence_gap_hours,
            }
        )
    return entry


def _class_snapshot(row) -> dict:
    """Serialize one class, adding its home room only when it has one.

    Automática keeps the legacy shape, so a school without home rooms keeps its digest.
    """
    entry: dict = {
        "id": row.id,
        "size": row.size,
        "grade_level": row.grade_level,
        "start_year": row.start_year,
        "end_year": row.end_year,
        "course_id": row.course_id,
    }
    if row.home_room_id is not None:
        entry["home_room_id"] = row.home_room_id
    return entry


@dataclass(frozen=True)
class SchedulerFingerprint:
    value: str
    snapshot: dict


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
            value=payload_digest(snapshot),
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
        return SchedulerFingerprint(value=payload_digest(snapshot), snapshot=snapshot)

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
                    models.Class.home_room_id,
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
                    select(
                        models.Teacher.id,
                        models.Teacher.lunch_required,
                        models.Teacher.minimum_presence_hours,
                        models.Teacher.maximum_presence_gap_hours,
                    )
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
                    select(models.Subject.id, models.Subject.room_type_id).where(
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
        link_ids = {row.id for row in assignment_rows}
        selection_rows = (
            (
                await self._db.execute(
                    select(
                        models.ClassSubjectLink.class_id,
                        models.ClassSubjectLink.subject_id,
                        models.ClassSubjectLink.grade_level,
                        models.class_subject_module.c.module_id,
                    )
                    .select_from(models.class_subject_module)
                    .join(
                        models.ClassSubjectLink,
                        and_(
                            models.ClassSubjectLink.organization_id
                            == models.class_subject_module.c.organization_id,
                            models.ClassSubjectLink.id
                            == models.class_subject_module.c.class_subject_link_id,
                        ),
                    )
                    .where(
                        models.class_subject_module.c.organization_id == organization_id,
                        models.class_subject_module.c.class_subject_link_id.in_(link_ids),
                    )
                )
            ).all()
            if link_ids
            else []
        )
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
        joint_group_rows = (
            await self._db.execute(
                select(
                    models.JointLessonGroup.id,
                    models.JointLessonGroup.subject_id,
                )
                .where(models.JointLessonGroup.organization_id == organization_id)
                .order_by(models.JointLessonGroup.id)
            )
        ).all()
        joint_lesson_groups: list[dict] = []
        if joint_group_rows:
            group_ids = [row.id for row in joint_group_rows]
            joint_class_rows = (
                await self._db.execute(
                    select(
                        models.joint_lesson_group_member.c.group_id,
                        models.ClassSubjectLink.class_id,
                    )
                    .join(
                        models.ClassSubjectLink,
                        models.ClassSubjectLink.id
                        == models.joint_lesson_group_member.c.class_subject_link_id,
                    )
                    .where(
                        models.joint_lesson_group_member.c.organization_id == organization_id,
                        models.joint_lesson_group_member.c.group_id.in_(group_ids),
                    )
                    .order_by(
                        models.joint_lesson_group_member.c.group_id,
                        models.ClassSubjectLink.class_id,
                    )
                )
            ).all()
            joint_module_rows = (
                await self._db.execute(
                    select(
                        models.joint_lesson_group_module.c.group_id,
                        models.joint_lesson_group_module.c.module_id,
                    )
                    .where(
                        models.joint_lesson_group_module.c.organization_id == organization_id,
                        models.joint_lesson_group_module.c.group_id.in_(group_ids),
                    )
                    .order_by(
                        models.joint_lesson_group_module.c.group_id,
                        models.joint_lesson_group_module.c.module_id,
                    )
                )
            ).all()
            classes_by_group: dict[int, list[int]] = {}
            for group_id, class_id in joint_class_rows:
                classes_by_group.setdefault(group_id, []).append(class_id)
            modules_by_group: dict[int, list[int]] = {}
            for group_id, module_id in joint_module_rows:
                modules_by_group.setdefault(group_id, []).append(module_id)
            joint_lesson_groups = [
                {
                    "subject_id": row.subject_id,
                    "class_ids": classes_by_group.get(row.id, []),
                    "module_ids": modules_by_group.get(row.id, []),
                }
                for row in joint_group_rows
            ]

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
        class_availability_rows = (
            (
                await self._db.execute(
                    select(
                        models.ClassAvailability.class_id,
                        models.ClassAvailability.timeslot_id,
                        models.ClassAvailability.score,
                    ).where(
                        models.ClassAvailability.organization_id == organization_id,
                        models.ClassAvailability.class_id.in_(class_ids),
                    )
                )
            ).all()
            if class_ids
            else []
        )
        room_rows = (
            await self._db.execute(
                select(
                    models.Room.id,
                    models.Room.capacity,
                    models.Room.room_type_id,
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
        priority_levels = await self._db.scalar(
            select(models.OrganizationSettings.schedule_priorities).where(
                models.OrganizationSettings.organization_id == organization_id
            )
        )

        snapshot = {
            "organization_id": organization_id,
            "school_year_id": school_year_id,
            "strategy": strategy,
            "schedule_priorities": school_priority_weights(priority_levels).to_dict(),
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
                        canonical_json(_constraint_payload(row)),
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
            "classes": [_class_snapshot(row) for row in sorted(class_rows, key=lambda row: row.id)],
            "subjects": [
                {"id": row.id, "room_type_id": row.room_type_id}
                for row in sorted(subject_rows, key=lambda row: row.id)
            ],
            "teachers": [
                _teacher_snapshot(row) for row in sorted(teacher_rows, key=lambda row: row.id)
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
                        row.class_id,
                        row.subject_id,
                        row.grade_level,
                        -1 if row.teacher_id is None else row.teacher_id,
                    ),
                )
            ],
            "class_subject_modules": [
                {
                    "class_id": row.class_id,
                    "subject_id": row.subject_id,
                    "grade_level": row.grade_level,
                    "module_id": row.module_id,
                }
                for row in sorted(
                    selection_rows,
                    key=lambda row: (
                        row.class_id,
                        row.subject_id,
                        row.grade_level,
                        row.module_id,
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
            "class_availability": [
                {
                    "class_id": row.class_id,
                    "timeslot_id": row.timeslot_id,
                    "score": row.score,
                }
                for row in sorted(
                    class_availability_rows,
                    key=lambda row: (row.class_id, row.timeslot_id),
                )
            ],
            "rooms": [
                {"id": row.id, "capacity": row.capacity, "room_type_id": row.room_type_id}
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

        if joint_lesson_groups:
            snapshot["joint_lesson_groups"] = joint_lesson_groups

        return canonical_json_value(snapshot)
