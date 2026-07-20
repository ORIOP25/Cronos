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
        "pending_draft_id",
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


def test_schedule_generation_job_tracks_lifecycle_and_snapshots():
    table = models.ScheduleGenerationJob.__table__

    assert {
        "organization_id",
        "school_year_id",
        "requested_by_membership_id",
        "strategy",
        "trigger_type",
        "job_status",
        "result_category",
        "generation_input_fingerprint",
        "debt_basis_fingerprint",
        "scheduler_state_version_used",
        "repair_policy_snapshot_hash",
        "input_snapshot_json",
        "queued_at",
        "started_at",
        "finished_at",
        "deadline_at",
        "duration_ms",
        "cancellation_requested_at",
        "failure_code",
        "failure_message",
        "idempotency_key",
    } <= set(table.columns.keys())
    assert any(
        constraint.name == "uq_schedule_generation_job_idempotency"
        for constraint in table.constraints
    )
    assert any(
        constraint.name == "uq_schedule_generation_job_id_scope" for constraint in table.constraints
    )
    assert any(
        constraint.name == "fk_schedule_generation_job_year_scope"
        for constraint in table.foreign_key_constraints
    )
    assert any(
        constraint.name == "ck_schedule_generation_job_duration_nonnegative"
        for constraint in table.constraints
    )
    assert {
        "ck_schedule_generation_job_result_consistency",
        "ck_schedule_generation_job_terminal_finished",
        "ck_schedule_generation_job_started_after_queued",
        "ck_schedule_generation_job_finished_after_started",
    } <= {constraint.name for constraint in table.constraints}
    assert "uq_schedule_generation_job_active_year" in {index.name for index in table.indexes}


def test_schedule_draft_stores_decision_inputs_and_output_summary():
    table = models.ScheduleDraft.__table__

    assert {
        "organization_id",
        "school_year_id",
        "generation_job_id",
        "strategy",
        "draft_state",
        "result_category",
        "trigger_type",
        "generation_input_fingerprint",
        "scheduler_state_version_used",
        "debt_basis_fingerprint",
        "repair_policy_snapshot_json",
        "repair_policy_snapshot_hash",
        "editable_start_date",
        "recovery_escalation_level",
        "adaptation_level",
        "projected_completion_date",
        "hard_end_date",
        "summary_json",
        "partial_recovery_blocker_type",
        "main_blocker_message",
        "recommended_actions_json",
        "warnings_json",
        "metrics_json",
        "stale_reason",
        "invalidated_reason",
        "created_by_membership_id",
        "created_at",
        "decided_by_membership_id",
        "decided_at",
    } <= set(table.columns.keys())


def test_schedule_draft_enforces_auditable_valid_output_invariants():
    table = models.ScheduleDraft.__table__
    constraint_names = {constraint.name for constraint in table.constraints}
    index_names = {index.name for index in table.indexes}

    assert "uq_schedule_drafts_generation_job" in constraint_names
    assert "uq_schedule_drafts_id_scope" in constraint_names
    assert "uq_schedule_drafts_id_job_scope" in constraint_names
    assert "ck_schedule_drafts_has_valid_output" in constraint_names
    assert "ck_schedule_drafts_completion_by_hard_end" in constraint_names
    assert {
        "ck_schedule_drafts_adaptive_editable_start",
        "ck_schedule_drafts_decision_consistency",
        "ck_schedule_drafts_stale_reason",
        "ck_schedule_drafts_invalidated_reason",
    } <= constraint_names
    assert "uq_schedule_drafts_pending_year" in index_names
    assert table_default(models.ScheduleDraft, "draft_state") == models.ScheduleDraftState.PENDING
    assert not table.columns.created_by_membership_id.nullable
    job_scope = next(
        constraint
        for constraint in table.foreign_key_constraints
        if constraint.name == "fk_schedule_drafts_generation_job_scope"
    )
    assert tuple(column.name for column in job_scope.columns) == (
        "generation_job_id",
        "organization_id",
        "school_year_id",
    )


