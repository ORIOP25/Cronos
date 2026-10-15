import pytest
from pydantic import ValidationError

from app.schemas import BulkImportFilePayload, BulkImportFiles, ClassConfigCreate


def test_class_config_accepts_explicit_name_for_imports_and_keeps_it_optional():
    named = ClassConfigCreate(
        name="10.º A",
        grade_level=10,
        size=25,
        start_year=2025,
        end_year=2028,
    )
    generated = ClassConfigCreate(grade_level=10, start_year=2025, end_year=2028)

    assert named.name == "10.º A"
    assert generated.name is None


def test_bulk_import_files_accept_teacher_availability_on_its_own():
    payload = BulkImportFilePayload(
        filename="Cronos_DisponibilidadeProfessores_Template.csv",
        content_base64="YWJj",
    )

    files = BulkImportFiles(teacher_availability=payload)

    assert files.teacher_availability is payload


def test_bulk_import_files_require_at_least_one_file():
    with pytest.raises(ValidationError):
        BulkImportFiles()
