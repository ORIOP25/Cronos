import base64
from datetime import time

import pytest

from app.services.bulk_import_policy import (
    CLASS_AVAILABILITY,
    IMPORT_RESOURCES,
    TEACHER_AVAILABILITY,
    TEACHER_PRESENCE,
    TEACHER_PRESENCE_FILENAME,
    TEACHER_PRESENCE_HEADERS,
    TEMPLATE_DEFINITIONS,
    ExistingClass,
    ExistingCourse,
    ExistingRoom,
    ExistingRoomType,
    ExistingSubject,
    ExistingTeacher,
    ExistingTimeslot,
    ImportSnapshot,
    parse_resource_file,
    render_availability_template,
    render_teacher_presence_template,
    render_template,
    template_filename,
    validate_import,
)

# Os quatro tipos iniciais de uma escola, na ordem do S1.
INITIAL_ROOM_TYPES = (
    ExistingRoomType(id=1, name="Normal"),
    ExistingRoomType(id=2, name="Laboratório"),
    ExistingRoomType(id=3, name="Ginásio"),
    ExistingRoomType(id=4, name="Artes"),
)


def encoded(text: str, *, bom: bool = True) -> str:
    value = ("\ufeff" if bom else "") + text
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def test_templates_use_the_official_names_and_are_deterministic():
    rendered = {resource: render_template(resource) for resource in TEMPLATE_DEFINITIONS}
    text = {resource: value.decode("utf-8-sig") for resource, value in rendered.items()}

    assert all(value == render_template(resource) for resource, value in rendered.items())
    assert all(value.startswith(b"\xef\xbb\xbf") for value in rendered.values())
    assert text["rooms"].splitlines()[0] == "Nome da sala;Tipo de sala;Capacidade"
    assert text["subjects"].splitlines()[0] == (
        "Nome da disciplina;Tipo de sala;Nome do módulo;Código do módulo;"
        "Horas do módulo;Ordem do módulo"
    )
    assert text["courses"].splitlines()[0] == (
        "Sigla do curso;Nome do curso;Nome da turma;Ano escolar;Ano de início;"
        "Ano de fim;Número de alunos;Sala da turma"
    )
    assert text["teachers"].splitlines()[0] == (
        "Nome do professor;Email do professor;Nome da disciplina"
    )
    assert text["assignments"].splitlines()[0] == (
        "Sigla do curso;Nome da turma;Nome da disciplina;Email do professor"
    )
    assert all(value.count(b"\r\n") == 2 for value in rendered.values())


def test_parser_accepts_both_delimiters_with_or_without_bom():
    for delimiter in (";", ","):
        for bom in (True, False):
            parsed = parse_resource_file(
                "rooms",
                "salas.csv",
                encoded(
                    f"Nome da sala{delimiter}Tipo de sala{delimiter}Capacidade\r\n"
                    f"Sala Nova{delimiter}Laboratório{delimiter}20\r\n",
                    bom=bom,
                ),
            )

            assert parsed.issues == ()
            assert parsed.rows == (
                {"name": "Sala Nova", "type": "Laboratório", "capacity": "20", "line": 2},
            )


def test_parser_reads_quoted_values_that_contain_either_delimiter():
    parsed = parse_resource_file(
        "rooms",
        "salas.csv",
        encoded('Nome da sala,Tipo de sala,Capacidade\r\n"Sala, Norte; bloco A",Normal,20\r\n'),
    )

    assert parsed.issues == ()
    assert parsed.rows[0]["name"] == "Sala, Norte; bloco A"


def test_parser_rejects_old_reordered_missing_and_extra_headers():
    cases = (
        "name;type;capacity\r\nSala;Normal;20\r\n",
        "Capacidade;Nome da sala;Tipo de sala\r\n20;Sala;Normal\r\n",
        "Nome da sala;Tipo de sala\r\nSala;Normal\r\n",
        "Nome da sala;Tipo de sala;Capacidade;Outra\r\nSala;Normal;20;X\r\n",
    )

    for content in cases:
        parsed = parse_resource_file("rooms", "salas.csv", encoded(content))
        assert "header_invalid" in {issue.code for issue in parsed.issues}


def test_parser_rejects_the_official_example_line():
    parsed = parse_resource_file(
        "rooms", "Cronos_Salas_Template.csv", base64.b64encode(render_template("rooms")).decode()
    )

    assert {issue.code for issue in parsed.issues} == {"template_example_present"}


def test_parser_reports_common_read_error_for_invalid_encoding_or_structure():
    invalid = parse_resource_file("rooms", "salas.csv", base64.b64encode(b"\xff\xfe").decode())
    malformed = parse_resource_file(
        "rooms", "salas.csv", encoded("Nome da sala|Tipo de sala|Capacidade\r\nSala|Normal|20\r\n")
    )

    assert invalid.issues[0].message == malformed.issues[0].message
    assert "Não foi possível ler este ficheiro" in invalid.issues[0].message


def test_parser_explains_when_file_belongs_to_another_import_section():
    parsed = parse_resource_file(
        "subjects",
        "professores.csv",
        encoded(
            "Nome do professor,Email do professor,Nome da disciplina\r\n"
            "Ana,ana@example.com,Programação\r\n",
            bom=False,
        ),
    )

    assert parsed.issues[0].code == "resource_mismatch"
    assert parsed.issues[0].message == (
        "Este ficheiro não corresponde à secção escolhida. Selecione o modelo correspondente."
    )


ROOMS_HEADER = "Nome da sala;Tipo de sala;Capacidade\r\n"
SUBJECTS_HEADER = "Nome da disciplina;Tipo de sala;Nome do módulo;Código do módulo;Horas do módulo;Ordem do módulo\r\n"
COURSES_HEADER = (
    "Sigla do curso;Nome do curso;Nome da turma;Ano escolar;Ano de início;Ano de fim;"
    "Número de alunos;Sala da turma\r\n"
)


def test_room_types_match_the_school_name_for_rooms_and_subjects_without_case_or_accents():
    rooms = parse_resource_file(
        "rooms",
        "salas.csv",
        encoded(ROOMS_HEADER + "Sala 1;LABORATORIO;20\r\nSala 2;GINÁSIO;20\r\nSala 3;artes;20\r\n"),
    )
    subjects = parse_resource_file(
        "subjects",
        "disciplinas.csv",
        encoded(SUBJECTS_HEADER + "Disciplina;laboratorio;Módulo;M1;30;1\r\n"),
    )

    result = validate_import(
        {"rooms": rooms, "subjects": subjects},
        ImportSnapshot(room_types=list(INITIAL_ROOM_TYPES)),
    )

    assert result.can_commit is True
    assert [(item.name, item.is_new) for item in result.room_types] == [
        ("LABORATORIO", False),
        ("GINÁSIO", False),
        ("artes", False),
    ]
    assert result.counts["room_types"] == 0


