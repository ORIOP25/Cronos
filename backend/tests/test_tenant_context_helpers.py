import pytest

from app.db.tenant import TENANT_OWNED_TABLES, _validate_organization_id


def test_tenant_registry_includes_hardened_tables():
    expected = {
        "availability",
        "course_subject_link",
        "teacher_subject_link",
        "class_subject_link",
        "module",
        "class_progress",
    }

    assert expected.issubset(set(TENANT_OWNED_TABLES))


@pytest.mark.parametrize("organization_id", [1, 2147483647])
def test_validate_organization_id_accepts_positive_ints(organization_id):
    assert _validate_organization_id(organization_id) == organization_id


@pytest.mark.parametrize("organization_id", [None, 0, -1, 2147483648, "1"])
def test_validate_organization_id_rejects_missing_or_invalid_values(organization_id):
    with pytest.raises(ValueError):
        _validate_organization_id(organization_id)
