"""Pure contracts, parsing and validation for administrative CSV imports."""

from __future__ import annotations

import base64
import csv
import io
from collections import defaultdict
from dataclasses import dataclass, field
from email.utils import parseaddr
from typing import Literal

MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 5 * 1024 * 1024
MAX_LINES = 5_000
IMPORT_RESOURCES = ("rooms", "subjects", "courses", "teachers", "assignments")
IssueSeverity = Literal["error", "warning"]


@dataclass(frozen=True)
class TemplateDefinition:
    headers: tuple[str, ...]
    example: tuple[str, ...]
    filename: str


TEMPLATE_DEFINITIONS = {
    "rooms": TemplateDefinition(
        ("name", "type", "capacity"),
        ("Sala de Exemplo", "normal", "30"),
        "salas.csv",
    ),
    "subjects": TemplateDefinition(
        ("name", "required_room_type", "module_name", "module_code", "module_hours", "module_order"),
        ("Disciplina de Exemplo", "normal", "Módulo de Exemplo", "MOD-EXEMPLO", "30", "1"),
        "disciplinas.csv",
    ),
    "courses": TemplateDefinition(
        ("abbreviation", "name", "class_name", "grade_level", "start_year", "end_year", "size"),
        ("EXEMPLO", "Curso de Exemplo", "Turma de Exemplo", "10", "2025", "2028", "25"),
        "cursos.csv",
    ),
    "teachers": TemplateDefinition(
        ("name", "email", "competency_subject"),
        ("Professor de Exemplo", "professor.exemplo@example.invalid", "Disciplina de Exemplo"),
        "professores.csv",
    ),
    "assignments": TemplateDefinition(
        ("course_abbreviation", "class_name", "subject_name", "teacher_email"),
        ("EXEMPLO", "Turma de Exemplo", "Disciplina de Exemplo", "professor.exemplo@example.invalid"),
        "atribuicoes.csv",
    ),
}


@dataclass(frozen=True)
class BulkImportIssue:
    code: str
    severity: IssueSeverity
    resource: str
    line: int | None
    field: str | None
    message: str

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "resource": self.resource,
            "line": self.line,
            "field": self.field,
            "message": self.message,
        }


@dataclass(frozen=True)
class ParsedResourceFile:
    resource: str
    filename: str
    rows: tuple[dict[str, str | int], ...] = ()
    issues: tuple[BulkImportIssue, ...] = ()
    decoded_bytes: int = 0


@dataclass(frozen=True)
class RoomImport:
    name: str
    room_type: str
    capacity: int
    line: int


@dataclass(frozen=True)
class ModuleImport:
    name: str
    code: str | None
    hours: int
    order: int
    line: int


@dataclass(frozen=True)
class SubjectImport:
    name: str
    room_type: str
    modules: tuple[ModuleImport, ...]
    line: int


@dataclass(frozen=True)
class ClassImport:
    name: str
    grade_level: int
    start_year: int
    end_year: int
    size: int
    line: int


@dataclass(frozen=True)
class CourseImport:
    abbreviation: str
    name: str
    classes: tuple[ClassImport, ...]
    line: int


@dataclass(frozen=True)
class TeacherImport:
    name: str
    email: str
    competency_subjects: tuple[str, ...]
    line: int


@dataclass(frozen=True)
class AssignmentImport:
    course_abbreviation: str
    class_name: str
    subject_name: str
    teacher_email: str | None
    line: int


@dataclass(frozen=True)
class ExistingRoom:
    id: int
    name: str


@dataclass(frozen=True)
class ExistingSubject:
    id: int
    name: str


@dataclass(frozen=True)
class ExistingCourse:
    id: int
    abbreviation: str
    name: str


@dataclass(frozen=True)
class ExistingClass:
    id: int
    course_id: int
    course_abbreviation: str
    name: str


@dataclass(frozen=True)
class ExistingTeacher:
    id: int
    email: str
    name: str


@dataclass(frozen=True)
class ExistingAssignment:
    course_abbreviation: str
    class_name: str
    subject_name: str