def test_an_unknown_room_type_name_is_one_new_type_across_rooms_and_subjects():
    rooms = parse_resource_file(
        "rooms", "salas.csv", encoded(ROOMS_HEADER + "Sala 1;oficina;20\r\n")
    )
    subjects = parse_resource_file(
        "subjects",
        "disciplinas.csv",
        encoded(SUBJECTS_HEADER + "Oficina;Oficina;Módulo;M1;30;1\r\n"),
    )

    result = validate_import(
        {"rooms": rooms, "subjects": subjects},
        ImportSnapshot(room_types=list(INITIAL_ROOM_TYPES)),
    )

    assert result.can_commit is True
    assert [(item.name, item.is_new) for item in result.room_types] == [("oficina", True)]
    assert result.counts["room_types"] == 1
    assert {"resource": "room_types", "name": "oficina"} in result.preview
    assert {item.room_type_name for item in result.rooms} == {"oficina"}
    assert {item.room_type_name for item in result.subjects} == {"Oficina"}


def test_room_type_names_must_be_present_and_at_most_sixty_characters():
    rooms = parse_resource_file(
        "rooms",
        "salas.csv",
        encoded(ROOMS_HEADER + f"Sala 1;;20\r\nSala 2;{'x' * 61};20\r\n"),
    )

    result = validate_import({"rooms": rooms}, ImportSnapshot(room_types=list(INITIAL_ROOM_TYPES)))

    assert result.can_commit is False
    assert [(issue.code, issue.line, issue.field, issue.message) for issue in result.issues] == [
        ("room_type_invalid", 2, "type", "Escreva o tipo de sala."),
        (
            "room_type_invalid",
            3,
            "type",
            "Escreva um nome de tipo com até 60 caracteres.",
        ),
    ]


def test_home_room_of_a_new_class_may_be_a_room_of_the_same_batch():
    rooms = parse_resource_file(
        "rooms", "salas.csv", encoded(ROOMS_HEADER + "Sala Nova;Normal;30\r\n")
    )
    courses = parse_resource_file(
        "courses",
        "cursos.csv",
        encoded(COURSES_HEADER + "TGEI;Curso;TGEI 25/28;10;2025;2028;25;sala nova\r\n"),
    )

    result = validate_import(
        {"rooms": rooms, "courses": courses}, ImportSnapshot(room_types=list(INITIAL_ROOM_TYPES))
    )

    assert result.can_commit is True
    assert result.courses[0].classes[0].home_room == "sala nova"


def test_home_room_of_a_new_class_may_be_an_existing_school_room_that_seats_it():
    courses = parse_resource_file(
        "courses",
        "cursos.csv",
        encoded(COURSES_HEADER + "TGEI;Curso;TGEI 25/28;10;2025;2028;25;SALA EXISTENTE\r\n"),
    )
    snapshot = ImportSnapshot(rooms=[ExistingRoom(id=7, name="Sala Existente", capacity=25)])

    result = validate_import({"courses": courses}, snapshot)

    assert result.can_commit is True
    assert result.courses[0].classes[0].home_room == "SALA EXISTENTE"


def test_empty_home_room_keeps_the_class_automatic():
    courses = parse_resource_file(
        "courses",
        "cursos.csv",
        encoded(COURSES_HEADER + "TGEI;Curso;TGEI 25/28;10;2025;2028;25;\r\n"),
    )

    result = validate_import({"courses": courses}, ImportSnapshot())

    assert result.can_commit is True
    assert result.courses[0].classes[0].home_room is None


def test_unknown_home_room_is_an_error_with_row_and_column():
    courses = parse_resource_file(
        "courses",
        "cursos.csv",
        encoded(COURSES_HEADER + "TGEI;Curso;TGEI 25/28;10;2025;2028;25;Sala Fantasma\r\n"),
    )

    result = validate_import({"courses": courses}, ImportSnapshot())

    assert result.can_commit is False
    assert [(issue.code, issue.line, issue.field, issue.message) for issue in result.issues] == [
        (
            "home_room_not_found",
            2,
            "home_room",
            "Sala não encontrada. Escreva o nome de uma sala existente ou do ficheiro de salas.",
        )
    ]


def test_home_room_must_seat_every_student_of_the_class():
    rooms = parse_resource_file(
        "rooms", "salas.csv", encoded(ROOMS_HEADER + "Sala Pequena;Normal;24\r\n")
    )
    courses = parse_resource_file(
        "courses",
        "cursos.csv",
        encoded(COURSES_HEADER + "TGEI;Curso;TGEI 25/28;10;2025;2028;25;Sala Pequena\r\n"),
    )

    result = validate_import(
        {"rooms": rooms, "courses": courses}, ImportSnapshot(room_types=list(INITIAL_ROOM_TYPES))
    )

    assert result.can_commit is False
    assert [(issue.code, issue.line, issue.field, issue.message) for issue in result.issues] == [
        (
            "home_room_capacity",
            2,
            "home_room",
            "A Sala Pequena não tem lugares para os 25 alunos da turma.",
        )
    ]


@pytest.mark.parametrize(
    ("room_name", "expected_subject"),
    [
        ("L-03", "A sala L-03"),
        ("Sala Pequena", "A Sala Pequena"),
        ("Sála 3", "A Sála 3"),
        ("Salão 2", "A sala Salão 2"),
    ],
)
def test_capacity_message_names_the_room_like_the_screen(room_name, expected_subject):
    rooms = parse_resource_file(
        "rooms", "salas.csv", encoded(ROOMS_HEADER + f"{room_name};Normal;24\r\n")
    )
    courses = parse_resource_file(
        "courses",
        "cursos.csv",
        encoded(COURSES_HEADER + f"TGEI;Curso;TGEI 25/28;10;2025;2028;25;{room_name}\r\n"),
    )

    result = validate_import(
        {"rooms": rooms, "courses": courses}, ImportSnapshot(room_types=list(INITIAL_ROOM_TYPES))
    )

    assert [issue.message for issue in result.issues] == [
        f"{expected_subject} não tem lugares para os 25 alunos da turma."
    ]


def test_old_seven_column_courses_header_is_refused():
    """Regressão: o cabeçalho antigo, sem a coluna Sala da turma, não é aceite."""
    old_header = (
        "Sigla do curso;Nome do curso;Nome da turma;Ano escolar;Ano de início;"
        "Ano de fim;Número de alunos\r\n"
    )

    parsed = parse_resource_file(
        "courses",
        "cursos_antigo.csv",
        encoded(old_header + "TGEI;Curso;TGEI 25/28;10;2025;2028;25\r\n"),
    )

    assert not parsed.rows
    assert [issue.code for issue in parsed.issues] == ["header_invalid"]


def test_home_room_without_class_fields_is_reported_instead_of_ignored():
    courses = parse_resource_file(
        "courses",
        "cursos.csv",
        encoded(COURSES_HEADER + "TGEI;Curso;;;;;;Sala Nova\r\n"),
    )

    result = validate_import({"courses": courses}, ImportSnapshot())

    assert result.can_commit is False
    assert [
        (issue.code, issue.line, issue.field)
        for issue in result.issues
        if issue.severity == "error"
    ] == [("class_partial", 2, "home_room")]


