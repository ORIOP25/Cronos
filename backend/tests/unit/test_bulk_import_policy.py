import base64
from datetime import time

from app.services.bulk_import_policy import (
    CLASS_AVAILABILITY,
    IMPORT_RESOURCES,
    TEACHER_AVAILABILITY,
    TEMPLATE_DEFINITIONS,
    ExistingClass,
    ExistingCourse,
    ExistingRoom,
    ExistingSubject,
    ExistingTeacher,
    ExistingTimeslot,
    ImportSnapshot,
    parse_resource_file,
    render_availability_template,
    render_template,
    template_filename,
    validate_import,
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
    assert result.counts["class_availability"] == 1
    assert [
        item["non_neutral_blocks"]
        for item in result.preview
        if item["resource"] == CLASS_AVAILABILITY
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
            "Sigla do curso;Nome do curso;Nome da turma;Ano escolar;Ano de início;Ano de fim;Número de alunos\r\n"
            "TGEI;Curso;TGEI 25/28;10;2025;2028;25\r\n"
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