@dataclass
class ImportSnapshot:
    rooms: list[ExistingRoom] = field(default_factory=list)
    subjects: list[ExistingSubject] = field(default_factory=list)
    courses: list[ExistingCourse] = field(default_factory=list)
    classes: list[ExistingClass] = field(default_factory=list)
    teachers: list[ExistingTeacher] = field(default_factory=list)
    assignments: list[ExistingAssignment] = field(default_factory=list)


@dataclass(frozen=True)
class ValidationResult:
    issues: tuple[BulkImportIssue, ...]
    rooms: tuple[RoomImport, ...] = ()
    subjects: tuple[SubjectImport, ...] = ()
    courses: tuple[CourseImport, ...] = ()
    teachers: tuple[TeacherImport, ...] = ()
    assignments: tuple[AssignmentImport, ...] = ()
    counts: dict[str, int] = field(default_factory=dict)
    preview: tuple[dict, ...] = ()
    inferred_competencies: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def can_commit(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)


def _issue(resource: str, code: str, message: str, *, line: int | None = None, field: str | None = None,
           severity: IssueSeverity = "error") -> BulkImportIssue:
    return BulkImportIssue(code, severity, resource, line, field, message)


def _clean(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _key(value: str) -> str:
    return _clean(value).casefold()


def _email(value: str) -> str:
    return _clean(value).lower()


def _valid_email(value: str) -> bool:
    parsed = parseaddr(value)[1]
    return parsed == value and "@" in value and not value.endswith("@") and " " not in value


def _is_blank_row(row: dict) -> bool:
    return all(not _clean(value) for key, value in row.items() if key is not None)


def render_template(resource: str) -> bytes:
    definition = TEMPLATE_DEFINITIONS.get(resource)
    if definition is None:
        raise KeyError(resource)
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow(definition.headers)
    writer.writerow(definition.example)
    return b"\xef\xbb\xbf" + output.getvalue().encode("utf-8")


def parse_resource_file(resource: str, filename: str, content_base64: str) -> ParsedResourceFile:
    if resource not in TEMPLATE_DEFINITIONS:
        return ParsedResourceFile(resource, filename, issues=(_issue(resource, "resource_unknown", "Recurso de importação desconhecido."),))
    definition = TEMPLATE_DEFINITIONS[resource]
    try:
        raw = base64.b64decode(content_base64, validate=True)
    except (ValueError, TypeError):
        return ParsedResourceFile(resource, filename, issues=(_issue(resource, "base64_invalid", "O conteúdo Base64 é inválido."),))
    if len(raw) > MAX_FILE_BYTES:
        return ParsedResourceFile(resource, filename, issues=(_issue(resource, "file_too_large", "O ficheiro excede 1 MiB."),), decoded_bytes=len(raw))
    if not raw.startswith(b"\xef\xbb\xbf"):
        return ParsedResourceFile(resource, filename, issues=(_issue(resource, "utf8_bom_required", "O ficheiro deve usar UTF-8 com BOM."),), decoded_bytes=len(raw))
    try:
        text = raw[3:].decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return ParsedResourceFile(resource, filename, issues=(_issue(resource, "utf8_invalid", "O ficheiro não é UTF-8 válido."),), decoded_bytes=len(raw))
    if "\x00" in text:
        return ParsedResourceFile(resource, filename, issues=(_issue(resource, "nul_byte", "O ficheiro contém um byte NUL inválido."),), decoded_bytes=len(raw))
    physical_lines = len(text.splitlines())
    if physical_lines > MAX_LINES:
        return ParsedResourceFile(resource, filename, issues=(_issue(resource, "line_limit_exceeded", "O ficheiro excede 5.000 linhas."),), decoded_bytes=len(raw))
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    if "," in first_line and ";" not in first_line:
        return ParsedResourceFile(resource, filename, issues=(_issue(resource, "delimiter_invalid", "Use ponto e vírgula (;) como separador."),), decoded_bytes=len(raw))

    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=";")
    headers = reader.fieldnames or []
    header_issues: list[BulkImportIssue] = []
    normalized_headers = [_key(header) for header in headers]
    if any(not header.strip() for header in headers):
        header_issues.append(_issue(resource, "header_empty", "O cabeçalho não pode conter colunas vazias.", line=1))
    if len(set(normalized_headers)) != len(normalized_headers):
        header_issues.append(_issue(resource, "header_duplicate", "O cabeçalho contém colunas repetidas.", line=1))
    missing = sorted(set(definition.headers) - set(headers))
    extra = sorted(set(headers) - set(definition.headers))
    if missing:
        header_issues.append(_issue(resource, "header_missing", f"Colunas em falta: {', '.join(missing)}.", line=1))
    if extra:
        header_issues.append(_issue(resource, "header_extra", f"Colunas não previstas: {', '.join(extra)}.", line=1))
    if header_issues:
        return ParsedResourceFile(resource, filename, issues=tuple(header_issues), decoded_bytes=len(raw))

    rows: list[dict[str, str | int]] = []
    issues: list[BulkImportIssue] = []
    for raw_row in reader:
        line = reader.line_num
        if _is_blank_row(raw_row):
            continue
        if None in raw_row or any(value is None for value in raw_row.values()):
            issues.append(_issue(resource, "column_count_invalid", "A linha não contém o número esperado de colunas.", line=line))
            continue
        row = {header: _clean(raw_row.get(header, "")) for header in definition.headers}
        row["line"] = line
        rows.append(row)
        if tuple(row[header] for header in definition.headers) == definition.example:
            issues.append(_issue(resource, "template_example_present", "Substitua a linha oficial de exemplo antes de importar.", line=line))
    if not rows:
        issues.append(_issue(resource, "no_data", "Selecione um ficheiro com pelo menos uma linha real."))
    return ParsedResourceFile(resource, filename, tuple(rows), tuple(issues), len(raw))