def test_policy_returns_all_cross_reference_issues_and_warnings():
    subjects = parse_resource_file(
        "subjects",
        "disciplinas.csv",
        encoded(
            "Nome da disciplina;Tipo de sala;Nome do módulo;Código do módulo;Horas do módulo;Ordem do módulo\r\n"
            "Programação;Laboratório;Módulo 1;M1;50;1\r\n"
        ),
    )
    courses = parse_resource_file(
        "courses",
        "cursos.csv",
        encoded(
            "Sigla do curso;Nome do curso;Nome da turma;Ano escolar;Ano de início;Ano de fim;Número de alunos;Sala da turma\r\n"
            "TGEI;Curso;10.º A;10;2025;2028;25;\r\n"
        ),
    )
    teachers = parse_resource_file(
        "teachers",
        "professores.csv",
        encoded(
            "Nome do professor;Email do professor;Nome da disciplina\r\n"
            "Ana;ana@example.com;Programação\r\n"
        ),
    )
    assignments = parse_resource_file(
        "assignments",
        "atribuicoes.csv",
        encoded(
            "Sigla do curso;Nome da turma;Nome da disciplina;Email do professor\r\n"
            "TGEI;10.º A;Programação;missing@example.com\r\n"
            "INEX;Turma;Inexistente;\r\n"
        ),
    )

    result = validate_import(
        {
            "subjects": subjects,
            "courses": courses,
            "teachers": teachers,
            "assignments": assignments,
        },
        ImportSnapshot(
            rooms=[ExistingRoom(id=1, name="Sala Existente", capacity=30)],
            subjects=[],
            courses=[],
            classes=[],
            teachers=[ExistingTeacher(id=2, email="old@example.com", name="Professor")],
        ),
    )

    codes = {issue.code for issue in result.issues}
    assert {
        "teacher_not_in_batch",
        "course_reference_missing",
        "subject_reference_missing",
    } <= codes
    assert "teacher_missing_warning" in codes
    assert result.can_commit is False


def test_policy_allows_existing_course_subject_class_references_but_not_existing_teacher():
    assignments = parse_resource_file(
        "assignments",
        "atribuicoes.csv",
        encoded(
            "Sigla do curso;Nome da turma;Nome da disciplina;Email do professor\r\n"
            "TGEI;10.º A;Programação;new@example.com\r\n"
        ),
    )
    result = validate_import(
        {"assignments": assignments},
        ImportSnapshot(
            courses=[ExistingCourse(id=1, abbreviation="TGEI", name="Curso")],
            classes=[ExistingClass(id=2, course_id=1, course_abbreviation="TGEI", name="10.º A")],
            subjects=[ExistingSubject(id=3, name="Programação")],
        ),
    )

    assert result.can_commit is False
    assert {issue.code for issue in result.issues} >= {"teacher_not_in_batch"}


def test_policy_rejects_teacher_competencies_without_a_subject_reference():
    teachers = parse_resource_file(
        "teachers",
        "professores.csv",
        encoded(
            "Nome do professor;Email do professor;Nome da disciplina\r\n"
            "Ana;ana@example.com;Inexistente\r\n"
        ),
    )

    result = validate_import({"teachers": teachers}, ImportSnapshot())

    assert result.can_commit is False
    assert "competency_subject_reference_missing" in {issue.code for issue in result.issues}


def _class_availability_snapshot(**kwargs) -> ImportSnapshot:
    return ImportSnapshot(
        classes=[ExistingClass(id=1, course_id=1, course_abbreviation="TGEI", name="TGEI 25/28")],
        timeslots=[
            ExistingTimeslot(id=10, day_of_week=0, start_time=time(8, 30)),
            ExistingTimeslot(id=11, day_of_week=0, start_time=time(9, 20)),
            ExistingTimeslot(id=12, day_of_week=4, start_time=time(8, 30)),
        ],
        **kwargs,
    )


def test_import_resources_include_both_availability_sections_and_filenames():
    assert CLASS_AVAILABILITY in IMPORT_RESOURCES
    assert TEACHER_AVAILABILITY in IMPORT_RESOURCES
    assert template_filename(CLASS_AVAILABILITY) == "Cronos_DisponibilidadeTurmas_Template.csv"
    assert (
        template_filename(TEACHER_AVAILABILITY) == "Cronos_DisponibilidadeProfessores_Template.csv"
    )


def test_class_availability_template_lists_sorted_hours_and_saved_levels():
    timeslots = (
        ExistingTimeslot(id=10, day_of_week=0, start_time=time(8, 30)),
        ExistingTimeslot(id=11, day_of_week=0, start_time=time(9, 20)),
        ExistingTimeslot(id=12, day_of_week=4, start_time=time(8, 30)),
    )
    classes = (ExistingClass(id=1, course_id=1, course_abbreviation="TGEI", name="TGEI 25/28"),)
    rendered = render_availability_template(
        CLASS_AVAILABILITY, timeslots, classes, {1: {10: -1, 12: 0}}
    )

    assert rendered.startswith(b"\xef\xbb\xbf")
    lines = rendered.decode("utf-8-sig").splitlines()
    assert lines[0] == "Sigla do curso;Nome da turma;Dia;08:30;09:20"
    assert lines[1] == "TGEI;TGEI 25/28;Segunda;Impossível;Neutro"
    assert lines[2] == "TGEI;TGEI 25/28;Sexta;Evitar;"
    assert rendered.count(b"\r\n") == 3


def test_class_availability_template_without_classes_is_header_only():
    timeslots = (
        ExistingTimeslot(id=10, day_of_week=0, start_time=time(8, 30)),
        ExistingTimeslot(id=11, day_of_week=4, start_time=time(9, 20)),
    )

    rendered = render_availability_template(CLASS_AVAILABILITY, timeslots, (), {})

    assert rendered.decode("utf-8-sig") == "Sigla do curso;Nome da turma;Dia;08:30;09:20\r\n"


def test_teacher_availability_template_orders_active_teachers_by_name_email_and_day():
    timeslots = (
        ExistingTimeslot(id=10, day_of_week=0, start_time=time(8, 30)),
        ExistingTimeslot(id=11, day_of_week=0, start_time=time(9, 20)),
        ExistingTimeslot(id=12, day_of_week=4, start_time=time(8, 30)),
    )
    teachers = (
        ExistingTeacher(id=2, email="bea@escola.pt", name="Bea Costa"),
        ExistingTeacher(id=1, email="ana.silva@escola.pt", name="ana silva"),
    )
    rendered = render_availability_template(
        TEACHER_AVAILABILITY, timeslots, teachers, {1: {10: -1, 11: 0, 12: 2}}
    )

    assert rendered.startswith(b"\xef\xbb\xbf")
    lines = rendered.decode("utf-8-sig").splitlines()
    assert lines[0] == "Nome do professor;Email do professor;Dia;08:30;09:20"
    assert lines[1] == "ana silva;ana.silva@escola.pt;Segunda;Impossível;Evitar"
    assert lines[2] == "ana silva;ana.silva@escola.pt;Sexta;Preferencial;"
    assert lines[3] == "Bea Costa;bea@escola.pt;Segunda;Neutro;Neutro"
    assert lines[4] == "Bea Costa;bea@escola.pt;Sexta;Neutro;"


