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


def test_templates_are_deterministic_utf8_bom_semicolon_and_coherent_example():
    rendered = {resource: render_template(resource) for resource in IMPORT_RESOURCES}

    assert all(value == render_template(resource) for resource, value in rendered.items())
    assert all(value.startswith(b"\xef\xbb\xbf") for value in rendered.values())
    assert all(b";" in value and b"\r\n" in value for value in rendered.values())
    assert all(value.count(b"\r\n") == 2 for value in rendered.values())


def test_parser_rejects_missing_bom_wrong_delimiter_and_example_rows():
    missing_bom = parse_resource_file(
        "rooms", "salas.csv", encoded("name;type;capacity\r\nSala;normal;20\r\n", bom=False)
    )
    wrong_delimiter = parse_resource_file(
        "rooms", "salas.csv", encoded("name,type,capacity\r\nSala,normal,20\r\n")
    )
    example = parse_resource_file("rooms", "salas.csv", base64.b64encode(render_template("rooms")).decode())

    assert {issue.code for issue in missing_bom.issues} == {"utf8_bom_required"}
    assert {issue.code for issue in wrong_delimiter.issues} == {"delimiter_invalid"}
    assert {issue.code for issue in example.issues} == {"template_example_present"}


def test_parser_accepts_header_order_and_preserves_physical_line_numbers():
    parsed = parse_resource_file(
        "rooms",
        "salas.csv",
        encoded("capacity;name;type\r\n\r\n20;Sala Nova;lab\r\n"),
    )

    assert not parsed.issues
    assert parsed.rows == ({"capacity": "20", "name": "Sala Nova", "type": "lab", "line": 3},)


def test_parser_rejects_rows_with_missing_columns():
    parsed = parse_resource_file(
        "rooms",
        "salas.csv",
        encoded("name;type;capacity\r\nSala Nova;lab\r\n"),
    )

    assert "column_count_invalid" in {issue.code for issue in parsed.issues}
    assert parsed.rows == ()


def test_policy_returns_all_cross_reference_issues_and_warnings():
    subjects = parse_resource_file(
        "subjects",
        "disciplinas.csv",
        encoded(
            "name;required_room_type;module_name;module_code;module_hours;module_order\r\n"
            "Programação;lab;Módulo 1;M1;50;1\r\n"
        ),
    )
    courses = parse_resource_file(
        "courses",
        "cursos.csv",
        encoded(
            "abbreviation;name;class_name;grade_level;start_year;end_year;size\r\n"
            "TGEI;Curso;10.º A;10;2025;2028;25\r\n"
        ),
    )
    teachers = parse_resource_file(
        "teachers",
        "professores.csv",
        encoded("name;email;competency_subject\r\nAna;ana@example.com;Programação\r\n"),
    )
    assignments = parse_resource_file(
        "assignments",
        "atribuicoes.csv",
        encoded(
            "course_abbreviation;class_name;subject_name;teacher_email\r\n"
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
    assert {"teacher_not_in_batch", "course_reference_missing", "subject_reference_missing"} <= codes
    assert "teacher_missing_warning" in codes
    assert result.can_commit is False


def test_policy_allows_existing_course_subject_class_references_but_not_existing_teacher():
    assignments = parse_resource_file(
        "assignments",
        "atribuicoes.csv",
        encoded(
            "course_abbreviation;class_name;subject_name;teacher_email\r\n"
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
        encoded("name;email;competency_subject\r\nAna;ana@example.com;Inexistente\r\n"),
    )

    result = validate_import({"teachers": teachers}, ImportSnapshot())

    assert result.can_commit is False
    assert "competency_subject_reference_missing" in {issue.code for issue in result.issues}