def _value(row: dict, field: str) -> str:
    return _clean(row.get(field, ""))


def _int_value(row: dict, resource: str, field: str, issues: list[BulkImportIssue], *, minimum: int | None = None) -> int | None:
    raw = _value(row, field)
    if not raw:
        issues.append(_issue(resource, "field_required", "Campo obrigatório.", line=int(row["line"]), field=field))
        return None
    try:
        value = int(raw)
    except ValueError:
        issues.append(_issue(resource, "integer_invalid", "Indique um número inteiro.", line=int(row["line"]), field=field))
        return None
    if minimum is not None and value < minimum:
        issues.append(_issue(resource, "integer_out_of_range", f"O valor deve ser maior ou igual a {minimum}.", line=int(row["line"]), field=field))
        return None
    return value


def _validate_rooms(parsed: ParsedResourceFile, snapshot: ImportSnapshot, issues: list[BulkImportIssue]) -> tuple[RoomImport, ...]:
    allowed = {"normal", "lab", "gym", "art"}
    result = []
    seen = set()
    existing = {_key(item.name) for item in snapshot.rooms}
    for row in parsed.rows:
        line = int(row["line"])
        name = _value(row, "name")
        room_type = _value(row, "type").lower()
        capacity = _int_value(row, "rooms", "capacity", issues, minimum=1)
        if not name:
            issues.append(_issue("rooms", "field_required", "Campo obrigatório.", line=line, field="name"))
        if room_type not in allowed:
            issues.append(_issue("rooms", "room_type_invalid", "Tipo de sala inválido.", line=line, field="type"))
        normalized = _key(name)
        if normalized in seen:
            issues.append(_issue("rooms", "duplicate_in_batch", "A sala está repetida no lote.", line=line, field="name"))
        if normalized in existing:
            issues.append(_issue("rooms", "duplicate_existing", "Já existe uma sala com este nome.", line=line, field="name"))
        seen.add(normalized)
        if name and room_type in allowed and capacity is not None:
            result.append(RoomImport(name, room_type, capacity, line))
    return tuple(result)