def test_teacher_availability_template_without_teachers_is_header_only():
    timeslots = (
        ExistingTimeslot(id=10, day_of_week=0, start_time=time(8, 30)),
        ExistingTimeslot(id=11, day_of_week=4, start_time=time(9, 20)),
    )

    rendered = render_availability_template(TEACHER_AVAILABILITY, timeslots, (), {})

    assert (
        rendered.decode("utf-8-sig") == "Nome do professor;Email do professor;Dia;08:30;09:20\r\n"
    )


def test_teacher_availability_parser_reads_dynamic_hour_headers():
    parsed = parse_resource_file(
        TEACHER_AVAILABILITY,
        "disponibilidade_professores.csv",
        encoded(
            "Nome do professor;Email do professor;Dia;8:30;09:20:00\r\n"
            "Ana Silva;Ana.Silva@Escola.PT;segunda-feira;Impossivel;Evitar\r\n"
        ),
    )

    assert parsed.issues == ()
    assert parsed.hours == ("08:30", "09:20")
    assert parsed.hour_titles == ("8:30", "09:20:00")
    assert parsed.rows[0]["teacher_name"] == "Ana Silva"
    assert parsed.rows[0]["teacher_email"] == "Ana.Silva@Escola.PT"
    assert parsed.rows[0]["8:30"] == "Impossivel"


def test_availability_grid_parser_rejects_the_other_grid_and_fixed_files():
    teacher_grid = (
        "Nome do professor;Email do professor;Dia;08:30\r\nAna;ana@escola.pt;Segunda;Neutro\r\n"
    )
    class_grid = "Sigla do curso;Nome da turma;Dia;08:30\r\nTGEI;TGEI 25/28;Segunda;Neutro\r\n"
    teachers_fixed = (
        "Nome do professor;Email do professor;Nome da disciplina\r\n"
        "Ana;ana@escola.pt;Programação\r\n"
    )
    cases = (
        (CLASS_AVAILABILITY, "professores.csv", teacher_grid),
        (TEACHER_AVAILABILITY, "turmas.csv", class_grid),
        (CLASS_AVAILABILITY, "professores.csv", teachers_fixed),
        (TEACHER_AVAILABILITY, "professores.csv", teachers_fixed),
        ("teachers", "professores.csv", teacher_grid),
        ("teachers", "turmas.csv", class_grid),
        ("assignments", "turmas.csv", class_grid),
    )

    for resource, filename, content in cases:
        parsed = parse_resource_file(resource, filename, encoded(content))
        assert parsed.issues, (resource, filename)
        assert parsed.issues[0].code == "resource_mismatch"
        assert parsed.issues[0].message == (
            "Este ficheiro não corresponde à secção escolhida. Selecione o modelo correspondente."
        )


def test_class_availability_parser_reads_dynamic_hour_headers():
    parsed = parse_resource_file(
        CLASS_AVAILABILITY,
        "disponibilidade.csv",
        encoded(
            "Sigla do curso;Nome da turma;Dia;8:30;09:20:00\r\n"
            "TGEI;TGEI 25/28;segunda-feira;Impossivel;Evitar\r\n"
        ),
    )

    assert parsed.issues == ()
    assert parsed.hours == ("08:30", "09:20")
    assert parsed.hour_titles == ("8:30", "09:20:00")
    assert parsed.rows[0]["course_abbreviation"] == "TGEI"
    assert parsed.rows[0]["8:30"] == "Impossivel"


def test_class_availability_parser_rejects_invalid_or_duplicate_hour_columns():
    invalid = parse_resource_file(
        CLASS_AVAILABILITY,
        "disponibilidade.csv",
        encoded("Sigla do curso;Nome da turma;Dia;8h30\r\nTGEI;TGEI 25/28;Segunda;Neutro\r\n"),
    )
    duplicate = parse_resource_file(
        CLASS_AVAILABILITY,
        "disponibilidade.csv",
        encoded(
            "Sigla do curso;Nome da turma;Dia;08:30;8:30\r\n"
            "TGEI;TGEI 25/28;Segunda;Neutro;Evitar\r\n"
        ),
    )

    assert "header_invalid" in {issue.code for issue in invalid.issues}
    assert "header_invalid" in {issue.code for issue in duplicate.issues}


def test_class_availability_validation_merges_every_day_into_one_row_per_class():
    parsed = parse_resource_file(
        CLASS_AVAILABILITY,
        "disponibilidade.csv",
        encoded(
            "Sigla do curso;Nome da turma;Dia;08:30;09:20\r\n"
            "TGEI;TGEI 25/28;SEGUNDA;impossível;Evitar\r\n"
            "TGEI;TGEI 25/28;sexta-feira;Preferencial;\r\n"
        ),
    )

    result = validate_import({"class_availability": parsed}, _class_availability_snapshot())

    assert result.can_commit is True
    assert len(result.class_availability) == 1
    assert result.class_availability[0].scores == {10: -1, 11: 0, 12: 2}
    assert result.class_availability[0].changed_blocks == 3
    assert result.counts["class_availability"] == 1
    assert [
        item["changed_blocks"] for item in result.preview if item["resource"] == CLASS_AVAILABILITY
    ] == [3]


def test_class_availability_validation_reports_each_row_problem_without_block_noise():
    parsed = parse_resource_file(
        CLASS_AVAILABILITY,
        "disponibilidade.csv",
        encoded(
            "Sigla do curso;Nome da turma;Dia;08:30;09:20\r\n"
            "TGEI;TGEI 25/28;Segunda;Neutro;Neutro\r\n"
            "TGEI;TGEI 25/28;Segunda;;\r\n"
            "TGEI;TGEI 25/28;Feriado;Neutro;Neutro\r\n"
            "TGEI;TGEI 25/28;Terça;Neutro;Neutro\r\n"
            "TGEI;Inexistente;Segunda;;\r\n"
            "TGEI;TGEI 25/28;Sexta;Neutro;Neutro\r\n"
            "TGEI;TGEI 25/28;Segunda;Talvez;\r\n"
        ),
    )

    result = validate_import({"class_availability": parsed}, _class_availability_snapshot())

    issues = {(issue.code, issue.field): issue.message for issue in result.issues}
    codes = [issue.code for issue in result.issues]
    assert result.can_commit is False
    assert issues[("duplicate_class_day", None)] == "Esta turma já tem uma linha para este dia."
    assert issues[("day_invalid", "day")] == (
        "Escreva um dia com blocos na grelha, por exemplo Segunda."
    )
    assert codes.count("day_invalid") == 2
    assert ("class_reference_missing", "class_name") in issues
    assert issues[("hour_without_block", "09:20")] == (
        "Este dia não tem bloco às 09:20. Deixe a célula vazia."
    )
    assert codes.count("hour_without_block") == 1
    assert issues[("level_invalid", "08:30")] == (
        "Escreva Impossível, Evitar, Neutro ou Preferencial."
    )


