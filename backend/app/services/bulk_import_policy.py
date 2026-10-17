"""Pure contracts, parsing and validation for administrative CSV imports."""

from __future__ import annotations

import base64
import csv
import io
import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import time
from email.utils import parseaddr
from typing import Literal

MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 5 * 1024 * 1024
MAX_LINES = 5_000
CLASS_AVAILABILITY = "class_availability"
TEACHER_AVAILABILITY = "teacher_availability"
TEACHER_PRESENCE = "teacher_presence"
TEACHER_PRESENCE_FILENAME = "Cronos_PresencaProfessores_Template.csv"
TEACHER_PRESENCE_HEADERS = (
    "Nome do professor",
    "Email do professor",
    "Hora de almoço",
    "Mínimo de horas por presença",
    "Furo máximo (horas)",
)
TEACHER_PRESENCE_FIELDS = ("name", "email", "lunch", "minimum_hours", "max_gap_hours")
IMPORT_RESOURCES = (
    "rooms",
    "subjects",
    "courses",
    "teachers",
    "assignments",
    CLASS_AVAILABILITY,
    TEACHER_AVAILABILITY,
    TEACHER_PRESENCE,
)
IssueSeverity = Literal["error", "warning"]


@dataclass(frozen=True)
class TemplateDefinition:
    headers: tuple[str, ...]
    fields: tuple[str, ...]
    example: tuple[str, ...]
    filename: str


TEMPLATE_DEFINITIONS = {
    "rooms": TemplateDefinition(
        ("Nome da sala", "Tipo de sala", "Capacidade"),
        ("name", "type", "capacity"),
        ("Sala de Exemplo", "Normal", "30"),
        "Cronos_Salas_Template.csv",
    ),
    "subjects": TemplateDefinition(
        (
            "Nome da disciplina",
            "Tipo de sala",
            "Nome do módulo",
            "Código do módulo",
            "Horas do módulo",
            "Ordem do módulo",
        ),
        (
            "name",
            "required_room_type",
            "module_name",
            "module_code",
            "module_hours",
            "module_order",
        ),
        ("Disciplina de Exemplo", "Normal", "Módulo de Exemplo", "MOD-EXEMPLO", "30", "1"),
        "Cronos_DisciplinasEModulos_Template.csv",
    ),
    "courses": TemplateDefinition(
        (
            "Sigla do curso",
            "Nome do curso",
            "Nome da turma",
            "Ano escolar",
            "Ano de início",
            "Ano de fim",
            "Número de alunos",
        ),
        ("abbreviation", "name", "class_name", "grade_level", "start_year", "end_year", "size"),
        ("EXEMPLO", "Curso de Exemplo", "Turma de Exemplo", "10", "2025", "2028", "25"),
        "Cronos_CursosETurmas_Template.csv",
    ),
    "teachers": TemplateDefinition(
        ("Nome do professor", "Email do professor", "Nome da disciplina"),
        ("name", "email", "competency_subject"),
        ("Professor de Exemplo", "professor.exemplo@example.invalid", "Disciplina de Exemplo"),
        "Cronos_ProfessoresECompetencias_Template.csv",
    ),
    "assignments": TemplateDefinition(
        ("Sigla do curso", "Nome da turma", "Nome da disciplina", "Email do professor"),
        ("course_abbreviation", "class_name", "subject_name", "teacher_email"),
        (
            "EXEMPLO",
            "Turma de Exemplo",
            "Disciplina de Exemplo",
            "professor.exemplo@example.invalid",
        ),
        "Cronos_Atribuicoes_Template.csv",
    ),
}

FILE_READ_ERROR_MESSAGE = (
    "Não foi possível ler este ficheiro. Descarregue novamente o modelo e guarde-o como CSV."
)
RESOURCE_MISMATCH_MESSAGE = (
    "Este ficheiro não corresponde à secção escolhida. Selecione o modelo correspondente."
)
ROOM_TYPE_MISSING_MESSAGE = "Escreva o tipo de sala."
ROOM_TYPE_UNKNOWN_MESSAGE = "Não existe um tipo de sala com esse nome."
AVAILABILITY_DAY_ERROR_MESSAGE = "Escreva um dia com blocos na grelha, por exemplo Segunda."
AVAILABILITY_LEVEL_ERROR_MESSAGE = "Escreva Impossível, Evitar, Neutro ou Preferencial."
TEACHER_PRESENCE_LUNCH_ERROR_MESSAGE = "Escreva Sim ou Não."
TEACHER_PRESENCE_MINIMUM_ERROR_MESSAGE = "Escreva um número inteiro de horas entre 1 e 12."
TEACHER_PRESENCE_GAP_ERROR_MESSAGE = "Escreva um número inteiro de horas entre 0 e 12."
TEACHER_PRESENCE_GAP_WITHOUT_MINIMUM_MESSAGE = "O furo máximo só se aplica com um mínimo de horas."
TEACHER_PRESENCE_UNKNOWN_TEACHER_MESSAGE = "Professor não encontrado."
TEACHER_PRESENCE_DUPLICATE_EMAIL_MESSAGE = "Este email aparece em mais de uma linha."

NEUTRAL_SCORE = 1
_HOUR_PATTERN = re.compile(r"^(\d{1,2}):([0-5]\d)(?::[0-5]\d)?$")
_LEVEL_SCORES = {"impossivel": -1, "evitar": 0, "neutro": NEUTRAL_SCORE, "preferencial": 2}
_LEVEL_LABELS = {-1: "Impossível", 0: "Evitar", NEUTRAL_SCORE: "Neutro", 2: "Preferencial"}
_DAY_VALUES = {
    "segunda": 0,
    "terca": 1,
    "quarta": 2,
    "quinta": 3,
    "sexta": 4,
    "sabado": 5,
    "domingo": 6,
}
_DAY_LABELS = ("Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo")


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
    # weekly availability grid dynamic header: normalized ``HH:MM`` hours and their
    # original column titles, in header order.
    hours: tuple[str, ...] = ()
    hour_titles: tuple[str, ...] = ()


@dataclass(frozen=True)
class RoomImport:
    name: str
    room_type_id: int
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
    room_type_id: int
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
class ExistingRoomType:
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
    is_active: bool = False
    lunch_required: bool = True
    minimum_hours: int | None = None
    max_gap_hours: int | None = None


@dataclass(frozen=True)
class ExistingAssignment:
    course_abbreviation: str
    class_name: str
    subject_name: str


@dataclass(frozen=True)
class ExistingTimeslot:
    id: int
    day_of_week: int
    start_time: time


@dataclass(frozen=True)
class ClassAvailabilityImport:
    course_abbreviation: str
    class_name: str
    line: int
    scores: dict[int, int]
    changed_blocks: int = 0