def _validate_subjects(parsed: ParsedResourceFile, snapshot: ImportSnapshot, issues: list[BulkImportIssue]) -> tuple[SubjectImport, ...]:
    groups: dict[str, list[dict]] = defaultdict(list)
    existing = {_key(item.name) for item in snapshot.subjects}
    for row in parsed.rows:
        groups[_key(_value(row, "name"))].append(row)
    result = []
    for normalized, rows in groups.items():
        first = rows[0]
        line = int(first["line"])
        name = _value(first, "name")
        room_type = _value(first, "required_room_type").lower()
        if not name:
            issues.append(_issue("subjects", "field_required", "Campo obrigatório.", line=line, field="name"))
        if room_type not in {"normal", "lab", "gym", "art"}:
            issues.append(_issue("subjects", "room_type_invalid", "Tipo de sala inválido.", line=line, field="required_room_type"))
        if normalized in existing:
            issues.append(_issue("subjects", "duplicate_existing", "Já existe uma disciplina com este nome.", line=line, field="name"))
        modules = []
        seen_orders = set()
        for row in rows:
            row_line = int(row["line"])
            current_type = _value(row, "required_room_type").lower()
            if current_type != room_type:
                issues.append(_issue("subjects", "parent_contradiction", "A disciplina repete-se com tipos de sala contraditórios.", line=row_line, field="required_room_type"))
            values = [_value(row, field) for field in ("module_name", "module_code", "module_hours", "module_order")]
            if not any(values):
                continue
            if not all(values[0::1]):
                issues.append(_issue("subjects", "module_partial", "Preencha todos os campos do módulo ou deixe-os todos vazios.", line=row_line, field="module_name"))
                continue
            hours = _int_value(row, "subjects", "module_hours", issues, minimum=1)
            order = _int_value(row, "subjects", "module_order", issues, minimum=1)
            if order in seen_orders:
                issues.append(_issue("subjects", "module_order_duplicate", "A ordem do módulo está repetida.", line=row_line, field="module_order"))
            seen_orders.add(order)
            if hours is not None and order is not None:
                modules.append(ModuleImport(_value(row, "module_name"), _value(row, "module_code") or None, hours, order, row_line))
        if not modules:
            issues.append(_issue("subjects", "subject_without_modules", "A disciplina será criada sem módulos.", line=line, field="module_name", severity="warning"))
        elif sorted(item.order for item in modules) != list(range(1, len(modules) + 1)):
            issues.append(_issue("subjects", "module_order_not_continuous", "As ordens dos módulos devem ser contínuas de 1 até n.", line=line, field="module_order"))
        if name and room_type in {"normal", "lab", "gym", "art"}:
            result.append(SubjectImport(name, room_type, tuple(sorted(modules, key=lambda item: item.order)), line))
    return tuple(result)


def _validate_courses(parsed: ParsedResourceFile, snapshot: ImportSnapshot, issues: list[BulkImportIssue]) -> tuple[CourseImport, ...]:
    groups: dict[str, list[dict]] = defaultdict(list)
    existing = {item.abbreviation.upper() for item in snapshot.courses}
    for row in parsed.rows:
        groups[_value(row, "abbreviation").upper()].append(row)
    result = []
    for abbreviation, rows in groups.items():
        first = rows[0]
        line = int(first["line"])
        name = _value(first, "name")
        if not abbreviation:
            issues.append(_issue("courses", "field_required", "Campo obrigatório.", line=line, field="abbreviation"))
        if not name:
            issues.append(_issue("courses", "field_required", "Campo obrigatório.", line=line, field="name"))
        if abbreviation in existing:
            issues.append(_issue("courses", "duplicate_existing", "Já existe um curso com esta sigla.", line=line, field="abbreviation"))
        classes = []
        seen_class_names = set()
        for row in rows:
            row_line = int(row["line"])
            class_values = [_value(row, field) for field in ("class_name", "grade_level", "start_year", "end_year", "size")]
            if not any(class_values):
                continue
            if not all(class_values):
                issues.append(_issue("courses", "class_partial", "Preencha todos os campos da turma ou deixe-os todos vazios.", line=row_line, field="class_name"))
                continue
            grade = _int_value(row, "courses", "grade_level", issues, minimum=10)
            start = _int_value(row, "courses", "start_year", issues)
            end = _int_value(row, "courses", "end_year", issues)
            size = _int_value(row, "courses", "size", issues, minimum=1)
            if grade is not None and grade > 12:
                issues.append(_issue("courses", "grade_invalid", "O ano deve ser 10, 11 ou 12.", line=row_line, field="grade_level"))
            if start is not None and end is not None and end <= start:
                issues.append(_issue("courses", "year_range_invalid", "O ano final deve ser maior que o inicial.", line=row_line, field="end_year"))
            class_key = _key(_value(row, "class_name"))
            if class_key in seen_class_names:
                issues.append(_issue("courses", "duplicate_in_batch", "A turma está repetida no lote.", line=row_line, field="class_name"))
            seen_class_names.add(class_key)
            if grade is not None and 10 <= grade <= 12 and start is not None and end is not None and end > start and size is not None:
                classes.append(ClassImport(_value(row, "class_name"), grade, start, end, size, row_line))
        if not classes:
            issues.append(_issue("courses", "course_without_classes", "O curso será criado sem turmas.", line=line, field="class_name", severity="warning"))
        if name and abbreviation:
            for row in rows[1:]:
                if _value(row, "name") and _value(row, "name") != name:
                    issues.append(_issue("courses", "parent_contradiction", "A sigla repete-se com nomes contraditórios.", line=int(row["line"]), field="name"))
            result.append(CourseImport(abbreviation, name, tuple(classes), line))
    return tuple(result)