def test_class_availability_validation_requires_the_current_grid_header():
    missing = parse_resource_file(
        CLASS_AVAILABILITY,
        "disponibilidade.csv",
        encoded("Sigla do curso;Nome da turma;Dia;08:30\r\nTGEI;TGEI 25/28;Segunda;Neutro\r\n"),
    )
    unknown = parse_resource_file(
        CLASS_AVAILABILITY,
        "disponibilidade.csv",
        encoded(
            "Sigla do curso;Nome da turma;Dia;08:30;09:20;10:10\r\n"
            "TGEI;TGEI 25/28;Segunda;Neutro;Neutro;Neutro\r\n"
        ),
    )

    missing_result = validate_import(
        {"class_availability": missing}, _class_availability_snapshot()
    )
    unknown_result = validate_import(
        {"class_availability": unknown}, _class_availability_snapshot()
    )

    assert ("missing_hour", None) in {(issue.code, issue.field) for issue in missing_result.issues}
    assert any(
        issue.code == "missing_hour"
        and issue.message == "Falta a coluna 09:20. Descarregue um modelo novo."
        for issue in missing_result.issues
    )
    assert any(
        issue.code == "unknown_hour"
        and issue.field == "10:10"
        and issue.message
        == "A grelha não tem blocos que comecem às 10:10. Descarregue um modelo novo."
        for issue in unknown_result.issues
    )


def test_class_availability_accepts_a_class_created_in_the_same_batch():
    courses = parse_resource_file(
        "courses",
        "cursos.csv",
        encoded(
            "Sigla do curso;Nome do curso;Nome da turma;Ano escolar;Ano de início;Ano de fim;Número de alunos;Sala da turma\r\n"
            "TGEI;Curso;TGEI 25/28;10;2025;2028;25;\r\n"
        ),
    )
    availability = parse_resource_file(
        CLASS_AVAILABILITY,
        "disponibilidade.csv",
        encoded(
            "Sigla do curso;Nome da turma;Dia;08:30;09:20\r\n"
            "TGEI;TGEI 25/28;Segunda;Impossível;\r\n"
        ),
    )

    result = validate_import(
        {"courses": courses, "class_availability": availability},
        ImportSnapshot(
            timeslots=[
                ExistingTimeslot(id=10, day_of_week=0, start_time=time(8, 30)),
                ExistingTimeslot(id=11, day_of_week=0, start_time=time(9, 20)),
            ]
        ),
    )

    assert result.can_commit is True
    assert result.class_availability[0].scores == {10: -1}


def _teacher(email: str = "ana@escola.pt", name: str = "Ana", *, active: bool = True):
    return ExistingTeacher(id=1, email=email, name=name, is_active=active)


def test_teacher_email_matches_case_insensitively_on_both_sides():
    timeslots = [ExistingTimeslot(id=10, day_of_week=0, start_time=time(8, 30))]
    file_with_upper = parse_resource_file(
        TEACHER_AVAILABILITY,
        "disponibilidade.csv",
        encoded(
            "Nome do professor;Email do professor;Dia;08:30\r\n"
            "Ana;Ana@Escola.PT;Segunda;Impossível\r\n"
        ),
    )
    file_with_lower = parse_resource_file(
        TEACHER_AVAILABILITY,
        "disponibilidade.csv",
        encoded(
            "Nome do professor;Email do professor;Dia;08:30\r\n"
            "Ana;ana@escola.pt;Segunda;Impossível\r\n"
        ),
    )

    lower_stored = validate_import(
        {TEACHER_AVAILABILITY: file_with_upper},
        ImportSnapshot(
            teachers=[ExistingTeacher(id=1, email="ana@escola.pt", name="Ana", is_active=True)],
            timeslots=timeslots,
        ),
    )
    upper_stored = validate_import(
        {TEACHER_AVAILABILITY: file_with_lower},
        ImportSnapshot(
            teachers=[ExistingTeacher(id=2, email="ANA@ESCOLA.PT", name="Ana", is_active=True)],
            timeslots=timeslots,
        ),
    )

    assert lower_stored.can_commit is True
    assert upper_stored.can_commit is True
    assert lower_stored.teacher_availability[0].teacher_email == "ana@escola.pt"
    assert upper_stored.teacher_availability[0].teacher_email == "ana@escola.pt"


def test_teacher_availability_merges_every_day_into_one_grid():
    timeslots = [
        ExistingTimeslot(id=10 + day, day_of_week=day, start_time=time(8, 30)) for day in range(5)
    ]
    parsed = parse_resource_file(
        TEACHER_AVAILABILITY,
        "disponibilidade.csv",
        encoded(
            "Nome do professor;Email do professor;Dia;08:30\r\n"
            "Ana;ana@escola.pt;Segunda;Impossível\r\n"
            "Ana;ana@escola.pt;Terça;Evitar\r\n"
            "Ana;ana@escola.pt;Quarta;Preferencial\r\n"
            "Ana;ana@escola.pt;Quinta;Neutro\r\n"
            "Ana;ana@escola.pt;Sexta;Evitar\r\n"
        ),
    )

    result = validate_import(
        {TEACHER_AVAILABILITY: parsed},
        ImportSnapshot(teachers=[_teacher()], timeslots=timeslots),
    )

    assert result.can_commit is True
    assert len(result.teacher_availability) == 1
    assert result.teacher_availability[0].scores == {10: -1, 11: 0, 12: 2, 14: 0}
    assert result.teacher_availability[0].changed_blocks == 4
    assert result.counts[TEACHER_AVAILABILITY] == 1


def test_teacher_availability_resolution_rejects_missing_and_inactive():
    parsed = parse_resource_file(
        TEACHER_AVAILABILITY,
        "disponibilidade.csv",
        encoded(
            "Nome do professor;Email do professor;Dia;08:30\r\n"
            "Sem email;;Segunda;Neutro\r\n"
            "Arquivado;arch@escola.pt;Segunda;Neutro\r\n"
            "Inexistente;missing@escola.pt;Segunda;Neutro\r\n"
        ),
    )

    result = validate_import(
        {TEACHER_AVAILABILITY: parsed},
        ImportSnapshot(
            teachers=[ExistingTeacher(id=1, email="arch@escola.pt", name="Arquivado")],
            timeslots=[ExistingTimeslot(id=10, day_of_week=0, start_time=time(8, 30))],
        ),
    )

    messages = {(issue.code, issue.field): issue.message for issue in result.issues}
    assert result.can_commit is False
    assert messages[("teacher_reference_missing", "teacher_email")] == (
        "Não existe nenhum professor com este email."
    )
    assert messages[("teacher_inactive", "teacher_email")] == (
        "Este professor está arquivado ou já não leciona. Retire a linha ou reative-o na Equipa."
    )
    assert sum(1 for issue in result.issues if issue.code == "teacher_reference_missing") == 2
    assert result.teacher_availability == ()


