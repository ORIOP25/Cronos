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
    class_service,
    course_service,
    member_service,
    room_service,
    subject_service,
)
from app.services.bulk_import_policy import (
    IMPORT_RESOURCES,
    MAX_TOTAL_BYTES,
    BulkImportIssue,
    ExistingAssignment,
    ExistingClass,
    ExistingCourse,
    ExistingRoom,
    ExistingSubject,
    ExistingTeacher,
    ImportSnapshot,
    ParsedResourceFile,
    ValidationResult,
    parse_resource_file,
    render_template,
    validate_import,
)


def template_bytes(resource: str) -> bytes:
    try:
        return render_template(resource)
    except KeyError as exc:
        raise AppError(
            kind="not_found",
            code="resource_not_found",
            detail="Unknown import template.",
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


async def load_snapshot(db: AsyncSession, organization_id: int) -> ImportSnapshot:
    rooms = (
        await db.scalars(
            select(models.Room).where(models.Room.organization_id == organization_id)
        )
    ).all()
    subjects = (
        await db.scalars(
            select(models.Subject).where(models.Subject.organization_id == organization_id)
        )
    ).all()
    courses = (
        await db.scalars(
            select(models.Course).where(models.Course.organization_id == organization_id)
        )
    ).all()
    class_rows = (
        await db.execute(
            select(models.Class, models.Course.abbreviation)
            .join(models.Course, models.Course.id == models.Class.course_id)
            .where(models.Class.organization_id == organization_id)
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
    return ImportSnapshot(
        rooms=[ExistingRoom(item.id, item.name) for item in rooms],
        subjects=[ExistingSubject(item.id, item.name) for item in subjects],
        courses=[ExistingCourse(item.id, item.abbreviation, item.name) for item in courses],
        classes=[ExistingClass(item.id, item.course_id, abbreviation, item.name) for item, abbreviation in class_rows],
        teachers=[
            ExistingTeacher(item.id, item.organization_membership.account.email, item.name)
            for item in teachers
        ],
        assignments=[ExistingAssignment(course, class_name, subject) for course, class_name, subject in assignment_rows],
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
    snapshot = await load_snapshot(db, organization_id)
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
    snapshot = await load_snapshot(db, organization_id)
    result = validate_import(files, snapshot)
    if not result.can_commit:
        _raise_validation(result)

    subject_ids = {item.name.casefold(): item.id for item in snapshot.subjects}
    class_ids = {
        (item.course_abbreviation.upper(), item.name.casefold()): item.id for item in snapshot.classes
    }
    teacher_ids: dict[str, int] = {}
    created_counts = {resource: 0 for resource in IMPORT_RESOURCES}
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
        assignments_by_course.setdefault(assignment.course_abbreviation.upper(), set()).add(subject_id)

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
        class_id = class_ids[(assignment.course_abbreviation.upper(), assignment.class_name.casefold())]
        subject_id = subject_ids[assignment.subject_name.casefold()]
        await class_service.add_class_subject(
            db,
            class_id,
            subject_id,
            organization_id,
            changed_by_membership_id=current_admin.membership_id,
        )
        if assignment.teacher_email:
            await class_service.update_class_subject_teacher(
                db,
                class_id,
                subject_id,
                schemas.ClassSubjectUpdate(teacher_id=teacher_ids[assignment.teacher_email]),
                organization_id,
                changed_by_membership_id=current_admin.membership_id,
            )
        created_counts["assignments"] += 1

    await db.flush()
    return schemas.BulkImportCommitResponse(
        created_counts=created_counts,
        warnings=[
            schemas.BulkImportIssue(**issue.as_dict())
            for issue in result.issues
            if issue.severity == "warning"
        ],
    )