@dataclass(frozen=True)
class TeacherAvailabilityImport:
    teacher_name: str
    teacher_email: str
    line: int
    scores: dict[int, int]
    changed_blocks: int = 0


@dataclass(frozen=True)
class TeacherPresenceImport:
    email: str
    lunch_required: bool
    minimum_hours: int | None
    max_gap_hours: int | None
    line: int


@dataclass
class ImportSnapshot:
    rooms: list[ExistingRoom] = field(default_factory=list)
    subjects: list[ExistingSubject] = field(default_factory=list)
    room_types: list[ExistingRoomType] = field(default_factory=list)
    courses: list[ExistingCourse] = field(default_factory=list)
    classes: list[ExistingClass] = field(default_factory=list)
    teachers: list[ExistingTeacher] = field(default_factory=list)
    assignments: list[ExistingAssignment] = field(default_factory=list)
    timeslots: list[ExistingTimeslot] = field(default_factory=list)
    # Current stored levels per class and teacher, loaded only for availability files.
    class_availability: dict[int, dict[int, int]] = field(default_factory=dict)
    teacher_availability: dict[int, dict[int, int]] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidationResult:
    issues: tuple[BulkImportIssue, ...]
    rooms: tuple[RoomImport, ...] = ()
    subjects: tuple[SubjectImport, ...] = ()
    courses: tuple[CourseImport, ...] = ()
    teachers: tuple[TeacherImport, ...] = ()
    assignments: tuple[AssignmentImport, ...] = ()
    class_availability: tuple[ClassAvailabilityImport, ...] = ()
    teacher_availability: tuple[TeacherAvailabilityImport, ...] = ()
    counts: dict[str, int] = field(default_factory=dict)
    preview: tuple[dict, ...] = ()
    inferred_competencies: dict[str, tuple[str, ...]] = field(default_factory=dict)
    teacher_presence: tuple[TeacherPresenceImport, ...] = ()

    @property
    def can_commit(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)


def _issue(
    resource: str,
    code: str,
    message: str,
    *,
    line: int | None = None,
    field: str | None = None,
    severity: IssueSeverity = "error",
) -> BulkImportIssue:
    return BulkImportIssue(code, severity, resource, line, field, message)


def _clean(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _key(value: str) -> str:
    return _clean(value).casefold()


def fold_text(value: str) -> str:
    """Lowercase and strip accents, so users may type ``Impossível`` or ``impossivel``."""
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", _clean(value).casefold())
        if not unicodedata.combining(character)
    )


def normalize_room_type(value: str, snapshot: ImportSnapshot) -> ExistingRoomType | None:
    """O tipo de sala da escola com este nome, dobrado por maiúsculas e acentos."""
    folded = fold_text(value)
    for room_type in snapshot.room_types:
        if fold_text(room_type.name) == folded:
            return room_type
    return None


def normalize_hour(value: str) -> str | None:
    """Accept ``H:MM``, ``HH:MM`` and ``HH:MM:SS`` and return ``HH:MM``."""
    match = _HOUR_PATTERN.match(_clean(value))
    if match is None or int(match.group(1)) > 23:
        return None
    return f"{int(match.group(1)):02d}:{int(match.group(2)):02d}"


def normalize_day(value: str) -> int | None:
    """Accept a Portuguese day name with or without ``-feira``, accents or case."""
    plain = fold_text(value)
    for suffix in ("-feira", "feira"):
        if plain.endswith(suffix):
            plain = plain[: -len(suffix)]
            break
    return _DAY_VALUES.get(plain.strip())


def normalize_level(value: str) -> int | None:
    return _LEVEL_SCORES.get(fold_text(value))


def normalize_yes_no(value: str) -> bool | None:
    """Accept ``Sim``/``Não`` without case or accents; an empty cell means Sim."""
    folded = fold_text(value)
    if not folded:
        return True
    if folded == "sim":
        return True
    if folded == "nao":
        return False
    return None


def _email(value: str) -> str:
    return _clean(value).lower()


def _valid_email(value: str) -> bool:
    parsed = parseaddr(value)[1]
    return parsed == value and "@" in value and not value.endswith("@") and " " not in value


@dataclass(frozen=True)
class AvailabilityResource:
    """A weekly availability grid resource: headers, fields, filename and row accessors."""

    filename: str
    fixed_headers: tuple[str, ...]
    fields: tuple[str, ...]
    values: Callable[[object], tuple[str, str]]
    sort_key: Callable[[object], tuple]


AVAILABILITY_RESOURCES: dict[str, AvailabilityResource] = {
    CLASS_AVAILABILITY: AvailabilityResource(
        filename="Cronos_DisponibilidadeTurmas_Template.csv",
        fixed_headers=("Sigla do curso", "Nome da turma", "Dia"),
        fields=("course_abbreviation", "class_name", "day"),
        values=lambda item: (item.course_abbreviation, item.name),
        sort_key=lambda item: (item.course_abbreviation, item.name),
    ),
    TEACHER_AVAILABILITY: AvailabilityResource(
        filename="Cronos_DisponibilidadeProfessores_Template.csv",
        fixed_headers=("Nome do professor", "Email do professor", "Dia"),
        fields=("teacher_name", "teacher_email", "day"),
        values=lambda item: (item.name, item.email),
        sort_key=lambda item: (item.name.casefold(), _email(item.email)),
    ),
}


def _matches_availability_grid(headers: list[str], *, except_resource: str | None = None) -> bool:
    return any(
        resource != except_resource
        and tuple(headers[: len(definition.fixed_headers)]) == definition.fixed_headers
        for resource, definition in AVAILABILITY_RESOURCES.items()
    )


def render_template(resource: str) -> bytes:
    definition = TEMPLATE_DEFINITIONS.get(resource)
    if definition is None:
        raise KeyError(resource)
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow(definition.headers)
    writer.writerow(definition.example)
    return b"\xef\xbb\xbf" + output.getvalue().encode("utf-8")


def template_filename(resource: str) -> str:
    if resource in AVAILABILITY_RESOURCES:
        return AVAILABILITY_RESOURCES[resource].filename
    if resource == TEACHER_PRESENCE:
        return TEACHER_PRESENCE_FILENAME
    return TEMPLATE_DEFINITIONS[resource].filename


