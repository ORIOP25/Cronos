"""Application service for validating and atomically committing CSV imports."""

from __future__ import annotations

from dataclasses import replace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import models, schemas
from app.core.auth import Actor
from app.core.exceptions import AppError
from app.services import (
    class_availability_service,
    class_service,
    course_service,
    grid_version_service,
    member_service,
    room_service,
    subject_service,
    teacher_service,
)
from app.services.bulk_import_policy import (
    CLASS_AVAILABILITY,
    IMPORT_RESOURCES,
    MAX_TOTAL_BYTES,
    TEACHER_AVAILABILITY,
    TEACHER_PRESENCE,
    BulkImportIssue,
    ExistingAssignment,
    ExistingClass,
    ExistingCourse,
    ExistingRoom,
    ExistingSubject,
    ExistingTeacher,
    ExistingTimeslot,
    ImportSnapshot,
    ParsedResourceFile,
    ValidationResult,
    _email,
    parse_resource_file,
    render_availability_template,
    render_teacher_presence_template,
    render_template,
    validate_import,
)

NO_GRID_BLOCKS_MESSAGE = "A escola ainda não configurou blocos."
WEEKLY_AVAILABILITY_RESOURCES = (CLASS_AVAILABILITY, TEACHER_AVAILABILITY)


def _teacher_is_active(membership: models.OrganizationMembership) -> bool:
    """A teacher is active with an active membership and the teacher capability."""
    return (
        membership.lifecycle_status == models.MembershipLifecycleStatus.active
        and membership.can_teach
    )


async def _visible_timeslots(db: AsyncSession, organization_id: int) -> list[models.Timeslot]:
    today = await grid_version_service.school_today(db, organization_id)
    resolved = await grid_version_service.resolve_grid(db, organization_id, today)
    return sorted(
        resolved.blocks, key=lambda block: (block.day_of_week, block.start_time, block.id)
    )


async def _require_visible_timeslots(
    db: AsyncSession, organization_id: int
) -> list[models.Timeslot]:
    timeslots = await _visible_timeslots(db, organization_id)
    if not timeslots:
        raise AppError(
            kind="bad_request",
            code="bad_request",
            detail=NO_GRID_BLOCKS_MESSAGE,
            # Whitelisted reason: the client maps it to a fixed local message and
            # never echoes raw server text.
            public_context={"reason": "no_grid_blocks"},
        )
    return timeslots


async def _availability_scores(
    db: AsyncSession, organization_id: int, entity_column, model
) -> dict[int, dict[int, int]]:
    """Load stored levels per entity from a weekly availability table."""
    rows = (
        await db.execute(
            select(entity_column, model.timeslot_id, model.score).where(
                model.organization_id == organization_id
            )
        )
    ).all()
    scores: dict[int, dict[int, int]] = {}
    for entity_id, timeslot_id, score in rows:
        scores.setdefault(int(entity_id), {})[int(timeslot_id)] = int(score)
    return scores


def _existing_timeslots(timeslots: list[models.Timeslot]) -> list[ExistingTimeslot]:
    return [ExistingTimeslot(block.id, block.day_of_week, block.start_time) for block in timeslots]


async def _class_availability_template(db: AsyncSession, organization_id: int) -> bytes:
    timeslots = await _require_visible_timeslots(db, organization_id)
    class_rows = (
        await db.execute(
            select(models.Class, models.Course.abbreviation)
            .join(models.Course, models.Course.id == models.Class.course_id)
            .where(
                models.Class.organization_id == organization_id,
                models.Class.is_archived.is_(False),
            )
        )
    ).all()
    scores = await _availability_scores(
        db, organization_id, models.ClassAvailability.class_id, models.ClassAvailability
    )
    return render_availability_template(
        CLASS_AVAILABILITY,
        _existing_timeslots(timeslots),
        [
            ExistingClass(item.id, item.course_id, abbreviation, item.name)
            for item, abbreviation in class_rows
        ],
        scores,
    )


async def _teacher_availability_template(db: AsyncSession, organization_id: int) -> bytes:
    timeslots = await _require_visible_timeslots(db, organization_id)
    teacher_rows = (
        await db.scalars(
            select(models.Teacher)
            .where(models.Teacher.organization_id == organization_id)
            .options(
                selectinload(models.Teacher.organization_membership).selectinload(
                    models.OrganizationMembership.account
                )
            )
        )
    ).all()
    scores = await _availability_scores(
        db, organization_id, models.Availability.teacher_id, models.Availability
    )
    return render_availability_template(
        TEACHER_AVAILABILITY,
        _existing_timeslots(timeslots),
        [
            ExistingTeacher(item.id, item.organization_membership.account.email, item.name)
            for item in teacher_rows
            if _teacher_is_active(item.organization_membership)
        ],
        scores,
    )


