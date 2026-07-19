import warnings

from sqlalchemy.exc import SAWarning

from app import models
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
    lesson_scope = next(
        constraint
        for constraint in models.LessonOccurrence.__table__.foreign_key_constraints
        if constraint.name == "fk_lesson_occurrence_active_block_scope"
    )
    assert lesson_scope.use_alter is True