def _validate_teachers(parsed: ParsedResourceFile, snapshot: ImportSnapshot, issues: list[BulkImportIssue]) -> tuple[TeacherImport, ...]:
    groups: dict[str, list[dict]] = defaultdict(list)
    existing = {_email(item.email) for item in snapshot.teachers}
    for row in parsed.rows:
        groups[_email(_value(row, "email"))].append(row)
    result = []
    for email, rows in groups.items():
        first = rows[0]
        line = int(first["line"])
        name = _value(first, "name")
        if not name:
            issues.append(_issue("teachers", "field_required", "Campo obrigatório.", line=line, field="name"))
        if not _valid_email(email):
            issues.append(_issue("teachers", "email_invalid", "Indique um email válido.", line=line, field="email"))
        if email in existing:
            issues.append(_issue("teachers", "teacher_existing_forbidden", "Professores existentes não podem ser referenciados pelo importador.", line=line, field="email"))
        subjects = []
        seen_subjects = set()
        for row in rows:
            current_name = _value(row, "name")
            if current_name and name and current_name != name:
                issues.append(_issue("teachers", "parent_contradiction", "O email repete-se com nomes contraditórios.", line=int(row["line"]), field="name"))
            subject = _value(row, "competency_subject")
            if subject and _key(subject) not in seen_subjects:
                subjects.append(subject)
                seen_subjects.add(_key(subject))
        if not subjects:
            issues.append(_issue("teachers", "teacher_without_competencies", "O professor será criado sem competências.", line=line, field="competency_subject", severity="warning"))
        if name and _valid_email(email):
            result.append(TeacherImport(name, email, tuple(subjects), line))
    return tuple(result)


def _validate_assignments(parsed: ParsedResourceFile, snapshot: ImportSnapshot, issues: list[BulkImportIssue]) -> tuple[AssignmentImport, ...]:
    result = []
    seen = set()
    existing = {(_key(item.course_abbreviation), _key(item.class_name), _key(item.subject_name)) for item in snapshot.assignments}
    for row in parsed.rows:
        line = int(row["line"])
        course = _value(row, "course_abbreviation").upper()
        class_name = _value(row, "class_name")
        subject = _value(row, "subject_name")
        teacher = _email(_value(row, "teacher_email")) or None
        for field_name, value in (("course_abbreviation", course), ("class_name", class_name), ("subject_name", subject)):
            if not value:
                issues.append(_issue("assignments", "field_required", "Campo obrigatório.", line=line, field=field_name))
        key = (_key(course), _key(class_name), _key(subject))
        if key in seen:
            issues.append(_issue("assignments", "duplicate_in_batch", "A atribuição está repetida no lote.", line=line))
        if key in existing:
            issues.append(_issue("assignments", "assignment_existing", "A atribuição já existe na organização.", line=line))
        seen.add(key)
        if teacher is None:
            issues.append(_issue("assignments", "teacher_missing_warning", "A atribuição ficará sem professor.", line=line, field="teacher_email", severity="warning"))
        result.append(AssignmentImport(course, class_name, subject, teacher, line))
    return tuple(result)


