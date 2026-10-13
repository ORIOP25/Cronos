from app import models


def test_scheduler_school_year_is_tenant_scoped_and_date_bounded():
    table = models.SchedulerSchoolYear.__table__

    assert {"organization_id", "label", "start_date", "hard_end_date", "timezone"} <= set(
        table.columns.keys()
    )
    assert any(
        constraint.name == "uq_scheduler_school_year_org_label" for constraint in table.constraints
    )
    assert any(
        constraint.name == "uq_scheduler_school_year_id_org" for constraint in table.constraints
    )
    assert any(
        constraint.name == "ck_scheduler_school_year_date_order" for constraint in table.constraints
    )
    assert "uq_scheduler_school_year_active_org" in {index.name for index in table.indexes}


def test_scheduler_school_year_state_has_one_row_per_tenant_year():
    table = models.SchedulerSchoolYearState.__table__

    assert {
        "organization_id",
        "school_year_id",
        "school_year_publication_state",
        "active_schedule_version_id",
        "scheduler_state_version",
        "approved_scheduler_state_version",
        "lock_version",
    } <= set(table.columns.keys())
    assert any(
        constraint.name == "uq_scheduler_school_year_state_org_year"
        for constraint in table.constraints
    )
    assert any(
        constraint.name == "ck_scheduler_school_year_state_published_has_version"
        for constraint in table.constraints
    )
    assert any(
        constraint.name == "fk_scheduler_school_year_state_year_scope"
        for constraint in table.foreign_key_constraints
    )


def test_scheduler_school_year_state_defaults_to_unpublished():
    state = models.SchedulerSchoolYearState(
        organization_id=1,
        school_year_id=1,
    )

    assert state.school_year_publication_state is None
    assert table_default(models.SchedulerSchoolYearState, "school_year_publication_state") == (
        models.SchoolYearPublicationState.UNPUBLISHED
    )


def table_default(model, column_name):
    default = model.__table__.columns[column_name].default
    assert default is not None
    return default.arg


def test_lesson_occurrence_exposes_revisioned_debt_identity():
    constraint_names = {
        constraint.name for constraint in models.LessonOccurrence.__table__.constraints
    }

    assert "uq_lesson_occurrence_id_org_revision" in constraint_names


def test_scheduler_state_version_events_explain_increment_decisions():
    table = models.SchedulerStateVersionEvent.__table__
    constraint_names = {constraint.name for constraint in table.constraints}
    index_names = {index.name for index in table.indexes}

    assert {
        "organization_id",
        "school_year_id",
        "version_before",
        "version_after",
        "entity_type",
        "entity_id",
        "operation",
        "change_scope",
        "changed_by_membership_id",
        "changed_at",
        "before_metadata_json",
        "after_metadata_json",
        "metadata_json",
    } <= set(table.columns.keys())
    assert {
        "ck_scheduler_state_version_events_versions_nonnegative",
        "ck_scheduler_state_version_events_increment",
        "ck_scheduler_state_version_events_entity_type_nonempty",
    } <= constraint_names
    assert "uq_scheduler_state_version_events_increment" in index_names
    assert {item.value for item in models.SchedulerStateChangeScope} == {
        "FUTURE_IMPACTING",
        "PAST_ONLY",
        "NO_OP",
        "INACTIVE_RESOURCE",
    }