async def _teacher_presence_template(db: AsyncSession, organization_id: int) -> bytes:
    """Render the presence model from the active teachers and their current rule."""
    rows = (
        await db.execute(
            select(models.Teacher, models.User.email)
            .join(
                models.OrganizationMembership,
                models.OrganizationMembership.id == models.Teacher.organization_membership_id,
            )
            .join(models.User, models.User.id == models.OrganizationMembership.account_id)
            .where(
                models.Teacher.organization_id == organization_id,
                models.OrganizationMembership.lifecycle_status
                == models.MembershipLifecycleStatus.active,
            )
        )
    ).all()
    return render_teacher_presence_template(
        [
            ExistingTeacher(
                id=item.id,
                email=user_email,
                name=item.name,
                lunch_required=item.lunch_required,
                minimum_hours=item.minimum_presence_hours,
                max_gap_hours=item.maximum_presence_gap_hours,
            )
            for item, user_email in rows
        ]
    )


async def template_bytes(db: AsyncSession, organization_id: int, resource: str) -> bytes:
    if resource == CLASS_AVAILABILITY:
        return await _class_availability_template(db, organization_id)
    if resource == TEACHER_AVAILABILITY:
        return await _teacher_availability_template(db, organization_id)
    if resource == TEACHER_PRESENCE:
        return await _teacher_presence_template(db, organization_id)
    try:
        return render_template(resource)
    except KeyError as exc:
        raise AppError(
            kind="not_found",
            code="resource_not_found",
            detail="Secção de importação desconhecida.",
        ) from exc


def _parsed_files(request: schemas.BulkImportFilesRequest) -> dict[str, ParsedResourceFile]:
    values = request.files.model_dump(exclude_none=True)
    parsed = {
        resource: parse_resource_file(
            resource,
            payload["filename"],
            payload["content_base64"],
        )
        for resource, payload in values.items()
    }
    if parsed and sum(item.decoded_bytes for item in parsed.values()) > MAX_TOTAL_BYTES:
        first_resource = next(iter(parsed))
        current = parsed[first_resource]
        parsed[first_resource] = replace(
            current,
            issues=current.issues
            + (
                BulkImportIssue(
                    code="total_size_too_large",
                    severity="error",
                    resource=first_resource,
                    line=None,
                    field=None,
                    message="O conjunto de ficheiros descodificado excede 5 MiB.",
                ),
            ),
        )
    return parsed


async def load_snapshot(
    db: AsyncSession, organization_id: int, *, include_availability: bool = False
) -> ImportSnapshot:
    rooms = (
        await db.scalars(
            select(models.Room).where(
                models.Room.organization_id == organization_id,
                models.Room.is_archived.is_(False),
            )
        )
    ).all()
    subjects = (
        await db.scalars(
            select(models.Subject).where(
                models.Subject.organization_id == organization_id,
                models.Subject.is_archived.is_(False),
            )
        )
    ).all()
    courses = (
        await db.scalars(
            select(models.Course).where(
                models.Course.organization_id == organization_id,
                models.Course.is_archived.is_(False),
            )
        )
    ).all()
    class_rows = (
        await db.execute(
            select(models.Class, models.Course.abbreviation)
            .join(models.Course, models.Course.id == models.Class.course_id)
            .where(
                models.Class.organization_id == organization_id,
                models.Class.is_archived.is_(False),
            )
        )
    ).all()
    teachers = (
        await db.scalars(
            select(models.Teacher)
            .where(models.Teacher.organization_id == organization_id)
            .options(
                selectinload(models.Teacher.organization_membership).selectinload(
                    models.OrganizationMembership.account
                ),
                selectinload(models.Teacher.subjects),
            )
        )
    ).all()
    assignment_rows = (
        await db.execute(
            select(
                models.Course.abbreviation,
                models.Class.name,
                models.Subject.name,
            )
            .select_from(models.ClassSubjectLink)
            .join(models.Class, models.Class.id == models.ClassSubjectLink.class_id)
            .join(models.Course, models.Course.id == models.Class.course_id)
            .join(models.Subject, models.Subject.id == models.ClassSubjectLink.subject_id)
            .where(models.ClassSubjectLink.organization_id == organization_id)
        )
    ).all()
    timeslots = await _visible_timeslots(db, organization_id)
    class_availability: dict[int, dict[int, int]] = {}
    teacher_availability: dict[int, dict[int, int]] = {}
    if include_availability:
        class_availability = await _availability_scores(
            db, organization_id, models.ClassAvailability.class_id, models.ClassAvailability
        )
        teacher_availability = await _availability_scores(
            db, organization_id, models.Availability.teacher_id, models.Availability
        )
    return ImportSnapshot(
        rooms=[ExistingRoom(item.id, item.name) for item in rooms],
        subjects=[ExistingSubject(item.id, item.name) for item in subjects],
        courses=[ExistingCourse(item.id, item.abbreviation, item.name) for item in courses],
        classes=[
            ExistingClass(item.id, item.course_id, abbreviation, item.name)
            for item, abbreviation in class_rows
        ],
        teachers=[
            ExistingTeacher(
                id=item.id,
                email=item.organization_membership.account.email,
                name=item.name,
                is_active=_teacher_is_active(item.organization_membership),
                lunch_required=item.lunch_required,
                minimum_hours=item.minimum_presence_hours,
                max_gap_hours=item.maximum_presence_gap_hours,
            )
            for item in teachers
        ],
        assignments=[
            ExistingAssignment(course, class_name, subject)
            for course, class_name, subject in assignment_rows
        ],
        timeslots=[
            ExistingTimeslot(block.id, block.day_of_week, block.start_time) for block in timeslots
        ],
        class_availability=class_availability,
        teacher_availability=teacher_availability,
    )