def render_availability_template(
    resource: str,
    timeslots: list[ExistingTimeslot] | tuple[ExistingTimeslot, ...],
    entities: list[ExistingClass | ExistingTeacher] | tuple[ExistingClass | ExistingTeacher, ...],
    scores: dict[int, dict[int, int]],
) -> bytes:
    """Render a weekly availability model from the visible grid, its entities and levels."""
    definition = AVAILABILITY_RESOURCES[resource]
    hours = sorted({block.start_time.strftime("%H:%M") for block in timeslots})
    timeslot_by_day_hour = {
        (block.day_of_week, block.start_time.strftime("%H:%M")): block.id for block in timeslots
    }
    days = sorted({block.day_of_week for block in timeslots})
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow([*definition.fixed_headers, *hours])
    for item in sorted(entities, key=definition.sort_key):
        item_scores = scores.get(item.id, {})
        for day in days:
            cells = []
            for hour in hours:
                timeslot_id = timeslot_by_day_hour.get((day, hour))
                if timeslot_id is None:
                    cells.append("")
                else:
                    cells.append(
                        _LEVEL_LABELS.get(item_scores.get(timeslot_id, NEUTRAL_SCORE), "Neutro")
                    )
            writer.writerow([*definition.values(item), _DAY_LABELS[day], *cells])
    return b"\xef\xbb\xbf" + output.getvalue().encode("utf-8")


def render_teacher_presence_template(
    teachers: list[ExistingTeacher] | tuple[ExistingTeacher, ...],
) -> bytes:
    """Render the teacher-presence model from the active teachers and their current rule."""
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow(TEACHER_PRESENCE_HEADERS)
    for item in sorted(teachers, key=lambda teacher: (_key(teacher.name), teacher.id)):
        writer.writerow(
            [
                item.name,
                item.email,
                "Sim" if item.lunch_required else "Não",
                "" if item.minimum_hours is None else str(item.minimum_hours),
                "" if item.max_gap_hours is None else str(item.max_gap_hours),
            ]
        )
    return b"\xef\xbb\xbf" + output.getvalue().encode("utf-8")


def parse_resource_file(resource: str, filename: str, content_base64: str) -> ParsedResourceFile:
    if (
        resource not in TEMPLATE_DEFINITIONS
        and resource not in AVAILABILITY_RESOURCES
        and resource != TEACHER_PRESENCE
    ):
        return ParsedResourceFile(
            resource,
            filename,
            issues=(_issue(resource, "resource_unknown", "Secção de importação desconhecida."),),
        )
    try:
        raw = base64.b64decode(content_base64, validate=True)
    except (ValueError, TypeError):
        return ParsedResourceFile(
            resource,
            filename,
            issues=(_issue(resource, "base64_invalid", FILE_READ_ERROR_MESSAGE),),
        )
    if len(raw) > MAX_FILE_BYTES:
        return ParsedResourceFile(
            resource,
            filename,
            issues=(_issue(resource, "file_too_large", "O ficheiro excede 1 MB."),),
            decoded_bytes=len(raw),
        )
    try:
        text = (
            raw[3:].decode("utf-8", errors="strict")
            if raw.startswith(b"\xef\xbb\xbf")
            else raw.decode("utf-8", errors="strict")
        )
    except UnicodeDecodeError:
        return ParsedResourceFile(
            resource,
            filename,
            issues=(_issue(resource, "utf8_invalid", FILE_READ_ERROR_MESSAGE),),
            decoded_bytes=len(raw),
        )
    if "\x00" in text:
        return ParsedResourceFile(
            resource,
            filename,
            issues=(_issue(resource, "nul_byte", FILE_READ_ERROR_MESSAGE),),
            decoded_bytes=len(raw),
        )
    physical_lines = len(text.splitlines())
    if physical_lines > MAX_LINES:
        return ParsedResourceFile(
            resource,
            filename,
            issues=(_issue(resource, "line_limit_exceeded", FILE_READ_ERROR_MESSAGE),),
            decoded_bytes=len(raw),
        )

    if resource in AVAILABILITY_RESOURCES:
        return _parse_availability_file(
            resource, AVAILABILITY_RESOURCES[resource], filename, text, len(raw)
        )
    if resource == TEACHER_PRESENCE:
        return _parse_teacher_presence_file(resource, filename, text, len(raw))

    definition = TEMPLATE_DEFINITIONS[resource]
    delimiter = None
    resource_mismatch = False
    for candidate in (",", ";"):
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=candidate)
        try:
            headers = next(reader)
        except StopIteration:
            headers = []
        if headers == list(definition.headers):
            delimiter = candidate
            break
        if any(
            other_resource != resource and headers == list(other_definition.headers)
            for other_resource, other_definition in TEMPLATE_DEFINITIONS.items()
        ):
            resource_mismatch = True
        if _matches_availability_grid(headers):
            resource_mismatch = True
    if delimiter is None:
        return ParsedResourceFile(
            resource,
            filename,
            issues=(
                _issue(
                    resource,
                    "resource_mismatch" if resource_mismatch else "header_invalid",
                    RESOURCE_MISMATCH_MESSAGE if resource_mismatch else FILE_READ_ERROR_MESSAGE,
                    line=1,
                ),
            ),
            decoded_bytes=len(raw),
        )

    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    next(reader, None)
    rows: list[dict[str, str | int]] = []
    issues: list[BulkImportIssue] = []
    for values in reader:
        line = reader.line_num
        if not any(_clean(value) for value in values):
            continue
        if len(values) != len(definition.fields):
            issues.append(
                _issue(
                    resource,
                    "column_count_invalid",
                    FILE_READ_ERROR_MESSAGE,
                    line=line,
                )
            )
            continue
        row = {field: _clean(value) for field, value in zip(definition.fields, values, strict=True)}
        row["line"] = line
        rows.append(row)
        if tuple(row[field] for field in definition.fields) == definition.example:
            issues.append(
                _issue(
                    resource,
                    "template_example_present",
                    "Substitua a linha oficial de exemplo antes de importar.",
                    line=line,
                )
            )
    if not rows:
        issues.append(
            _issue(resource, "no_data", "Selecione um ficheiro com pelo menos uma linha real.")
        )
    return ParsedResourceFile(resource, filename, tuple(rows), tuple(issues), len(raw))


