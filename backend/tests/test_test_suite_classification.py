import pytest
from conftest import classify_test_suite


def test_plain_test_is_unit():
    assert classify_test_suite([], []) == "unit"


def test_database_fixture_is_integration():
    assert classify_test_suite(["db_session"], []) == "integration"


def test_http_fixture_is_integration():
    assert classify_test_suite(["async_client"], []) == "integration"


def test_postgresql_marker_is_integration():
    assert classify_test_suite([], ["postgresql"]) == "integration"


def test_redis_marker_has_no_suite_marker():
    assert classify_test_suite([], ["redis"]) is None


def test_unit_marker_with_database_fixture_fails_classification():
    with pytest.raises(ValueError, match="db_session"):
        classify_test_suite(["db_session"], ["unit"])


def test_unit_marker_with_redis_marker_fails_classification():
    with pytest.raises(ValueError, match="redis"):
        classify_test_suite([], ["unit", "redis"])


def test_unit_marker_with_postgresql_marker_fails_classification():
    with pytest.raises(ValueError, match="postgresql"):
        classify_test_suite([], ["unit", "postgresql"])


def test_solver_marker_does_not_change_suite():
    assert classify_test_suite([], ["solver"]) == "unit"


def test_slow_marker_does_not_change_suite():
    assert classify_test_suite([], ["slow"]) == "unit"