def _response(result: ValidationResult) -> schemas.BulkImportValidationResponse:
    issues = [schemas.BulkImportIssue(**issue.as_dict()) for issue in result.issues]
    preview = schemas.BulkImportPreview(
        counts=result.counts,
        items=list(result.preview),
        can_commit=result.can_commit,
    )
    return schemas.BulkImportValidationResponse(
        can_commit=result.can_commit,
        preview=preview,
        issues=issues,
    )


async def validate(
    db: AsyncSession,
    request: schemas.BulkImportFilesRequest,
    organization_id: int,
) -> schemas.BulkImportValidationResponse:
    files = _parsed_files(request)
    snapshot = await load_snapshot(
        db,
        organization_id,
        include_availability=any(resource in files for resource in WEEKLY_AVAILABILITY_RESOURCES),
    )
    return _response(validate_import(files, snapshot))


def _raise_validation(result: ValidationResult) -> None:
    response = _response(result)
    raise AppError(
        kind="validation",
        code="bulk_import_validation_failed",
        detail="O lote de importação contém erros.",
        public_context=response.model_dump(mode="json"),
    )


async def commit_import(
    db: AsyncSession,
    request: schemas.BulkImportFilesRequest,
    organization_id: int,
    current_admin: Actor,
) -> schemas.BulkImportCommitResponse:
    files = _parsed_files(request)
    snapshot = await load_snapshot(
        db,
        organization_id,
        include_availability=any(resource in files for resource in WEEKLY_AVAILABILITY_RESOURCES),
    )
    result = validate_import(files, snapshot)
    if not result.can_commit:
        _raise_validation(result)

    subject_ids = {item.name.casefold(): item.id for item in snapshot.subjects}
    class_ids = {
        (item.course_abbreviation.upper(), item.name.casefold()): item.id
        for item in snapshot.classes
    }
    teacher_ids: dict[str, int] = {}
    created_counts = dict.fromkeys(IMPORT_RESOURCES, 0)
    created_counts.update({"classes": 0, "modules": 0, "competencies": 0})

    for item in result.rooms:
        await room_service.create_room(
            db,
            schemas.RoomCreate(name=item.name, type=item.room_type, capacity=item.capacity),
            organization_id,
            changed_by_membership_id=current_admin.membership_id,
        )
        created_counts["rooms"] += 1

    for item in result.subjects:
        subject = await subject_service.create_subject(
            db,
            schemas.SubjectCreate(
                name=item.name,
                required_room_type=item.room_type,
                modules=[
                    schemas.ModuleCreate(
                        name=module.name,
                        code=module.code,
                        hours_total=module.hours,
                        order=module.order - 1,
                    )
                    for module in item.modules
                ],
            ),
            organization_id,
            changed_by_membership_id=current_admin.membership_id,
        )
        subject_ids[item.name.casefold()] = subject.id
        created_counts["subjects"] += 1
        created_counts["modules"] += len(item.modules)

    for item in result.teachers:
        subject_names = set(item.competency_subjects)
        subject_names.update(result.inferred_competencies.get(item.email, ()))
        teacher = await member_service.create_member(
            db,
            schemas.MemberCreate(
                organization_display_name=item.name,
                email=item.email,
                capabilities=["teacher"],
                teacher_access_mode="scheduler_only",
                subject_ids=[subject_ids[name.casefold()] for name in subject_names],
            ),
            organization_id=organization_id,
            current_admin=current_admin,
        )
        if teacher.teacher_id is None:
            raise RuntimeError("Imported teacher profile was not created.")
        teacher_ids[item.email] = teacher.teacher_id
        created_counts["teachers"] += 1
        created_counts["competencies"] += len(subject_names)

    assignments_by_course: dict[str, set[int]] = {}
    for assignment in result.assignments:
        subject_id = subject_ids[assignment.subject_name.casefold()]
        assignments_by_course.setdefault(assignment.course_abbreviation.upper(), set()).add(
            subject_id
        )

    for item in result.courses:
        course = await course_service.create_course(
            db,
            schemas.CourseCreate(
                name=item.name,
                abbreviation=item.abbreviation,
                subject_ids=sorted(assignments_by_course.get(item.abbreviation.upper(), set())),
                classes_config=[
                    schemas.ClassConfigCreate(
                        name=class_item.name,
                        grade_level=class_item.grade_level,
                        size=class_item.size,
                        start_year=class_item.start_year,
                        end_year=class_item.end_year,
                    )
                    for class_item in item.classes
                ],
            ),
            organization_id,
            changed_by_membership_id=current_admin.membership_id,
        )
        created_counts["courses"] += 1
        created_counts["classes"] += len(item.classes)
        for class_item in course.classes:
            class_ids[(item.abbreviation.upper(), class_item.name.casefold())] = class_item.id

    for assignment in result.assignments:
        class_id = class_ids[
            (assignment.course_abbreviation.upper(), assignment.class_name.casefold())
        ]
        subject_id = subject_ids[assignment.subject_name.casefold()]
        await class_service.add_class_subject(
            db,
            class_id,
            subject_id,
            organization_id,
            changed_by_membership_id=current_admin.membership_id,
        )
        if assignment.teacher_email:
            await class_service.update_class_subject(
                db,
                class_id,
                subject_id,
                schemas.ClassSubjectUpdate(teacher_id=teacher_ids[assignment.teacher_email]),
                organization_id,
                changed_by_membership_id=current_admin.membership_id,
            )
        created_counts["assignments"] += 1

    for item in result.class_availability:
        class_id = class_ids[(item.course_abbreviation.upper(), item.class_name.casefold())]
        payload = [
            schemas.AvailabilitySelfCreate(
                timeslot_id=timeslot.id,
                score=models.PreferenceLevel(
                    item.scores.get(timeslot.id, models.PreferenceLevel.NEUTRAL.value)
                ),
            )
            for timeslot in snapshot.timeslots
        ]
        await class_availability_service.replace_class_availability(
            db,
            class_id,
            payload,
            organization_id,
            changed_by_membership_id=current_admin.membership_id,
        )
        created_counts[CLASS_AVAILABILITY] += 1

    # Teacher grids are written last, once per teacher, through the same service the
    # availability window uses (I04). Every visible block gets a level; a block
    # absent from the file stays NEUTRAL.
    existing_teacher_ids = {_email(item.email): item.id for item in snapshot.teachers}
    for item in result.teacher_availability:
        teacher_id = teacher_ids.get(item.teacher_email) or existing_teacher_ids[item.teacher_email]
        payload = [
            schemas.AvailabilitySelfCreate(
                timeslot_id=timeslot.id,
                score=models.PreferenceLevel(
                    item.scores.get(timeslot.id, models.PreferenceLevel.NEUTRAL.value)
                ),
            )
            for timeslot in snapshot.timeslots
        ]
        await teacher_service.set_teacher_availability(
            db,
            teacher_id,
            payload,
            organization_id,
            changed_by_membership_id=current_admin.membership_id,
        )
        created_counts[TEACHER_AVAILABILITY] += 1

    presence_teacher_ids = {item.email.lower(): item.id for item in snapshot.teachers}
    presence_teacher_ids.update(teacher_ids)
    existing_presence = {
        item.email.lower(): (item.lunch_required, item.minimum_hours, item.max_gap_hours)
        for item in snapshot.teachers
    }
    for item in result.teacher_presence:
        before = existing_presence.get(item.email, (True, None, None))
        after = (item.lunch_required, item.minimum_hours, item.max_gap_hours)
        await teacher_service.set_teacher_presence(
            db,
            presence_teacher_ids[item.email],
            schemas.TeacherPresence(
                lunch_required=item.lunch_required,
                minimum_hours=item.minimum_hours,
                max_gap_hours=item.max_gap_hours,
            ),
            organization_id,
            changed_by_membership_id=current_admin.membership_id,
        )
        if before != after:
            created_counts[TEACHER_PRESENCE] += 1

    await db.flush()
    return schemas.BulkImportCommitResponse(
        created_counts=created_counts,
        warnings=[
            schemas.BulkImportIssue(**issue.as_dict())
            for issue in result.issues
            if issue.severity == "warning"
        ],
    )