def test_teacher_changed_blocks_compare_all_visible_slots_including_missing_days():
    parsed = parse_resource_file(
        TEACHER_AVAILABILITY,
        "disponibilidade.csv",
        encoded(
            "Nome do professor;Email do professor;Dia;08:30;09:20\r\n"
            "Ana;ana@escola.pt;Segunda;Impossível;\r\n"
        ),
    )

    result = validate_import(
        {TEACHER_AVAILABILITY: parsed},
        ImportSnapshot(
            teachers=[_teacher()],
            timeslots=[
                ExistingTimeslot(id=10, day_of_week=0, start_time=time(8, 30)),
                ExistingTimeslot(id=11, day_of_week=0, start_time=time(9, 20)),
                ExistingTimeslot(id=12, day_of_week=4, start_time=time(8, 30)),
            ],
            teacher_availability={1: {10: -1, 11: 0, 12: 2}},
        ),
    )

    assert result.can_commit is True
    item = result.teacher_availability[0]
    assert item.scores == {10: -1}
    assert item.changed_blocks == 2


def test_availability_levels_accept_only_the_four_names():
    accepted = parse_resource_file(
        TEACHER_AVAILABILITY,
        "disponibilidade.csv",
        encoded(
            "Nome do professor;Email do professor;Dia;08:30\r\n"
            "Ana;ana@escola.pt;Segunda;impossível\r\n"
            "Bea;bea@escola.pt;Segunda;NEUTRO\r\n"
        ),
    )
    rejected = parse_resource_file(
        TEACHER_AVAILABILITY,
        "disponibilidade.csv",
        encoded(
            "Nome do professor;Email do professor;Dia;08:30\r\n"
            "Ana;ana@escola.pt;Segunda;Proibido\r\n"
            "Bea;bea@escola.pt;Segunda;Prefere\r\n"
        ),
    )
    snapshot = ImportSnapshot(
        teachers=[
            ExistingTeacher(id=1, email="ana@escola.pt", name="Ana", is_active=True),
            ExistingTeacher(id=2, email="bea@escola.pt", name="Bea", is_active=True),
        ],
        timeslots=[ExistingTimeslot(id=10, day_of_week=0, start_time=time(8, 30))],
    )

    accepted_result = validate_import({TEACHER_AVAILABILITY: accepted}, snapshot)
    rejected_result = validate_import({TEACHER_AVAILABILITY: rejected}, snapshot)

    assert accepted_result.can_commit is True
    assert rejected_result.can_commit is False
    level_issues = [issue for issue in rejected_result.issues if issue.code == "level_invalid"]
    assert len(level_issues) == 2
    assert all(
        issue.message == "Escreva Impossível, Evitar, Neutro ou Preferencial."
        for issue in level_issues
    )


def test_teacher_grid_ignores_the_name_column():
    parsed = parse_resource_file(
        TEACHER_AVAILABILITY,
        "disponibilidade.csv",
        encoded(
            "Nome do professor;Email do professor;Dia;08:30\r\n"
            ";ana@escola.pt;Segunda;Impossível\r\n"
        ),
    )

    result = validate_import(
        {TEACHER_AVAILABILITY: parsed},
        ImportSnapshot(
            teachers=[
                ExistingTeacher(id=1, email="ana@escola.pt", name="Ana Guardada", is_active=True)
            ],
            timeslots=[ExistingTimeslot(id=10, day_of_week=0, start_time=time(8, 30))],
        ),
    )

    assert result.can_commit is True
    assert result.teacher_availability[0].teacher_name == "Ana Guardada"


def test_teacher_availability_accepts_a_teacher_created_in_the_same_batch():
    teachers_file = parse_resource_file(
        "teachers",
        "professores.csv",
        encoded(
            "Nome do professor;Email do professor;Nome da disciplina\r\n"
            "Nova Professora;nova@escola.pt;Programação\r\n"
        ),
    )
    availability = parse_resource_file(
        TEACHER_AVAILABILITY,
        "disponibilidade.csv",
        encoded(
            "Nome do professor;Email do professor;Dia;08:30\r\n"
            "Nome do ficheiro;nova@escola.pt;Segunda;Impossível\r\n"
        ),
    )

    result = validate_import(
        {"teachers": teachers_file, TEACHER_AVAILABILITY: availability},
        ImportSnapshot(
            subjects=[ExistingSubject(id=5, name="Programação")],
            timeslots=[ExistingTimeslot(id=10, day_of_week=0, start_time=time(8, 30))],
        ),
    )

    assert result.can_commit is True
    item = result.teacher_availability[0]
    assert item.teacher_email == "nova@escola.pt"
    assert item.teacher_name == "Nova Professora"
    assert item.changed_blocks == 1


def test_teacher_availability_rejects_duplicate_day_lines():
    parsed = parse_resource_file(
        TEACHER_AVAILABILITY,
        "disponibilidade.csv",
        encoded(
            "Nome do professor;Email do professor;Dia;08:30\r\n"
            "Ana;ana@escola.pt;Segunda;Neutro\r\n"
            "Outro nome;ANA@escola.pt;segunda-feira;Evitar\r\n"
        ),
    )

    result = validate_import(
        {TEACHER_AVAILABILITY: parsed},
        ImportSnapshot(
            teachers=[_teacher()],
            timeslots=[ExistingTimeslot(id=10, day_of_week=0, start_time=time(8, 30))],
        ),
    )

    assert result.can_commit is False
    issue = next(issue for issue in result.issues if issue.code == "duplicate_teacher_day")
    assert issue.message == "Este professor já tem uma linha para este dia."
    assert issue.field is None


def test_availability_preview_sorts_by_changed_blocks_then_teacher_identity():
    parsed = parse_resource_file(
        TEACHER_AVAILABILITY,
        "disponibilidade.csv",
        encoded(
            "Nome do professor;Email do professor;Dia;08:30;09:20\r\n"
            "zeta;zeta@escola.pt;Segunda;Impossível;Evitar\r\n"
            "ana;ana@escola.pt;Segunda;Impossível;\r\n"
            "Bea;bea@escola.pt;Segunda;Impossível;\r\n"
        ),
    )

    result = validate_import(
        {TEACHER_AVAILABILITY: parsed},
        ImportSnapshot(
            teachers=[
                ExistingTeacher(id=1, email="zeta@escola.pt", name="zeta", is_active=True),
                ExistingTeacher(id=2, email="ana@escola.pt", name="ana", is_active=True),
                ExistingTeacher(id=3, email="bea@escola.pt", name="Bea", is_active=True),
            ],
            timeslots=[
                ExistingTimeslot(id=10, day_of_week=0, start_time=time(8, 30)),
                ExistingTimeslot(id=11, day_of_week=0, start_time=time(9, 20)),
            ],
        ),
    )

    items = [item for item in result.preview if item["resource"] == TEACHER_AVAILABILITY]
    assert [item["teacher_email"] for item in items] == [
        "zeta@escola.pt",
        "ana@escola.pt",
        "bea@escola.pt",
    ]