def test_pending_draft_pointer_is_tenant_and_school_year_scoped():
    table = models.SchedulerSchoolYearState.__table__
    foreign_keys = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in table.foreign_key_constraints
    }

    assert foreign_keys["fk_scheduler_school_year_state_pending_draft_scope"] == (
        "pending_draft_id",
        "organization_id",
        "school_year_id",
    )


def test_schedule_draft_blocks_are_complete_target_state_rows():
    table = models.ScheduleDraftBlock.__table__

    assert {
        "organization_id",
        "school_year_id",
        "draft_id",
        "source_active_block_id",
        "stable_block_key",
        "class_id",
        "subject_id",
        "teacher_id",
        "room_id",
        "room_type_id",
        "date",
        "timeslot_id",
        "duration_minutes",
        "module_sequence_index",
        "is_recovery_block",
        "recovery_source_occurrence_id",
        "recovery_source_occurrence_revision",
        "change_type",
        "reason_code",
        "created_at",
    } <= set(table.columns.keys())
    assert "REMOVED" not in {value.value for value in models.ScheduleDraftBlockChangeType}


def test_schedule_draft_blocks_enforce_overlap_and_recovery_invariants():
    table = models.ScheduleDraftBlock.__table__
    constraint_names = {constraint.name for constraint in table.constraints}

    assert {
        "uq_schedule_draft_blocks_stable_key",
        "uq_schedule_draft_blocks_class_slot",
        "uq_schedule_draft_blocks_teacher_slot",
        "uq_schedule_draft_blocks_room_slot",
        "ck_schedule_draft_blocks_duration_positive",
        "ck_schedule_draft_blocks_recovery_source",
        "ck_schedule_draft_blocks_recovery_revision_positive",
        "ck_schedule_draft_blocks_change_source",
        "ck_schedule_draft_blocks_stable_key_nonempty",
    } <= constraint_names
    assert table_default(models.ScheduleDraftBlock, "is_recovery_block") is False

    draft_scope = next(
        constraint
        for constraint in table.foreign_key_constraints
        if constraint.name == "fk_schedule_draft_blocks_draft_scope"
    )
    assert tuple(column.name for column in draft_scope.columns) == (
        "draft_id",
        "organization_id",
        "school_year_id",
    )
    source_fk = next(
        fk
        for fk in table.foreign_key_constraints
        if fk.name == "fk_schedule_draft_blocks_source_active"
    )
    assert tuple(element.target_fullname for element in source_fk.elements) == (
        "active_schedule_blocks.id",
    )
    assert source_fk.ondelete == "RESTRICT"


def test_schedule_diff_entries_preserve_audit_snapshots_and_references():
    table = models.ScheduleDiffEntry.__table__

    assert {
        "organization_id",
        "school_year_id",
        "generation_job_id",
        "draft_id",
        "class_id",
        "subject_id",
        "teacher_id",
        "before_active_block_id",
        "after_draft_block_id",
        "before_date",
        "before_timeslot_id",
        "before_room_id",
        "after_date",
        "after_timeslot_id",
        "after_room_id",
        "before_snapshot_json",
        "after_snapshot_json",
        "change_type",
        "impact_scope",
        "reason_code",
        "reason_message",
        "recovery_link_impact_json",
        "created_at",
    } <= set(table.columns.keys())
    assert {value.value for value in models.ScheduleDiffChangeType} == {
        "ADDED",
        "MOVED",
        "CHANGED",
        "REMOVED",
        "UNCHANGED_IMPACTED",
    }


def test_schedule_diff_entries_are_parent_scoped_and_snapshot_safe():
    table = models.ScheduleDiffEntry.__table__
    constraint_names = {constraint.name for constraint in table.constraints}
    draft_scope = next(
        constraint
        for constraint in table.foreign_key_constraints
        if constraint.name == "fk_schedule_diff_entries_draft_job_scope"
    )

    assert "ck_schedule_diff_entries_sides" in constraint_names
    assert tuple(column.name for column in draft_scope.columns) == (
        "draft_id",
        "generation_job_id",
        "organization_id",
        "school_year_id",
    )
    before_fk = next(
        fk
        for fk in table.foreign_key_constraints
        if fk.name == "fk_schedule_diff_entries_before_active"
    )
    assert tuple(element.target_fullname for element in before_fk.elements) == (
        "active_schedule_blocks.id",
    )
    assert table_default(models.ScheduleDiffEntry, "impact_scope") == (
        models.ScheduleDiffScope.AFFECTED
    )


