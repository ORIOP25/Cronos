import warnings

from sqlalchemy.exc import SAWarning

from app.db.database import Base


def test_metadata_sort_has_no_foreign_key_cycle_warning():
    with warnings.catch_warnings():
        warnings.simplefilter("error", SAWarning)
        assert list(Base.metadata.sorted_tables)


def test_cycle_breaking_foreign_keys_are_named_and_deferred():
    deferred = [
        constraint
        for table in Base.metadata.tables.values()
        for constraint in table.foreign_key_constraints
        if constraint.use_alter
    ]
    assert deferred
    assert all(constraint.name for constraint in deferred)