def _parse_availability_file(
    resource: str,
    definition: AvailabilityResource,
    filename: str,
    text: str,
    decoded_bytes: int,
) -> ParsedResourceFile:
    """Parse the dynamic header: three fixed columns then sorted distinct hour columns."""
    delimiter = None
    resource_mismatch = False
    for candidate in (",", ";"):
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=candidate)
        try:
            headers = next(reader)
        except StopIteration:
            headers = []
        if tuple(headers[: len(definition.fixed_headers)]) == definition.fixed_headers:
            delimiter = candidate
            break
        if any(headers == list(other.headers) for other in TEMPLATE_DEFINITIONS.values()):
            resource_mismatch = True
        if _matches_availability_grid(headers, except_resource=resource):
            resource_mismatch = True
    if delimiter is None:
        return ParsedResourceFile(
            resource,
            filename,
            issues=(
                _issue(
                    resource,
                    "resource_mismatch" if resource_mismatch else "header_invalid",
                    RESOURCE_MISMATCH_MESSAGE if resource_mismatch else FILE_READ_ERROR_MESSAGE,
                    line=1,
                ),
            ),
            decoded_bytes=decoded_bytes,
        )

    hours: list[str] = []
    hour_titles: list[str] = []
    for title in headers[len(definition.fixed_headers) :]:
        cleaned = _clean(title)
        hour = normalize_hour(cleaned)
        if hour is None or hour in hours:
            return ParsedResourceFile(
                resource,
                filename,
                issues=(_issue(resource, "header_invalid", FILE_READ_ERROR_MESSAGE, line=1),),
                decoded_bytes=decoded_bytes,
            )
        hours.append(hour)
        hour_titles.append(cleaned)

    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    next(reader, None)
    rows: list[dict[str, str | int]] = []
    issues: list[BulkImportIssue] = []
    field_names = definition.fields
    for values in reader:
        line = reader.line_num
        if not any(_clean(value) for value in values):
            continue
        if len(values) != len(headers):
            issues.append(
                _issue(resource, "column_count_invalid", FILE_READ_ERROR_MESSAGE, line=line)
            )
            continue
        row: dict[str, str | int] = {
            field_name: _clean(value)
            for field_name, value in zip(field_names, values[: len(field_names)], strict=True)
        }
        row.update(
            {
                title: _clean(value)
                for title, value in zip(hour_titles, values[len(field_names) :], strict=True)
            }
        )
        row["line"] = line
        rows.append(row)
    if not rows:
        issues.append(
            _issue(resource, "no_data", "Selecione um ficheiro com pelo menos uma linha real.")
        )
    return ParsedResourceFile(
        resource,
        filename,
        tuple(rows),
        tuple(issues),
        decoded_bytes,
        tuple(hours),
        tuple(hour_titles),
    )


def _parse_teacher_presence_file(
    resource: str, filename: str, text: str, decoded_bytes: int
) -> ParsedResourceFile:
    """Parse the teacher-presence model: five fixed columns, no example row."""
    delimiter = None
    resource_mismatch = False
    for candidate in (",", ";"):
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=candidate)
        try:
            headers = next(reader)
        except StopIteration:
            headers = []
        if tuple(headers) == TEACHER_PRESENCE_HEADERS:
            delimiter = candidate
            break
        if any(headers == list(definition.headers) for definition in TEMPLATE_DEFINITIONS.values()):
            resource_mismatch = True
    if delimiter is None:
        return ParsedResourceFile(
            resource,
            filename,
            issues=(
                _issue(
                    resource,
                    "resource_mismatch" if resource_mismatch else "header_invalid",
                    RESOURCE_MISMATCH_MESSAGE if resource_mismatch else FILE_READ_ERROR_MESSAGE,
                    line=1,
                ),
            ),
            decoded_bytes=decoded_bytes,
        )

    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    next(reader, None)
    rows: list[dict[str, str | int]] = []
    issues: list[BulkImportIssue] = []
    for values in reader:
        line = reader.line_num
        if not any(_clean(value) for value in values):
            continue
        if len(values) != len(TEACHER_PRESENCE_FIELDS):
            issues.append(
                _issue(resource, "column_count_invalid", FILE_READ_ERROR_MESSAGE, line=line)
            )
            continue
        row = {
            field: _clean(value)
            for field, value in zip(TEACHER_PRESENCE_FIELDS, values, strict=True)
        }
        row["line"] = line
        rows.append(row)
    if not rows:
        issues.append(
            _issue(resource, "no_data", "Selecione um ficheiro com pelo menos uma linha real.")
        )
    return ParsedResourceFile(resource, filename, tuple(rows), tuple(issues), decoded_bytes)


def _value(row: dict, field: str) -> str:
    return _clean(row.get(field, ""))


def _int_value(
    row: dict,
    resource: str,
    field: str,
    issues: list[BulkImportIssue],
    *,
    minimum: int | None = None,
) -> int | None:
    raw = _value(row, field)
    if not raw:
        issues.append(
            _issue(
                resource, "field_required", "Campo obrigatório.", line=int(row["line"]), field=field
            )
        )
        return None
    try:
        value = int(raw)
    except ValueError:
        issues.append(
            _issue(
                resource,
                "integer_invalid",
                "Indique um número inteiro.",
                line=int(row["line"]),
                field=field,
            )
        )
        return None
    if minimum is not None and value < minimum:
        issues.append(
            _issue(
                resource,
                "integer_out_of_range",
                f"O valor deve ser maior ou igual a {minimum}.",
                line=int(row["line"]),
                field=field,
            )
        )
        return None
    return value


def _room_type_issue(
    resource: str,
    value: str,
    room_type: ExistingRoomType | None,
    *,
    line: int,
    field: str,
) -> BulkImportIssue | None:
    """O tipo em branco é campo obrigatório; o desconhecido não existe na escola."""
    if not _clean(value):
        return _issue(
            resource, "room_type_invalid", ROOM_TYPE_MISSING_MESSAGE, line=line, field=field
        )
    if room_type is None:
        return _issue(
            resource, "room_type_unknown", ROOM_TYPE_UNKNOWN_MESSAGE, line=line, field=field
        )
    return None


def _validate_rooms(
    parsed: ParsedResourceFile, snapshot: ImportSnapshot, issues: list[BulkImportIssue]
) -> tuple[RoomImport, ...]:
    result = []
    seen = set()
    existing = {_key(item.name) for item in snapshot.rooms}
    for row in parsed.rows:
        line = int(row["line"])
        name = _value(row, "name")
        raw_type = _value(row, "type")
        room_type = normalize_room_type(raw_type, snapshot)
        capacity = _int_value(row, "rooms", "capacity", issues, minimum=1)
        if not name:
            issues.append(
                _issue("rooms", "field_required", "Campo obrigatório.", line=line, field="name")
            )
        type_issue = _room_type_issue("rooms", raw_type, room_type, line=line, field="type")
        if type_issue is not None:
            issues.append(type_issue)
        normalized = _key(name)
        if normalized in seen:
            issues.append(
                _issue(
                    "rooms",
                    "duplicate_in_batch",
                    "A sala está repetida no lote.",
                    line=line,
                    field="name",
                )
            )
        if normalized in existing:
            issues.append(
                _issue(
                    "rooms",
                    "duplicate_existing",
                    "Já existe uma sala com este nome.",
                    line=line,
                    field="name",
                )
            )
        seen.add(normalized)
        if name and room_type is not None and capacity is not None:
            result.append(RoomImport(name, room_type.id, capacity, line))
    return tuple(result)


