"""Unit contracts for the database integrity audit helpers."""

from scripts import audit_database_integrity


class _FakeInspector:
    def __init__(self, indexes):
        self._indexes = indexes

    def get_pk_constraint(self, table, schema=None):
        return {"constrained_columns": ["id"]}

    def get_unique_constraints(self, table, schema=None):
        return [{"column_names": ["organization_id", "id"]}]

    def get_indexes(self, table, schema=None):
        return self._indexes


def _index(name, columns, *, unique=True, where=None):
    index = {"name": name, "column_names": columns, "unique": unique}
    if where is not None:
        index["dialect_options"] = {"postgresql_where": where}
    return index


def test_unique_column_sets_skip_expression_and_partial_indexes():
    inspector = _FakeInspector(
        [
            _index("uq_room_type_org_name", ["organization_id", None]),
            _index("uq_room_type_org_normal", ["organization_id"], where="is_normal IS TRUE"),
            _index("uq_course_active_org_abbreviation", ["organization_id", "abbreviation"]),
        ]
    )

    assert audit_database_integrity._unique_column_sets(inspector, "room_type") == {
        ("id",),
        ("organization_id", "id"),
        ("organization_id", "abbreviation"),
    }