def validate_import(files: dict[str, ParsedResourceFile], snapshot: ImportSnapshot) -> ValidationResult:
    issues: list[BulkImportIssue] = [issue for parsed in files.values() for issue in parsed.issues]
    rooms = _validate_rooms(files["rooms"], snapshot, issues) if "rooms" in files else ()
    subjects = _validate_subjects(files["subjects"], snapshot, issues) if "subjects" in files else ()
    courses = _validate_courses(files["courses"], snapshot, issues) if "courses" in files else ()
    teachers = _validate_teachers(files["teachers"], snapshot, issues) if "teachers" in files else ()
    assignments = _validate_assignments(files["assignments"], snapshot, issues) if "assignments" in files else ()

    subject_names = {_key(item.name) for item in subjects} | {_key(item.name) for item in snapshot.subjects}
    course_abbreviations = {item.abbreviation.upper() for item in courses} | {item.abbreviation.upper() for item in snapshot.courses}
    class_names = {(item.course_abbreviation.upper(), _key(item.name)) for item in snapshot.classes}
    class_names.update((course.abbreviation.upper(), _key(cls.name)) for course in courses for cls in course.classes)
    teacher_emails = {_email(item.email) for item in teachers}
    existing_teacher_emails = {_email(item.email) for item in snapshot.teachers}
    inferred: dict[str, set[str]] = defaultdict(set)
    for teacher in teachers:
        inferred[teacher.email].update(teacher.competency_subjects)
        for competency_subject in teacher.competency_subjects:
            if _key(competency_subject) not in subject_names:
                issues.append(
                    _issue(
                        "teachers",
                        "competency_subject_reference_missing",
                        "A disciplina da competência não existe.",
                        line=teacher.line,
                        field="competency_subject",
                    )
                )
    for assignment in assignments:
        if assignment.course_abbreviation.upper() not in course_abbreviations:
            issues.append(_issue("assignments", "course_reference_missing", "O curso referenciado não existe.", line=assignment.line, field="course_abbreviation"))
        if (assignment.course_abbreviation.upper(), _key(assignment.class_name)) not in class_names:
            issues.append(_issue("assignments", "class_reference_missing", "A turma referenciada não existe nesse curso.", line=assignment.line, field="class_name"))
        if _key(assignment.subject_name) not in subject_names:
            issues.append(_issue("assignments", "subject_reference_missing", "A disciplina referenciada não existe.", line=assignment.line, field="subject_name"))
        if assignment.teacher_email:
            if assignment.teacher_email in existing_teacher_emails:
                issues.append(_issue("assignments", "teacher_existing_forbidden", "Professores existentes não podem ser usados em atribuições importadas.", line=assignment.line, field="teacher_email"))
            elif assignment.teacher_email not in teacher_emails:
                issues.append(_issue("assignments", "teacher_not_in_batch", "O professor deve ser criado no mesmo lote.", line=assignment.line, field="teacher_email"))
            else:
                inferred[assignment.teacher_email].add(assignment.subject_name)

    counts = {
        "rooms": len(rooms),
        "subjects": len(subjects),
        "modules": sum(len(item.modules) for item in subjects),
        "courses": len(courses),
        "classes": sum(len(item.classes) for item in courses),
        "teachers": len(teachers),
        "competencies": sum(len(values) for values in inferred.values()),
        "assignments": len(assignments),
    }
    preview = tuple(
        [{"resource": "rooms", "name": item.name, "line": item.line} for item in rooms]
        + [{"resource": "subjects", "name": item.name, "modules": len(item.modules), "line": item.line} for item in subjects]
        + [{"resource": "courses", "abbreviation": item.abbreviation, "classes": len(item.classes), "line": item.line} for item in courses]
        + [{"resource": "teachers", "email": item.email, "line": item.line} for item in teachers]
        + [{"resource": "assignments", "course_abbreviation": item.course_abbreviation, "class_name": item.class_name, "subject_name": item.subject_name, "line": item.line} for item in assignments]
    )[:100]
    return ValidationResult(
        tuple(issues), rooms, subjects, courses, teachers, assignments, counts, preview,
        {email: tuple(sorted(values, key=_key)) for email, values in inferred.items()},
    )