def _validate_subjects(
    parsed: ParsedResourceFile, snapshot: ImportSnapshot, issues: list[BulkImportIssue]
) -> tuple[SubjectImport, ...]:
    groups: dict[str, list[dict]] = defaultdict(list)
    existing = {_key(item.name) for item in snapshot.subjects}
    for row in parsed.rows:
        groups[_key(_value(row, "name"))].append(row)
    result = []
    for normalized, rows in groups.items():
        first = rows[0]
        line = int(first["line"])
        name = _value(first, "name")
        raw_type = _value(first, "required_room_type")
        room_type = normalize_room_type(raw_type, snapshot)
        if not name:
            issues.append(
                _issue("subjects", "field_required", "Campo obrigatório.", line=line, field="name")
            )
        type_issue = _room_type_issue(
            "subjects", raw_type, room_type, line=line, field="required_room_type"
        )
        if type_issue is not None:
            issues.append(type_issue)
        if normalized in existing:
            issues.append(
                _issue(
                    "subjects",
                    "duplicate_existing",
                    "Já existe uma disciplina com este nome.",
                    line=line,
                    field="name",
                )
            )
        modules = []
        seen_orders = set()
        for row in rows:
            row_line = int(row["line"])
            current_type = normalize_room_type(_value(row, "required_room_type"), snapshot)
            if current_type != room_type:
                issues.append(
                    _issue(
                        "subjects",
                        "parent_contradiction",
                        "A disciplina repete-se com tipos de sala contraditórios.",
                        line=row_line,
                        field="required_room_type",
                    )
                )
            values = [
                _value(row, field)
                for field in ("module_name", "module_code", "module_hours", "module_order")
            ]
            if not any(values):
                continue
            if not all(values[0::1]):
                issues.append(
                    _issue(
                        "subjects",
                        "module_partial",
                        "Preencha todos os campos do módulo ou deixe-os todos vazios.",
                        line=row_line,
                        field="module_name",
                    )
                )
                continue
            hours = _int_value(row, "subjects", "module_hours", issues, minimum=1)
            order = _int_value(row, "subjects", "module_order", issues, minimum=1)
            if order in seen_orders:
                issues.append(
                    _issue(
                        "subjects",
                        "module_order_duplicate",
                        "A ordem do módulo está repetida.",
                        line=row_line,
                        field="module_order",
                    )
                )
            seen_orders.add(order)
            if hours is not None and order is not None:
                modules.append(
                    ModuleImport(
                        _value(row, "module_name"),
                        _value(row, "module_code") or None,
                        hours,
                        order,
                        row_line,
                    )
                )
        if not modules:
            issues.append(
                _issue(
                    "subjects",
                    "subject_without_modules",
                    "A disciplina será criada sem módulos.",
                    line=line,
                    field="module_name",
                    severity="warning",
                )
            )
        elif sorted(item.order for item in modules) != list(range(1, len(modules) + 1)):
            issues.append(
                _issue(
                    "subjects",
                    "module_order_not_continuous",
                    "As ordens dos módulos devem ser contínuas de 1 até n.",
                    line=line,
                    field="module_order",
                )
            )
        if name and room_type is not None:
            result.append(
                SubjectImport(
                    name,
                    room_type.id,
                    tuple(sorted(modules, key=lambda item: item.order)),
                    line,
                )
            )
    return tuple(result)


def _validate_courses(
    parsed: ParsedResourceFile, snapshot: ImportSnapshot, issues: list[BulkImportIssue]
) -> tuple[CourseImport, ...]:
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
            issues.append(
                _issue(
                    "courses",
                    "field_required",
                    "Campo obrigatório.",
                    line=line,
                    field="abbreviation",
                )
            )
        if not name:
            issues.append(
                _issue("courses", "field_required", "Campo obrigatório.", line=line, field="name")
            )
        if abbreviation in existing:
            issues.append(
                _issue(
                    "courses",
                    "duplicate_existing",
                    "Já existe um curso com esta sigla.",
                    line=line,
                    field="abbreviation",
                )
            )
        classes = []
        seen_class_names = set()
        for row in rows:
            row_line = int(row["line"])
            class_values = [
                _value(row, field)
                for field in ("class_name", "grade_level", "start_year", "end_year", "size")
            ]
            if not any(class_values):
                continue
            if not all(class_values):
                issues.append(
                    _issue(
                        "courses",
                        "class_partial",
                        "Preencha todos os campos da turma ou deixe-os todos vazios.",
                        line=row_line,
                        field="class_name",
                    )
                )
                continue
            grade = _int_value(row, "courses", "grade_level", issues, minimum=10)
            start = _int_value(row, "courses", "start_year", issues)
            end = _int_value(row, "courses", "end_year", issues)
            size = _int_value(row, "courses", "size", issues, minimum=1)
            if grade is not None and grade > 12:
                issues.append(
                    _issue(
                        "courses",
                        "grade_invalid",
                        "O ano deve ser 10, 11 ou 12.",
                        line=row_line,
                        field="grade_level",
                    )
                )
            if start is not None and end is not None and end <= start:
                issues.append(
                    _issue(
                        "courses",
                        "year_range_invalid",
                        "O ano final deve ser maior que o inicial.",
                        line=row_line,
                        field="end_year",
                    )
                )
            class_key = _key(_value(row, "class_name"))
            if class_key in seen_class_names:
                issues.append(
                    _issue(
                        "courses",
                        "duplicate_in_batch",
                        "A turma está repetida no lote.",
                        line=row_line,
                        field="class_name",
                    )
                )
            seen_class_names.add(class_key)
            if (
                grade is not None
                and 10 <= grade <= 12
                and start is not None
                and end is not None
                and end > start
                and size is not None
            ):
                classes.append(
                    ClassImport(_value(row, "class_name"), grade, start, end, size, row_line)
                )
        if not classes:
            issues.append(
                _issue(
                    "courses",
                    "course_without_classes",
                    "O curso será criado sem turmas.",
                    line=line,
                    field="class_name",
                    severity="warning",
                )
            )
        if name and abbreviation:
            for row in rows[1:]:
                if _value(row, "name") and _value(row, "name") != name:
                    issues.append(
                        _issue(
                            "courses",
                            "parent_contradiction",
                            "A sigla repete-se com nomes contraditórios.",
                            line=int(row["line"]),
                            field="name",
                        )
                    )
            result.append(CourseImport(abbreviation, name, tuple(classes), line))
    return tuple(result)


