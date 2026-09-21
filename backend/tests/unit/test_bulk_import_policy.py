import base64

from app.services.bulk_import_policy import (
    IMPORT_RESOURCES,
    ExistingClass,
    ExistingCourse,
    ExistingRoom,
    ExistingSubject,
    ExistingTeacher,
    ImportSnapshot,
    parse_resource_file,
    render_template,
    validate_import,
)


def encoded(text: str, *, bom: bool = True) -> str:
    value = ("\ufeff" if bom else "") + text
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def test_templates_use_the_official_names_and_are_deterministic():
    rendered = {resource: render_template(resource) for resource in IMPORT_RESOURCES}
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
        "Ano de fim;Número de alunos"
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


def test_room_types_are_normalized_for_rooms_and_subjects():
    rooms = parse_resource_file(
        "rooms",
        "salas.csv",
        encoded(
            "Nome da sala;Tipo de sala;Capacidade\r\n"
            "Sala 1;LABORATORIO;20\r\n"
            "Sala 2;GINÁSIO;20\r\n"
            "Sala 3;artes;20\r\n"
        ),
    )
    subjects = parse_resource_file(
        "subjects",
        "disciplinas.csv",
        encoded(
            "Nome da disciplina;Tipo de sala;Nome do módulo;Código do módulo;Horas do módulo;Ordem do módulo\r\n"
            "Disciplina;laboratorio;Módulo;M1;30;1\r\n"
        ),
    )

    result = validate_import(
        {"rooms": rooms, "subjects": subjects},
        ImportSnapshot(),
    )

    assert result.can_commit is True
    assert [item.room_type for item in result.rooms] == ["lab", "gym", "art"]
    assert result.subjects[0].room_type == "lab"


def test_room_types_reject_internal_codes_and_unknown_values():
    parsed = parse_resource_file(
        "rooms",
        "salas.csv",
        encoded(
            "Nome da sala;Tipo de sala;Capacidade\r\nSala 1;lab;20\r\nSala 2;Biblioteca;20\r\n"
        ),
    )

    result = validate_import({"rooms": parsed}, ImportSnapshot())

    assert result.can_commit is False
    assert {issue.code for issue in result.issues} >= {"room_type_invalid"}
    assert all(
        "Escreva Normal, Laboratório, Ginásio ou Artes." in issue.message
        for issue in result.issues
        if issue.code == "room_type_invalid"
    )


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
            "Sigla do curso;Nome do curso;Nome da turma;Ano escolar;Ano de início;Ano de fim;Número de alunos\r\n"
            "TGEI;Curso;10.º A;10;2025;2028;25\r\n"
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
            rooms=[ExistingRoom(id=1, name="Sala Existente")],
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