def test_class_availability_preview_sorts_by_changed_blocks_then_course_and_class():
    parsed = parse_resource_file(
        CLASS_AVAILABILITY,
        "disponibilidade.csv",
        encoded(
            "Sigla do curso;Nome da turma;Dia;08:30;09:20\r\n"
            "TGEI;B;Segunda;Impossível;\r\n"
            "TGEI;A;Segunda;Impossível;\r\n"
        ),
    )

    result = validate_import(
        {CLASS_AVAILABILITY: parsed},
        ImportSnapshot(
            classes=[
                ExistingClass(id=1, course_id=1, course_abbreviation="TGEI", name="B"),
                ExistingClass(id=2, course_id=1, course_abbreviation="TGEI", name="A"),
            ],
            timeslots=[
                ExistingTimeslot(id=10, day_of_week=0, start_time=time(8, 30)),
                ExistingTimeslot(id=11, day_of_week=0, start_time=time(9, 20)),
            ],
        ),
    )

    items = [item for item in result.preview if item["resource"] == CLASS_AVAILABILITY]
    assert [item["class_name"] for item in items] == ["A", "B"]


def test_all_impossible_availability_is_a_warning_for_teachers_and_classes():
    timeslots = [
        ExistingTimeslot(id=10, day_of_week=0, start_time=time(8, 30)),
        ExistingTimeslot(id=12, day_of_week=4, start_time=time(8, 30)),
    ]
    teacher_file = parse_resource_file(
        TEACHER_AVAILABILITY,
        "disponibilidade.csv",
        encoded(
            "Nome do professor;Email do professor;Dia;08:30\r\n"
            "Ana;ana@escola.pt;Segunda;Impossível\r\n"
            "Ana;ana@escola.pt;Sexta;Impossível\r\n"
        ),
    )
    class_file = parse_resource_file(
        CLASS_AVAILABILITY,
        "disponibilidade.csv",
        encoded(
            "Sigla do curso;Nome da turma;Dia;08:30\r\n"
            "TGEI;TGEI 25/28;Segunda;Impossível\r\n"
            "TGEI;TGEI 25/28;Sexta;Impossível\r\n"
        ),
    )

    teacher_result = validate_import(
        {TEACHER_AVAILABILITY: teacher_file},
        ImportSnapshot(teachers=[_teacher()], timeslots=timeslots),
    )
    class_result = validate_import(
        {CLASS_AVAILABILITY: class_file},
        ImportSnapshot(
            classes=[
                ExistingClass(id=1, course_id=1, course_abbreviation="TGEI", name="TGEI 25/28")
            ],
            timeslots=timeslots,
        ),
    )

    assert teacher_result.can_commit is True
    assert class_result.can_commit is True
    teacher_message = (
        "O professor fica com todos os blocos em Impossível. "
        "Se tiver aulas, a geração do horário fica bloqueada."
    )
    class_message = (
        "A turma fica com todos os blocos em Impossível. "
        "Se tiver aulas, a geração do horário fica bloqueada."
    )
    assert any(
        issue.code == "all_blocks_impossible"
        and issue.severity == "warning"
        and issue.message == teacher_message
        for issue in teacher_result.issues
    )
    assert any(
        issue.code == "all_blocks_impossible"
        and issue.severity == "warning"
        and issue.message == class_message
        for issue in class_result.issues
    )


def test_availability_preview_keeps_every_row_beyond_the_generic_cap():
    room_rows = "".join(f"Sala {index};Normal;20\r\n" for index in range(1, 121))
    rooms_file = parse_resource_file(
        "rooms",
        "salas.csv",
        encoded("Nome da sala;Tipo de sala;Capacidade\r\n" + room_rows),
    )
    teacher_rows = "".join(
        f"Professor {index};teacher{index}@escola.pt;Segunda;Neutro\r\n" for index in range(1, 121)
    )
    teachers_file = parse_resource_file(
        TEACHER_AVAILABILITY,
        "disponibilidade.csv",
        encoded("Nome do professor;Email do professor;Dia;08:30\r\n" + teacher_rows),
    )

    result = validate_import(
        {"rooms": rooms_file, TEACHER_AVAILABILITY: teachers_file},
        ImportSnapshot(
            room_types=list(INITIAL_ROOM_TYPES),
            teachers=[
                ExistingTeacher(
                    id=index,
                    email=f"teacher{index}@escola.pt",
                    name=f"Professor {index}",
                    is_active=True,
                )
                for index in range(1, 121)
            ],
            timeslots=[ExistingTimeslot(id=10, day_of_week=0, start_time=time(8, 30))],
        ),
    )

    assert result.can_commit is True
    assert len(result.teacher_availability) == 120
    room_items = [item for item in result.preview if item["resource"] == "rooms"]
    teacher_items = [item for item in result.preview if item["resource"] == TEACHER_AVAILABILITY]
    assert len(room_items) == 100
    assert len(teacher_items) == 120


def test_changed_blocks_is_zero_when_the_stored_grid_already_matches():
    timeslots = [
        ExistingTimeslot(id=10, day_of_week=0, start_time=time(8, 30)),
        ExistingTimeslot(id=11, day_of_week=0, start_time=time(9, 20)),
    ]
    teacher_file = parse_resource_file(
        TEACHER_AVAILABILITY,
        "disponibilidade.csv",
        encoded(
            "Nome do professor;Email do professor;Dia;08:30;09:20\r\n"
            "Ana;ana@escola.pt;Segunda;Impossível;Evitar\r\n"
        ),
    )
    class_file = parse_resource_file(
        CLASS_AVAILABILITY,
        "disponibilidade.csv",
        encoded(
            "Sigla do curso;Nome da turma;Dia;08:30;09:20\r\n"
            "TGEI;TGEI 25/28;Segunda;Impossível;Evitar\r\n"
        ),
    )

    teacher_result = validate_import(
        {TEACHER_AVAILABILITY: teacher_file},
        ImportSnapshot(
            teachers=[_teacher()],
            timeslots=timeslots,
            teacher_availability={1: {10: -1, 11: 0}},
        ),
    )
    class_result = validate_import(
        {CLASS_AVAILABILITY: class_file},
        ImportSnapshot(
            classes=[
                ExistingClass(id=1, course_id=1, course_abbreviation="TGEI", name="TGEI 25/28")
            ],
            timeslots=timeslots,
            class_availability={1: {10: -1, 11: 0}},
        ),
    )

    assert teacher_result.can_commit is True
    assert class_result.can_commit is True
    assert teacher_result.teacher_availability[0].changed_blocks == 0
    assert class_result.class_availability[0].changed_blocks == 0


TEACHER_PRESENCE_ROW = (
    "Nome do professor;Email do professor;Hora de almoço;"
    "Mínimo de horas por presença;Furo máximo (horas)\r\n"
)


def _teacher_presence_snapshot(**kwargs) -> ImportSnapshot:
    return ImportSnapshot(
        teachers=[
            ExistingTeacher(id=1, email="ana@example.com", name="Ana"),
            ExistingTeacher(id=2, email="bruno@example.com", name="Bruno"),
            ExistingTeacher(id=3, email="carla@example.com", name="Carla"),
        ],
        **kwargs,
    )


def test_teacher_presence_resource_uses_the_official_filename_and_headers():
    assert TEACHER_PRESENCE in IMPORT_RESOURCES
    assert TEACHER_PRESENCE_FILENAME == "Cronos_PresencaProfessores_Template.csv"
    assert TEACHER_PRESENCE_HEADERS == (
        "Nome do professor",
        "Email do professor",
        "Hora de almoço",
        "Mínimo de horas por presença",
        "Furo máximo (horas)",
    )


