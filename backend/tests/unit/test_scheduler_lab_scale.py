import pytest

from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.lab.scale import build_scale_fixture


@pytest.mark.parametrize("class_count", [10, 30, 45, 60])
def test_scale_fixture_witness_is_valid_without_enumeration(class_count):
    fixture = build_scale_fixture(class_count)

    report = validate_candidate(fixture.snapshot, fixture.witness)

    assert report.valid
    assert report.total_credit_minutes == class_count * 240
    assert len(fixture.snapshot.assignments) == class_count


def test_scale_fixture_uses_shared_teachers_without_conflicts():
    fixture = build_scale_fixture(30)
    teacher_count = len({row.teacher_id for row in fixture.snapshot.assignments})

    assert teacher_count < 30
    assert validate_candidate(fixture.snapshot, fixture.witness).valid


def test_scale_fixture_supports_a_partial_final_lesson():
    fixture = build_scale_fixture(10, module_minutes=100)

    report = validate_candidate(fixture.snapshot, fixture.witness)

    assert report.valid
    assert report.total_credit_minutes == 1000


def test_scale_fixture_rejects_demand_that_does_not_fit():
    with pytest.raises(ValueError):
        build_scale_fixture(10, module_minutes=300)