def _validate_teachers(
    parsed: ParsedResourceFile, snapshot: ImportSnapshot, issues: list[BulkImportIssue]
) -> tuple[TeacherImport, ...]:
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
            issues.append(
                _issue("teachers", "field_required", "Campo obrigatório.", line=line, field="name")
            )
        if not _valid_email(email):
            issues.append(
                _issue(
                    "teachers",
                    "email_invalid",
                    "Indique um email válido.",
                    line=line,
                    field="email",
                )
            )
        if email in existing:
            issues.append(
                _issue(
                    "teachers",
                    "teacher_existing_forbidden",
                    "Professores existentes não podem ser referenciados pelo importador.",
                    line=line,
                    field="email",
                )
            )
        subjects = []
        seen_subjects = set()
        for row in rows:
            current_name = _value(row, "name")
            if current_name and name and current_name != name:
                issues.append(
                    _issue(
                        "teachers",
                        "parent_contradiction",
                        "O email repete-se com nomes contraditórios.",
                        line=int(row["line"]),
                        field="name",
                    )
                )
            subject = _value(row, "competency_subject")
            if subject and _key(subject) not in seen_subjects:
                subjects.append(subject)
                seen_subjects.add(_key(subject))
        if not subjects:
            issues.append(
                _issue(
                    "teachers",
                    "teacher_without_competencies",
                    "O professor será criado sem competências.",
                    line=line,
                    field="competency_subject",
                    severity="warning",
                )
            )
        if name and _valid_email(email):
            result.append(TeacherImport(name, email, tuple(subjects), line))
    return tuple(result)


def _validate_assignments(
    parsed: ParsedResourceFile, snapshot: ImportSnapshot, issues: list[BulkImportIssue]
) -> tuple[AssignmentImport, ...]:
    result = []
    seen = set()
    existing = {
        (_key(item.course_abbreviation), _key(item.class_name), _key(item.subject_name))
        for item in snapshot.assignments
    }
    for row in parsed.rows:
        line = int(row["line"])
        course = _value(row, "course_abbreviation").upper()
        class_name = _value(row, "class_name")
        subject = _value(row, "subject_name")
        teacher = _email(_value(row, "teacher_email")) or None
        for field_name, value in (
            ("course_abbreviation", course),
            ("class_name", class_name),
            ("subject_name", subject),
        ):
            if not value:
                issues.append(
                    _issue(
                        "assignments",
                        "field_required",
                        "Campo obrigatório.",
                        line=line,
                        field=field_name,
                    )
                )
        key = (_key(course), _key(class_name), _key(subject))
        if key in seen:
            issues.append(
                _issue(
                    "assignments",
                    "duplicate_in_batch",
                    "A atribuição está repetida no lote.",
                    line=line,
                )
            )
        if key in existing:
            issues.append(
                _issue(
                    "assignments",
                    "assignment_existing",
                    "A atribuição já existe na organização.",
                    line=line,
                )
            )
        seen.add(key)
        if teacher is None:
            issues.append(
                _issue(
                    "assignments",
                    "teacher_missing_warning",
                    "A atribuição ficará sem professor.",
                    line=line,
                    field="teacher_email",
                    severity="warning",
                )
            )
        result.append(AssignmentImport(course, class_name, subject, teacher, line))
    return tuple(result)


@dataclass(frozen=True)
class _AvailabilityTarget:
    """Where an availability row points: current-scores key, grouping key and identity."""

    current_key: int | None
    duplicate_key: object
    identity: tuple[str, str]


@dataclass
class _MergedAvailability:
    target: _AvailabilityTarget
    line: int
    scores: dict[int, int]
    changed_blocks: int = 0


def _validate_availability(
    resource: str,
    parsed: ParsedResourceFile,
    snapshot: ImportSnapshot,
    current_scores: dict[int, dict[int, int]],
    resolve: Callable[[dict, list[BulkImportIssue]], _AvailabilityTarget | None],
    issues: list[BulkImportIssue],
    *,
    duplicate_code: str,
    duplicate_message: str,
    all_impossible_message: str,
) -> list[_MergedAvailability]:
    """Validate a weekly grid shared by classes and teachers.

    ``resolve`` maps a row to its entity and records the resource-specific
    reference errors. Hours, days, cells, duplicates, the merged grid, changed
    blocks and the all-impossible warning are shared by both resources.
    """
    grid_hours = sorted({block.start_time.strftime("%H:%M") for block in snapshot.timeslots})
    days_with_blocks = {block.day_of_week for block in snapshot.timeslots}
    timeslot_by_day_hour = {
        (block.day_of_week, block.start_time.strftime("%H:%M")): block.id
        for block in snapshot.timeslots
    }
    header_hours = set(parsed.hours)
    for hour, title in zip(parsed.hours, parsed.hour_titles, strict=True):
        if hour not in grid_hours:
            issues.append(
                _issue(
                    resource,
                    "unknown_hour",
                    f"A grelha não tem blocos que comecem às {hour}. Descarregue um modelo novo.",
                    line=1,
                    field=title,
                )
            )
    for hour in grid_hours:
        if hour not in header_hours:
            issues.append(
                _issue(
                    resource,
                    "missing_hour",
                    f"Falta a coluna {hour}. Descarregue um modelo novo.",
                    line=1,
                )
            )

    # Every day line of an entity merges into one aggregate, so the commit
    # replaces the whole grid exactly once per entity (D05, D14).
    entries: dict[object, _MergedAvailability] = {}
    seen: set[tuple[object, int]] = set()
    for row in parsed.rows:
        line = int(row["line"])
        target = resolve(row, issues)
        day = normalize_day(_value(row, "day"))
        day_valid = day is not None and day in days_with_blocks
        if not day_valid:
            issues.append(
                _issue(
                    resource,
                    "day_invalid",
                    AVAILABILITY_DAY_ERROR_MESSAGE,
                    line=line,
                    field="day",
                )
            )
        if target is not None:
            row_key = (target.duplicate_key, day if day is not None else -1)
            if row_key in seen:
                issues.append(_issue(resource, duplicate_code, duplicate_message, line=line))
            seen.add(row_key)
        # A line without a valid day or entity cannot map cells to blocks. Its own
        # errors are already recorded, so skip cell lookups to avoid block noise.
        if target is None or not day_valid:
            continue
        entry = entries.get(target.duplicate_key)
        if entry is None:
            entry = _MergedAvailability(target, line, {})
            entries[target.duplicate_key] = entry
        for title, hour in zip(parsed.hour_titles, parsed.hours, strict=True):
            cell = _value(row, title)
            if not cell:
                continue
            level = normalize_level(cell)
            if level is None:
                issues.append(
                    _issue(
                        resource,
                        "level_invalid",
                        AVAILABILITY_LEVEL_ERROR_MESSAGE,
                        line=line,
                        field=title,
                    )
                )
                continue
            timeslot_id = timeslot_by_day_hour.get((day, hour))
            if timeslot_id is None:
                issues.append(
                    _issue(
                        resource,
                        "hour_without_block",
                        f"Este dia não tem bloco às {hour}. Deixe a célula vazia.",
                        line=line,
                        field=title,
                    )
                )
                continue
            if level != NEUTRAL_SCORE:
                entry.scores[timeslot_id] = level

    visible_blocks = snapshot.timeslots
    for entry in entries.values():
        current = (
            current_scores.get(entry.target.current_key, {})
            if entry.target.current_key is not None
            else {}
        )
        entry.changed_blocks = sum(
            1
            for block in visible_blocks
            if entry.scores.get(block.id, NEUTRAL_SCORE) != current.get(block.id, NEUTRAL_SCORE)
        )
        if visible_blocks and all(
            entry.scores.get(block.id, NEUTRAL_SCORE) == -1 for block in visible_blocks
        ):
            issues.append(
                _issue(
                    resource, "all_blocks_impossible", all_impossible_message, severity="warning"
                )
            )
    return list(entries.values())