def test_teacher_presence_template_lists_active_teachers_sorted_by_name_with_current_values():
    teachers = (
        ExistingTeacher(
            id=2,
            email="bruno@example.invalid",
            name="Bruno",
            lunch_required=False,
            minimum_hours=3,
            max_gap_hours=2,
        ),
        ExistingTeacher(id=1, email="ana@example.invalid", name="Ana"),
    )

    rendered = render_teacher_presence_template(teachers)

    assert rendered.startswith(b"\xef\xbb\xbf")
    lines = rendered.decode("utf-8-sig").splitlines()
    assert lines[0] == ";".join(TEACHER_PRESENCE_HEADERS)
    assert lines[1] == "Ana;ana@example.invalid;Sim;;"
    assert lines[2] == "Bruno;bruno@example.invalid;Não;3;2"


def test_teacher_presence_template_without_teachers_is_header_only():
    rendered = render_teacher_presence_template(())

    assert rendered.decode("utf-8-sig") == ";".join(TEACHER_PRESENCE_HEADERS) + "\r\n"


def test_teacher_presence_parser_reads_the_five_columns_and_rejects_other_headers():
    parsed = parse_resource_file(
        TEACHER_PRESENCE,
        "presenca.csv",
        encoded(TEACHER_PRESENCE_ROW + "Ana;ana@example.com;NÃO;;\r\n"),
    )
    mismatch = parse_resource_file(
        TEACHER_PRESENCE,
        "salas.csv",
        encoded("Nome da sala;Tipo de sala;Capacidade\r\nSala;Normal;20\r\n"),
    )

    assert parsed.issues == ()
    assert parsed.rows[0]["email"] == "ana@example.com"
    assert mismatch.issues[0].code == "resource_mismatch"


def test_teacher_presence_validation_applies_lunch_and_hour_rules():
    parsed = parse_resource_file(
        TEACHER_PRESENCE,
        "presenca.csv",
        encoded(
            TEACHER_PRESENCE_ROW
            + "Ana;ana@example.com;Não;;\r\n"
            + "Bruno;bruno@example.com;;4;\r\n"
            + "Carla;carla@example.com;sim;2;0\r\n"
        ),
    )

    result = validate_import({TEACHER_PRESENCE: parsed}, _teacher_presence_snapshot())

    assert result.can_commit is True
    assert [
        (item.email, item.lunch_required, item.minimum_hours, item.max_gap_hours)
        for item in result.teacher_presence
    ] == [
        ("ana@example.com", False, None, None),
        ("bruno@example.com", True, 4, 1),
        ("carla@example.com", True, 2, 0),
    ]
    assert result.counts[TEACHER_PRESENCE] == 3


def test_teacher_presence_validation_rejects_invalid_values_with_exact_messages():
    parsed = parse_resource_file(
        TEACHER_PRESENCE,
        "presenca.csv",
        encoded(
            TEACHER_PRESENCE_ROW
            + "Ana;ana@example.com;Talvez;;\r\n"
            + "Bruno;bruno@example.com;Sim;0;\r\n"
            + "Carla;carla@example.com;Sim;13;\r\n"
            + "Ana;ana2@example.com;Sim;3.5;\r\n"
        ),
    )

    result = validate_import({TEACHER_PRESENCE: parsed}, _teacher_presence_snapshot())

    assert result.can_commit is False
    issues = {(issue.code, issue.field): issue for issue in result.issues}
    assert issues[("lunch_invalid", "lunch")].message == "Escreva Sim ou Não."
    assert issues[("minimum_hours_invalid", "minimum_hours")].message == (
        "Escreva um número inteiro de horas entre 1 e 12."
    )
    assert [issue.code for issue in result.issues].count("minimum_hours_invalid") == 3
    assert result.teacher_presence == ()


def test_teacher_presence_validation_rejects_gap_without_minimum_and_out_of_range_gap():
    parsed = parse_resource_file(
        TEACHER_PRESENCE,
        "presenca.csv",
        encoded(
            TEACHER_PRESENCE_ROW
            + "Ana;ana@example.com;Sim;;2\r\n"
            + "Bruno;bruno@example.com;Sim;3;13\r\n"
        ),
    )

    result = validate_import({TEACHER_PRESENCE: parsed}, _teacher_presence_snapshot())

    assert result.can_commit is False
    issues = {(issue.code, issue.field): issue for issue in result.issues}
    assert issues[("max_gap_hours_without_minimum", "max_gap_hours")].message == (
        "O furo máximo só se aplica com um mínimo de horas."
    )
    assert issues[("max_gap_hours_invalid", "max_gap_hours")].message == (
        "Escreva um número inteiro de horas entre 0 e 12."
    )


def test_teacher_presence_validation_reports_duplicate_and_unknown_emails_with_line_and_column():
    parsed = parse_resource_file(
        TEACHER_PRESENCE,
        "presenca.csv",
        encoded(
            TEACHER_PRESENCE_ROW
            + "Ana;ana@example.com;Sim;;\r\n"
            + "Ana;ana@example.com;Não;;\r\n"
            + "Zé;missing@example.com;Sim;;\r\n"
        ),
    )

    result = validate_import({TEACHER_PRESENCE: parsed}, _teacher_presence_snapshot())

    assert result.can_commit is False
    issues = {(issue.code, issue.line, issue.field): issue for issue in result.issues}
    assert issues[("duplicate_in_batch", 3, "email")].message == (
        "Este email aparece em mais de uma linha."
    )
    assert issues[("teacher_reference_missing", 4, "email")].message == (
        "Professor não encontrado."
    )


def test_teacher_presence_validation_accepts_a_teacher_created_in_the_same_batch():
    teachers = parse_resource_file(
        "teachers",
        "professores.csv",
        encoded(
            "Nome do professor;Email do professor;Nome da disciplina\r\nNova;nova@example.com;\r\n"
        ),
    )
    presence = parse_resource_file(
        TEACHER_PRESENCE,
        "presenca.csv",
        encoded(TEACHER_PRESENCE_ROW + "Nova;nova@example.com;Sim;3;1\r\n"),
    )

    result = validate_import(
        {"teachers": teachers, TEACHER_PRESENCE: presence},
        ImportSnapshot(),
    )

    assert result.can_commit is True
    assert len(result.teacher_presence) == 1
    assert result.teacher_presence[0].minimum_hours == 3


def test_teacher_presence_r10_only_the_named_teachers_are_changed():
    parsed = parse_resource_file(
        TEACHER_PRESENCE,
        "presenca.csv",
        encoded(
            TEACHER_PRESENCE_ROW
            + "Ana;ana@example.com;Sim;3;1\r\n"
            + "Bruno;bruno@example.com;Não;;\r\n"
        ),
    )

    result = validate_import({TEACHER_PRESENCE: parsed}, _teacher_presence_snapshot())

    assert result.can_commit is True
    assert {item.email for item in result.teacher_presence} == {
        "ana@example.com",
        "bruno@example.com",
    }
    assert result.counts[TEACHER_PRESENCE] == 2