def test_active_schedule_blocks_are_versioned_approved_targets():
    table = models.ActiveScheduleBlock.__table__
    constraint_names = {constraint.name for constraint in table.constraints}
    index_names = {index.name for index in table.indexes}

    assert {
        "organization_id",
        "school_year_id",
        "schedule_version_id",
        "stable_block_key",
        "class_id",
        "subject_id",
        "teacher_id",
        "room_id",
        "date",
        "timeslot_id",
        "duration_minutes",
        "source_draft_block_id",
        "is_recovery_block",
        "status",
        "created_at",
        "updated_at",
    } <= set(table.columns.keys())
    assert {
        "uq_active_schedule_blocks_id_scope",
        "uq_active_schedule_blocks_source_draft_block",
        "uq_active_schedule_blocks_version_stable_key",
        "ck_active_schedule_blocks_duration_positive",
    } <= constraint_names
    assert {
        "uq_active_schedule_blocks_class_slot",
        "uq_active_schedule_blocks_teacher_slot",
        "uq_active_schedule_blocks_room_slot",
    } <= index_names
    assert table_default(models.ActiveScheduleBlock, "status") == (
        models.ActiveScheduleBlockStatus.ACTIVE
    )


def test_planned_recovery_links_are_scoped_and_delivery_idempotent():
    table = models.PlannedRecoveryLink.__table__
    constraint_names = {constraint.name for constraint in table.constraints}
    foreign_key_names = {constraint.name for constraint in table.foreign_key_constraints}

    assert {
        "organization_id",
        "school_year_id",
        "debt_occurrence_id",
        "debt_occurrence_revision",
        "planned_active_block_id",
        "planned_draft_block_id",
        "planned_recovery_minutes",
        "delivered_recovery_minutes",
        "delivered_lesson_log_id",
        "delivered_at",
        "class_id",
        "subject_id",
        "teacher_id",
        "status",
        "created_at",
        "updated_at",
    } <= set(table.columns.keys())
    assert {
        "uq_planned_recovery_links_active_block",
        "uq_planned_recovery_links_draft_block",
        "uq_planned_recovery_links_delivery_log",
        "ck_planned_recovery_links_planned_minutes_positive",
        "ck_planned_recovery_links_delivered_minutes_range",
        "ck_planned_recovery_links_has_target",
        "ck_planned_recovery_links_delivery_evidence",
    } <= constraint_names
    assert {
        "fk_planned_recovery_links_debt_scope",
        "fk_planned_recovery_links_active_block_scope",
        "fk_planned_recovery_links_draft_block_scope",
        "fk_planned_recovery_links_delivery_evidence",
    } <= foreign_key_names
    assert table_default(models.PlannedRecoveryLink, "status") == (
        models.PlannedRecoveryLinkStatus.PLANNED
    )
    assert table_default(models.PlannedRecoveryLink, "delivered_recovery_minutes") == 0


def test_lesson_occurrence_exposes_revisioned_debt_identity():
    constraint_names = {
        constraint.name for constraint in models.LessonOccurrence.__table__.constraints
    }

    assert "uq_lesson_occurrence_id_org_revision" in constraint_names


def test_lesson_log_can_prove_delivery_for_exact_active_block():
    table = models.LessonLog.__table__
    constraint_names = {constraint.name for constraint in table.constraints}

    assert "active_schedule_block_id" in table.columns
    assert "ck_lesson_log_exactly_one_target" in constraint_names
    assert "uq_lesson_log_active_schedule_block" in constraint_names
    assert "uq_lesson_log_id_org_active_block" in constraint_names


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