def _validate_class_availability(
    parsed: ParsedResourceFile,
    snapshot: ImportSnapshot,
    class_names: set[tuple[str, str]],
    class_ids: dict[tuple[str, str], int],
    issues: list[BulkImportIssue],
) -> tuple[ClassAvailabilityImport, ...]:
    def resolve(row: dict, issues: list[BulkImportIssue]) -> _AvailabilityTarget | None:
        course = _value(row, "course_abbreviation").upper()
        class_name = _value(row, "class_name")
        key = (course, _key(class_name))
        if key not in class_names:
            issues.append(
                _issue(
                    CLASS_AVAILABILITY,
                    "class_reference_missing",
                    "A turma referenciada não existe nesse curso.",
                    line=int(row["line"]),
                    field="class_name",
                )
            )
            return None
        return _AvailabilityTarget(class_ids.get(key), key, (course, class_name))

    merged = _validate_availability(
        CLASS_AVAILABILITY,
        parsed,
        snapshot,
        snapshot.class_availability,
        resolve,
        issues,
        duplicate_code="duplicate_class_day",
        duplicate_message="Esta turma já tem uma linha para este dia.",
        all_impossible_message=(
            "A turma fica com todos os blocos em Impossível. "
            "Se tiver aulas, a geração do horário fica bloqueada."
        ),
    )
    return tuple(
        ClassAvailabilityImport(
            entry.target.identity[0],
            entry.target.identity[1],
            entry.line,
            entry.scores,
            entry.changed_blocks,
        )
        for entry in merged
    )


def _validate_teacher_availability(
    parsed: ParsedResourceFile,
    snapshot: ImportSnapshot,
    batch_teachers: tuple[TeacherImport, ...],
    issues: list[BulkImportIssue],
) -> tuple[TeacherAvailabilityImport, ...]:
    existing = {_email(teacher.email): teacher for teacher in snapshot.teachers}
    batch_names = {_email(teacher.email): teacher.name for teacher in batch_teachers}

    def resolve(row: dict, issues: list[BulkImportIssue]) -> _AvailabilityTarget | None:
        email = _email(_value(row, "teacher_email"))
        line = int(row["line"])
        # Resolution order (D04, D07, D08): missing email, then inactive, then active.
        if not email or (email not in existing and email not in batch_names):
            issues.append(
                _issue(
                    TEACHER_AVAILABILITY,
                    "teacher_reference_missing",
                    "Não existe nenhum professor com este email.",
                    line=line,
                    field="teacher_email",
                )
            )
            return None
        if email in batch_names:
            # A teacher created in the same batch starts from an all-neutral grid (D08).
            return _AvailabilityTarget(None, email, (batch_names[email], email))
        teacher = existing[email]
        if not teacher.is_active:
            issues.append(
                _issue(
                    TEACHER_AVAILABILITY,
                    "teacher_inactive",
                    "Este professor está arquivado ou já não leciona. Retire a linha ou "
                    "reative-o na Equipa.",
                    line=line,
                    field="teacher_email",
                )
            )
            return None
        return _AvailabilityTarget(teacher.id, email, (teacher.name, email))

    merged = _validate_availability(
        TEACHER_AVAILABILITY,
        parsed,
        snapshot,
        snapshot.teacher_availability,
        resolve,
        issues,
        duplicate_code="duplicate_teacher_day",
        duplicate_message="Este professor já tem uma linha para este dia.",
        all_impossible_message=(
            "O professor fica com todos os blocos em Impossível. "
            "Se tiver aulas, a geração do horário fica bloqueada."
        ),
    )
    return tuple(
        TeacherAvailabilityImport(
            entry.target.identity[0],
            entry.target.identity[1],
            entry.line,
            entry.scores,
            entry.changed_blocks,
        )
        for entry in merged
    )


def _strict_hour(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def _teacher_presence_hours(
    row: dict, issues: list[BulkImportIssue]
) -> tuple[int | None, int | None]:
    """Return ``(minimum, max_gap)``; no minimum means no rule, gap defaults to 1."""
    line = int(row["line"])
    raw_minimum = _value(row, "minimum_hours")
    raw_gap = _value(row, "max_gap_hours")
    minimum = _strict_hour(raw_minimum) if raw_minimum else None
    if raw_minimum and (minimum is None or not 1 <= minimum <= 12):
        issues.append(
            _issue(
                TEACHER_PRESENCE,
                "minimum_hours_invalid",
                TEACHER_PRESENCE_MINIMUM_ERROR_MESSAGE,
                line=line,
                field="minimum_hours",
            )
        )
        minimum = None
    if raw_gap and not raw_minimum:
        issues.append(
            _issue(
                TEACHER_PRESENCE,
                "max_gap_hours_without_minimum",
                TEACHER_PRESENCE_GAP_WITHOUT_MINIMUM_MESSAGE,
                line=line,
                field="max_gap_hours",
            )
        )
        return None, None
    max_gap = _strict_hour(raw_gap) if raw_gap else None
    if raw_gap and (max_gap is None or not 0 <= max_gap <= 12):
        issues.append(
            _issue(
                TEACHER_PRESENCE,
                "max_gap_hours_invalid",
                TEACHER_PRESENCE_GAP_ERROR_MESSAGE,
                line=line,
                field="max_gap_hours",
            )
        )
        max_gap = None
    if raw_minimum and not raw_gap and minimum is not None:
        max_gap = 1
    return minimum, max_gap


def _validate_teacher_presence(
    parsed: ParsedResourceFile,
    known_teacher_emails: set[str],
    issues: list[BulkImportIssue],
) -> tuple[TeacherPresenceImport, ...]:
    result = []
    seen: set[str] = set()
    for row in parsed.rows:
        line = int(row["line"])
        before = len(issues)
        email = _email(_value(row, "email"))
        lunch = normalize_yes_no(_value(row, "lunch"))
        if lunch is None:
            issues.append(
                _issue(
                    TEACHER_PRESENCE,
                    "lunch_invalid",
                    TEACHER_PRESENCE_LUNCH_ERROR_MESSAGE,
                    line=line,
                    field="lunch",
                )
            )
        minimum, max_gap = _teacher_presence_hours(row, issues)
        if email in seen:
            issues.append(
                _issue(
                    TEACHER_PRESENCE,
                    "duplicate_in_batch",
                    TEACHER_PRESENCE_DUPLICATE_EMAIL_MESSAGE,
                    line=line,
                    field="email",
                )
            )
        elif email not in known_teacher_emails:
            issues.append(
                _issue(
                    TEACHER_PRESENCE,
                    "teacher_reference_missing",
                    TEACHER_PRESENCE_UNKNOWN_TEACHER_MESSAGE,
                    line=line,
                    field="email",
                )
            )
        seen.add(email)
        if len(issues) == before:
            result.append(TeacherPresenceImport(email, lunch, minimum, max_gap, line))
    return tuple(result)


def validate_import(
    files: dict[str, ParsedResourceFile], snapshot: ImportSnapshot
) -> ValidationResult:
    issues: list[BulkImportIssue] = [issue for parsed in files.values() for issue in parsed.issues]
    rooms = _validate_rooms(files["rooms"], snapshot, issues) if "rooms" in files else ()
    subjects = (
        _validate_subjects(files["subjects"], snapshot, issues) if "subjects" in files else ()
    )
    courses = _validate_courses(files["courses"], snapshot, issues) if "courses" in files else ()
    teachers = (
        _validate_teachers(files["teachers"], snapshot, issues) if "teachers" in files else ()
    )
    assignments = (
        _validate_assignments(files["assignments"], snapshot, issues)
        if "assignments" in files
        else ()
    )

    subject_names = {_key(item.name) for item in subjects} | {
        _key(item.name) for item in snapshot.subjects
    }
    course_abbreviations = {item.abbreviation.upper() for item in courses} | {
        item.abbreviation.upper() for item in snapshot.courses
    }
    class_names = {(item.course_abbreviation.upper(), _key(item.name)) for item in snapshot.classes}
    class_ids = {
        (item.course_abbreviation.upper(), _key(item.name)): item.id for item in snapshot.classes
    }
    class_names.update(
        (course.abbreviation.upper(), _key(cls.name))
        for course in courses
        for cls in course.classes
    )
    class_availability = (
        _validate_class_availability(
            files[CLASS_AVAILABILITY], snapshot, class_names, class_ids, issues
        )
        if CLASS_AVAILABILITY in files
        else ()
    )
    teacher_availability = (
        _validate_teacher_availability(files[TEACHER_AVAILABILITY], snapshot, teachers, issues)
        if TEACHER_AVAILABILITY in files
        else ()
    )
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
            issues.append(
                _issue(
                    "assignments",
                    "course_reference_missing",
                    "O curso referenciado não existe.",
                    line=assignment.line,
                    field="course_abbreviation",
                )
            )
        if (assignment.course_abbreviation.upper(), _key(assignment.class_name)) not in class_names:
            issues.append(
                _issue(
                    "assignments",
                    "class_reference_missing",
                    "A turma referenciada não existe nesse curso.",
                    line=assignment.line,
                    field="class_name",
                )
            )
        if _key(assignment.subject_name) not in subject_names:
            issues.append(
                _issue(
                    "assignments",
                    "subject_reference_missing",
                    "A disciplina referenciada não existe.",
                    line=assignment.line,
                    field="subject_name",
                )
            )
        if assignment.teacher_email:
            if assignment.teacher_email in existing_teacher_emails:
                issues.append(
                    _issue(
                        "assignments",
                        "teacher_existing_forbidden",
                        "Professores existentes não podem ser usados em atribuições importadas.",
                        line=assignment.line,
                        field="teacher_email",
                    )
                )
            elif assignment.teacher_email not in teacher_emails:
                issues.append(
                    _issue(
                        "assignments",
                        "teacher_not_in_batch",
                        "O professor deve ser criado no mesmo lote.",
                        line=assignment.line,
                        field="teacher_email",
                    )
                )
            else:
                inferred[assignment.teacher_email].add(assignment.subject_name)

    known_teacher_emails = teacher_emails | existing_teacher_emails
    teacher_presence = (
        _validate_teacher_presence(files[TEACHER_PRESENCE], known_teacher_emails, issues)
        if TEACHER_PRESENCE in files
        else ()
    )

    counts = {
        "rooms": len(rooms),
        "subjects": len(subjects),
        "modules": sum(len(item.modules) for item in subjects),
        "courses": len(courses),
        "classes": sum(len(item.classes) for item in courses),
        "teachers": len(teachers),
        "competencies": sum(len(values) for values in inferred.values()),
        "assignments": len(assignments),
        CLASS_AVAILABILITY: len(class_availability),
        TEACHER_AVAILABILITY: len(teacher_availability),
        TEACHER_PRESENCE: len(teacher_presence),
    }
    # Availability rows sit outside the generic 100-item cut (D15); the interface
    # tables show every class and teacher row they receive.
    generic_preview = (
        [{"resource": "rooms", "name": item.name, "line": item.line} for item in rooms]
        + [
            {
                "resource": "subjects",
                "name": item.name,
                "modules": len(item.modules),
                "line": item.line,
            }
            for item in subjects
        ]
        + [
            {
                "resource": "courses",
                "abbreviation": item.abbreviation,
                "classes": len(item.classes),
                "line": item.line,
            }
            for item in courses
        ]
        + [{"resource": "teachers", "email": item.email, "line": item.line} for item in teachers]
        + [
            {
                "resource": "assignments",
                "course_abbreviation": item.course_abbreviation,
                "class_name": item.class_name,
                "subject_name": item.subject_name,
                "line": item.line,
            }
            for item in assignments
        ]
    )
    availability_preview = [
        {
            "resource": CLASS_AVAILABILITY,
            "course_abbreviation": item.course_abbreviation,
            "class_name": item.class_name,
            "changed_blocks": item.changed_blocks,
            "line": item.line,
        }
        for item in sorted(
            class_availability,
            key=lambda item: (-item.changed_blocks, item.course_abbreviation, item.class_name),
        )
    ] + [
        {
            "resource": TEACHER_AVAILABILITY,
            "teacher_name": item.teacher_name,
            "teacher_email": item.teacher_email,
            "changed_blocks": item.changed_blocks,
            "line": item.line,
        }
        for item in sorted(
            teacher_availability,
            key=lambda item: (
                -item.changed_blocks,
                item.teacher_name.casefold(),
                item.teacher_email,
            ),
        )
    ]
    preview = tuple(generic_preview[:100] + availability_preview)
    return ValidationResult(
        tuple(issues),
        rooms,
        subjects,
        courses,
        teachers,
        assignments,
        class_availability,
        teacher_availability,
        counts,
        preview,
        {email: tuple(sorted(values, key=_key)) for email, values in inferred.items()},
        teacher_presence,
    )
