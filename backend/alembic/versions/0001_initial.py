"""Frozen prelaunch database baseline.

Revision ID: 0001_initial
"""

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

UPGRADE_SQL = [
    "CREATE TYPE organizationplanstatus AS ENUM ('inactive', 'active', 'suspended')",
    "CREATE TYPE membershiplifecyclestatus AS ENUM ('active', 'archived')",
    "CREATE TYPE membershipaccessstatus AS ENUM ('none', 'pending_invite', 'invite_expired', 'active', 'blocked', 'sync_error')",
    "CREATE TYPE teacheraccessmode AS ENUM ('platform', 'scheduler_only')",
    "CREATE TYPE clerkinvitationstatus AS ENUM ('pending', 'accepted', 'revoked', 'expired')",
    "CREATE TYPE memberaccessoperationtype AS ENUM ('create_invitation', 'revoke_invitation', 'revoke_membership', 'change_role', 'resend_invitation', 'restore_access', 'block_access')",
    "CREATE TYPE memberaccessoperationstatus AS ENUM ('pending', 'clerk_succeeded', 'local_committed', 'failed', 'compensated', 'compensation_failed', 'support_required')",
    "CREATE TYPE clerkwebhookprocessingstatus AS ENUM ('received', 'processing', 'processed', 'ignored', 'retryable_failed', 'sync_error', 'dead_letter')",
    "CREATE TYPE roomtype AS ENUM ('normal', 'lab', 'gym', 'art')",
    "CREATE TYPE constrainttype AS ENUM ('specific_room', 'lock_time', 'teacher_unavailable', 'teacher_preferred')",
    "CREATE TYPE schoolyearpublicationstate AS ENUM ('UNPUBLISHED', 'PUBLISHED')",
    "CREATE TYPE schedulegenerationstrategy AS ENUM ('COMPLETE_GENERATION', 'ADAPTIVE_REPAIR')",
    "CREATE TYPE schedulegenerationtrigger AS ENUM ('FIRST_GENERATION', 'EXPLICIT_DEBT', 'SCHEDULER_CHANGE', 'MIXED')",
    "CREATE TYPE schedulegenerationjobstatus AS ENUM ('QUEUED', 'RUNNING', 'CANCEL_REQUESTED', 'CANCELED', 'SUCCEEDED', 'FAILED', 'NO_VALID_OUTPUT')",
    "CREATE TYPE schedulegenerationresultcategory AS ENUM ('COMPLETE_SUCCESS', 'PARTIAL_RECOVERY', 'NO_VALID_OUTPUT')",
    "CREATE TYPE scheduledraftstate AS ENUM ('PENDING', 'APPROVED', 'REJECTED', 'REPLACED', 'STALE', 'INVALIDATED')",
    "CREATE TYPE scheduledraftblockchangetype AS ENUM ('UNCHANGED', 'ADDED', 'MOVED', 'ROOM_ONLY', 'REPLACED')",
    "CREATE TYPE schedulediffchangetype AS ENUM ('ADDED', 'MOVED', 'CHANGED', 'REMOVED', 'UNCHANGED_IMPACTED')",
    "CREATE TYPE schedulediffscope AS ENUM ('AFFECTED', 'RELATED', 'UNRELATED')",
    "CREATE TYPE activescheduleblockstatus AS ENUM ('ACTIVE', 'REMOVED', 'CANCELED')",
    "CREATE TYPE plannedrecoverylinkstatus AS ENUM ('PLANNED', 'DELIVERED', 'CANCELED', 'REPLACED')",
    "CREATE TYPE schedulerstatechangeoperation AS ENUM ('CREATE', 'UPDATE', 'DELETE', 'BULK_IMPORT')",
    "CREATE TYPE schedulerstatechangescope AS ENUM ('FUTURE_IMPACTING', 'PAST_ONLY', 'NO_OP', 'INACTIVE_RESOURCE')",
    "CREATE TYPE calendareventtype AS ENUM ('national_holiday', 'school_break', 'exam_period', 'other')",
    "CREATE TYPE calendareventsource AS ENUM ('auto', 'manual')",
    "CREATE TYPE lessonoccurrencestatus AS ENUM ('GIVEN', 'GAP', 'SUBSTITUTED', 'REVOKED')",
    "CREATE TYPE operationalblockstatus AS ENUM ('ACTIVE', 'CANCELLED')",
    "CREATE TYPE operationalblockexecutionstatus AS ENUM ('PENDING_LOG', 'COMPLETED', 'CANCELLED')",
    "CREATE TYPE lessonlogstatus AS ENUM ('PENDING', 'COMPLETED', 'OCCURRENCE')",
    "CREATE TYPE timesheetstatus AS ENUM ('OPEN', 'SUBMITTED', 'APPROVED')",
    "CREATE TABLE organization (\n\tid SERIAL NOT NULL, \n\tname VARCHAR(100) NOT NULL, \n\tclerk_org_id VARCHAR(255), \n\tplan_status organizationplanstatus NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (clerk_org_id)\n)",
    'CREATE TABLE "user" (\n\tid SERIAL NOT NULL, \n\tname VARCHAR(150), \n\temail VARCHAR(100) NOT NULL, \n\tclerk_user_id VARCHAR(255), \n\tclerk_primary_email_id VARCHAR(255), \n\tclerk_profile_name VARCHAR(255), \n\tlast_clerk_sync_at TIMESTAMP WITH TIME ZONE, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (clerk_user_id)\n)',
    'CREATE UNIQUE INDEX ix_user_email ON "user" (email)',
    "CREATE TABLE teacher (\n\tid SERIAL NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\torganization_membership_id INTEGER NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id)\n)",
    "CREATE UNIQUE INDEX ix_teacher_organization_membership_id ON teacher (organization_membership_id)",
    "CREATE TABLE organization_membership (\n\tid SERIAL NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\taccount_id INTEGER NOT NULL, \n\torganization_display_name VARCHAR(150) NOT NULL, \n\tlifecycle_status membershiplifecyclestatus NOT NULL, \n\taccess_status membershipaccessstatus NOT NULL, \n\tteacher_access_mode teacheraccessmode, \n\tcan_admin BOOLEAN NOT NULL, \n\tcan_teach BOOLEAN NOT NULL, \n\tclerk_membership_id VARCHAR(255), \n\tclerk_invitation_id VARCHAR(255), \n\tclerk_invitation_status clerkinvitationstatus, \n\tinvitation_expires_at TIMESTAMP WITH TIME ZONE, \n\taccess_error_category VARCHAR(80), \n\taccess_error_safe_message VARCHAR(240), \n\taccess_block_reason VARCHAR(120), \n\tcreated_by_membership_id INTEGER, \n\tupdated_by_membership_id INTEGER, \n\tlock_version INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_org_membership_account UNIQUE (organization_id, account_id), \n\tCONSTRAINT ck_membership_active_has_account CHECK (access_status != 'active' OR account_id IS NOT NULL), \n\tCONSTRAINT ck_membership_has_capability CHECK (can_admin OR can_teach), \n\tCONSTRAINT ck_membership_teacher_mode CHECK (can_teach = (teacher_access_mode IS NOT NULL)), \n\tCONSTRAINT ck_membership_admin_not_scheduler_only CHECK (NOT (can_admin AND teacher_access_mode = 'scheduler_only')), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE CASCADE, \n\tFOREIGN KEY(account_id) REFERENCES \"user\" (id) ON DELETE CASCADE, \n\tFOREIGN KEY(created_by_membership_id) REFERENCES organization_membership (id) ON DELETE SET NULL, \n\tFOREIGN KEY(updated_by_membership_id) REFERENCES organization_membership (id) ON DELETE SET NULL\n)",
    "CREATE INDEX ix_organization_membership_lifecycle_status ON organization_membership (lifecycle_status)",
    "CREATE INDEX ix_organization_membership_clerk_membership_id ON organization_membership (clerk_membership_id)",
    "CREATE INDEX ix_organization_membership_account_id ON organization_membership (account_id)",
    "CREATE INDEX ix_organization_membership_access_status ON organization_membership (access_status)",
    "CREATE INDEX ix_organization_membership_clerk_invitation_id ON organization_membership (clerk_invitation_id)",
    "CREATE UNIQUE INDEX uq_org_membership_clerk_membership ON organization_membership (clerk_membership_id) WHERE clerk_membership_id IS NOT NULL",
    "CREATE UNIQUE INDEX uq_org_membership_clerk_invitation ON organization_membership (clerk_invitation_id) WHERE clerk_invitation_id IS NOT NULL",
    "CREATE INDEX ix_organization_membership_organization_id ON organization_membership (organization_id)",
    'CREATE TABLE clerk_webhook_event (\n\tid SERIAL NOT NULL, \n\tsvix_id VARCHAR(255) NOT NULL, \n\tevent_type VARCHAR(120) NOT NULL, \n\tclerk_object_id VARCHAR(255), \n\tclerk_org_id VARCHAR(255), \n\tclerk_user_id VARCHAR(255), \n\tpayload_json JSON NOT NULL, \n\tprocessing_status clerkwebhookprocessingstatus NOT NULL, \n\terror_category VARCHAR(80), \n\tsupport_resolution_action VARCHAR(80), \n\tsupport_resolved_by_user_id INTEGER, \n\tsupport_resolved_at TIMESTAMP WITH TIME ZONE, \n\tsupport_resolution_note VARCHAR(500), \n\tattempt_count INTEGER NOT NULL, \n\tlast_attempt_at TIMESTAMP WITH TIME ZONE, \n\tnext_retry_at TIMESTAMP WITH TIME ZONE, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tprocessed_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(support_resolved_by_user_id) REFERENCES "user" (id) ON DELETE SET NULL\n)',
    "CREATE INDEX ix_clerk_webhook_event_processing_status ON clerk_webhook_event (processing_status)",
    "CREATE INDEX ix_clerk_webhook_event_clerk_org_id ON clerk_webhook_event (clerk_org_id)",
    "CREATE INDEX ix_clerk_webhook_event_clerk_user_id ON clerk_webhook_event (clerk_user_id)",
    "CREATE INDEX ix_clerk_webhook_event_event_type ON clerk_webhook_event (event_type)",
    "CREATE INDEX ix_clerk_webhook_event_clerk_object_id ON clerk_webhook_event (clerk_object_id)",
    "CREATE UNIQUE INDEX ix_clerk_webhook_event_svix_id ON clerk_webhook_event (svix_id)",
    "CREATE INDEX ix_clerk_webhook_due_work ON clerk_webhook_event (processing_status, next_retry_at, created_at)",
    "CREATE TABLE room (\n\tid SERIAL NOT NULL, \n\tname VARCHAR(100) NOT NULL, \n\tcapacity INTEGER NOT NULL, \n\ttype roomtype NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id)\n)",
    "CREATE TABLE subject (\n\tid SERIAL NOT NULL, \n\tname VARCHAR(100) NOT NULL, \n\trequired_room_type roomtype NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id)\n)",
    "CREATE TABLE timeslot (\n\tid SERIAL NOT NULL, \n\tday_of_week INTEGER NOT NULL, \n\tstart_time TIME WITHOUT TIME ZONE NOT NULL, \n\tend_time TIME WITHOUT TIME ZONE NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_timeslot UNIQUE (day_of_week, start_time, organization_id), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id)\n)",
    "CREATE TABLE organization_settings (\n\tid SERIAL NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\tschool_start_date DATE, \n\tschool_hard_end_date DATE, \n\trepair_stability_window_days INTEGER, \n\tauto_confirm_enabled BOOLEAN NOT NULL, \n\tauto_confirm_cutoff_time TIME WITHOUT TIME ZONE, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE CASCADE\n)",
    "CREATE UNIQUE INDEX ix_organization_settings_organization_id ON organization_settings (organization_id)",
    "CREATE TABLE scheduler_school_year (\n\tid SERIAL NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\tlabel VARCHAR(20) NOT NULL, \n\tstart_date DATE NOT NULL, \n\thard_end_date DATE NOT NULL, \n\ttimezone VARCHAR(64) NOT NULL, \n\tis_active BOOLEAN NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_scheduler_school_year_id_org UNIQUE (id, organization_id), \n\tCONSTRAINT uq_scheduler_school_year_org_label UNIQUE (organization_id, label), \n\tCONSTRAINT ck_scheduler_school_year_date_order CHECK (hard_end_date >= start_date), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE CASCADE\n)",
    "CREATE UNIQUE INDEX uq_scheduler_school_year_active_org ON scheduler_school_year (organization_id) WHERE is_active IS true",
    "CREATE INDEX ix_scheduler_school_year_organization_id ON scheduler_school_year (organization_id)",
    "CREATE TABLE organization_grid_settings (\n\tid SERIAL NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\tlunch_window_start TIME WITHOUT TIME ZONE, \n\tlunch_window_end TIME WITHOUT TIME ZONE, \n\tlunch_min_duration_minutes INTEGER, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE CASCADE\n)",
    "CREATE UNIQUE INDEX ix_organization_grid_settings_organization_id ON organization_grid_settings (organization_id)",
    "CREATE TABLE school_calendar_event (\n\tid SERIAL NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\tname VARCHAR(150) NOT NULL, \n\tstart_date DATE NOT NULL, \n\tend_date DATE NOT NULL, \n\tevent_type calendareventtype NOT NULL, \n\tsource calendareventsource NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE CASCADE\n)",
    "CREATE INDEX ix_school_calendar_event_organization_id ON school_calendar_event (organization_id)",
    "CREATE TABLE teacher_endpoint_operational_event (\n\tid SERIAL NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\tactor_membership_id INTEGER, \n\tactor_role VARCHAR(20), \n\tendpoint_key VARCHAR(80) NOT NULL, \n\thttp_status INTEGER NOT NULL, \n\tlatency_ms INTEGER NOT NULL, \n\tactive_generation_id VARCHAR(100), \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE CASCADE, \n\tFOREIGN KEY(actor_membership_id) REFERENCES organization_membership (id) ON DELETE SET NULL\n)",
    "CREATE INDEX ix_teacher_endpoint_event_org_created ON teacher_endpoint_operational_event (organization_id, created_at)",
    "CREATE INDEX ix_teacher_endpoint_operational_event_created_at ON teacher_endpoint_operational_event (created_at)",
    "CREATE INDEX ix_teacher_endpoint_event_org_endpoint_created ON teacher_endpoint_operational_event (organization_id, endpoint_key, created_at)",
    "CREATE INDEX ix_teacher_endpoint_operational_event_actor_membership_id ON teacher_endpoint_operational_event (actor_membership_id)",
    "CREATE INDEX ix_teacher_endpoint_operational_event_http_status ON teacher_endpoint_operational_event (http_status)",
    "CREATE INDEX ix_teacher_endpoint_operational_event_endpoint_key ON teacher_endpoint_operational_event (endpoint_key)",
    "CREATE INDEX ix_teacher_endpoint_operational_event_organization_id ON teacher_endpoint_operational_event (organization_id)",
    "CREATE TABLE course (\n\tid SERIAL NOT NULL, \n\tname VARCHAR(150) NOT NULL, \n\tabbreviation VARCHAR(10) NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_course_org_abbreviation UNIQUE (organization_id, abbreviation), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id)\n)",
    "CREATE TABLE course_subject_link (\n\torganization_id INTEGER NOT NULL, \n\tcourse_id INTEGER NOT NULL, \n\tsubject_id INTEGER NOT NULL, \n\tPRIMARY KEY (organization_id, course_id, subject_id), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE CASCADE, \n\tFOREIGN KEY(course_id) REFERENCES course (id) ON DELETE CASCADE, \n\tFOREIGN KEY(subject_id) REFERENCES subject (id) ON DELETE CASCADE\n)",
    "CREATE INDEX ix_course_subject_link_organization_id ON course_subject_link (organization_id)",
    "CREATE TABLE teacher_subject_link (\n\torganization_id INTEGER NOT NULL, \n\tteacher_id INTEGER NOT NULL, \n\tsubject_id INTEGER NOT NULL, \n\tPRIMARY KEY (organization_id, teacher_id, subject_id), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE CASCADE, \n\tFOREIGN KEY(teacher_id) REFERENCES teacher (id) ON DELETE CASCADE, \n\tFOREIGN KEY(subject_id) REFERENCES subject (id) ON DELETE CASCADE\n)",
    "CREATE INDEX ix_teacher_subject_link_organization_id ON teacher_subject_link (organization_id)",
    "CREATE TABLE availability (\n\tid SERIAL NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\tteacher_id INTEGER NOT NULL, \n\ttimeslot_id INTEGER NOT NULL, \n\tscore INTEGER NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_teacher_timeslot_availability UNIQUE (organization_id, teacher_id, timeslot_id), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE CASCADE, \n\tFOREIGN KEY(teacher_id) REFERENCES teacher (id), \n\tFOREIGN KEY(timeslot_id) REFERENCES timeslot (id)\n)",
    "CREATE INDEX ix_availability_timeslot_id ON availability (timeslot_id)",
    "CREATE INDEX ix_availability_organization_id ON availability (organization_id)",
    "CREATE INDEX ix_availability_teacher_id ON availability (teacher_id)",
    'CREATE TABLE member_access_operation (\n\tid SERIAL NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\tmembership_id INTEGER, \n\taccount_id INTEGER, \n\ttarget_email VARCHAR(255) NOT NULL, \n\toperation_type memberaccessoperationtype NOT NULL, \n\toperation_status memberaccessoperationstatus NOT NULL, \n\tidempotency_key VARCHAR(160) NOT NULL, \n\tintended_capabilities_json JSON NOT NULL, \n\tintended_clerk_role VARCHAR(40), \n\tprevious_access_snapshot_json JSON, \n\tdraft_payload_json JSON, \n\tclerk_org_id VARCHAR(255), \n\tclerk_user_id VARCHAR(255), \n\tclerk_membership_id VARCHAR(255), \n\tclerk_invitation_id VARCHAR(255), \n\tprovider_error_category VARCHAR(80), \n\tprovider_error_safe_message VARCHAR(240), \n\tprovider_error_reference VARCHAR(120), \n\tcompensation_attempted_at TIMESTAMP WITH TIME ZONE, \n\tsupport_required_at TIMESTAMP WITH TIME ZONE, \n\tsupport_resolution_action VARCHAR(80), \n\tsupport_resolved_by_user_id INTEGER, \n\tsupport_resolved_at TIMESTAMP WITH TIME ZONE, \n\tsupport_resolution_note VARCHAR(500), \n\tcreated_by_membership_id INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE CASCADE, \n\tFOREIGN KEY(membership_id) REFERENCES organization_membership (id) ON DELETE SET NULL, \n\tFOREIGN KEY(account_id) REFERENCES "user" (id) ON DELETE SET NULL, \n\tFOREIGN KEY(support_resolved_by_user_id) REFERENCES "user" (id) ON DELETE SET NULL, \n\tFOREIGN KEY(created_by_membership_id) REFERENCES organization_membership (id) ON DELETE RESTRICT\n)',
    "CREATE INDEX ix_member_access_operation_target_email ON member_access_operation (target_email)",
    "CREATE INDEX ix_member_access_operation_account_id ON member_access_operation (account_id)",
    "CREATE INDEX ix_member_access_operation_operation_status ON member_access_operation (operation_status)",
    "CREATE INDEX ix_member_access_operation_membership_id ON member_access_operation (membership_id)",
    "CREATE INDEX ix_member_access_operation_organization_id ON member_access_operation (organization_id)",
    "CREATE UNIQUE INDEX ix_member_access_operation_idempotency_key ON member_access_operation (idempotency_key)",
    "CREATE UNIQUE INDEX uq_member_operation_unresolved_membership ON member_access_operation (organization_id, membership_id) WHERE membership_id IS NOT NULL AND operation_status IN ('pending', 'clerk_succeeded', 'compensation_failed', 'support_required')",
    "CREATE UNIQUE INDEX uq_member_operation_unresolved_email ON member_access_operation (organization_id, lower(target_email)) WHERE operation_status IN ('pending', 'clerk_succeeded', 'compensation_failed', 'support_required')",
    "CREATE TABLE class (\n\tid SERIAL NOT NULL, \n\tname VARCHAR(100) NOT NULL, \n\tsize INTEGER NOT NULL, \n\tstart_year INTEGER NOT NULL, \n\tend_year INTEGER NOT NULL, \n\tgrade_level INTEGER NOT NULL, \n\tprojected_end_date DATE, \n\tis_archived BOOLEAN NOT NULL, \n\tcourse_id INTEGER NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(course_id) REFERENCES course (id), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id)\n)",
    "CREATE TABLE schedule_generation_job (\n\tid SERIAL NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\tschool_year_id INTEGER NOT NULL, \n\trequested_by_membership_id INTEGER, \n\tstrategy schedulegenerationstrategy NOT NULL, \n\ttrigger_type schedulegenerationtrigger, \n\tjob_status schedulegenerationjobstatus NOT NULL, \n\tresult_category schedulegenerationresultcategory, \n\tgeneration_input_fingerprint VARCHAR(64), \n\tdebt_basis_fingerprint VARCHAR(64), \n\tscheduler_state_version_used INTEGER, \n\trepair_policy_snapshot_hash VARCHAR(64), \n\tinput_snapshot_json JSON, \n\tqueued_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tstarted_at TIMESTAMP WITH TIME ZONE, \n\tfinished_at TIMESTAMP WITH TIME ZONE, \n\tdeadline_at TIMESTAMP WITH TIME ZONE, \n\tduration_ms INTEGER, \n\tcancellation_requested_at TIMESTAMP WITH TIME ZONE, \n\tfailure_code VARCHAR(50), \n\tfailure_message TEXT, \n\tidempotency_key VARCHAR(100), \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_schedule_generation_job_year_scope FOREIGN KEY(school_year_id, organization_id) REFERENCES scheduler_school_year (id, organization_id) ON DELETE CASCADE, \n\tCONSTRAINT uq_schedule_generation_job_id_scope UNIQUE (id, organization_id, school_year_id), \n\tCONSTRAINT uq_schedule_generation_job_idempotency UNIQUE (organization_id, school_year_id, idempotency_key), \n\tCONSTRAINT ck_schedule_generation_job_duration_nonnegative CHECK (duration_ms IS NULL OR duration_ms >= 0), \n\tCONSTRAINT ck_schedule_generation_job_result_consistency CHECK ((job_status = 'SUCCEEDED' AND result_category IN ('COMPLETE_SUCCESS', 'PARTIAL_RECOVERY')) OR (job_status = 'NO_VALID_OUTPUT' AND result_category = 'NO_VALID_OUTPUT') OR (job_status NOT IN ('SUCCEEDED', 'NO_VALID_OUTPUT') AND result_category IS NULL)), \n\tCONSTRAINT ck_schedule_generation_job_terminal_finished CHECK ((job_status IN ('CANCELED', 'SUCCEEDED', 'FAILED', 'NO_VALID_OUTPUT') AND finished_at IS NOT NULL) OR (job_status NOT IN ('CANCELED', 'SUCCEEDED', 'FAILED', 'NO_VALID_OUTPUT') AND finished_at IS NULL)), \n\tCONSTRAINT ck_schedule_generation_job_started_after_queued CHECK (started_at IS NULL OR started_at >= queued_at), \n\tCONSTRAINT ck_schedule_generation_job_finished_after_started CHECK (finished_at IS NULL OR (started_at IS NOT NULL AND finished_at >= started_at)), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE CASCADE, \n\tFOREIGN KEY(requested_by_membership_id) REFERENCES organization_membership (id) ON DELETE SET NULL\n)",
    "CREATE INDEX ix_schedule_generation_job_organization_id ON schedule_generation_job (organization_id)",
    "CREATE UNIQUE INDEX uq_schedule_generation_job_active_year ON schedule_generation_job (organization_id, school_year_id) WHERE job_status IN ('QUEUED', 'RUNNING', 'CANCEL_REQUESTED')",
    "CREATE INDEX ix_schedule_generation_job_school_year_id ON schedule_generation_job (school_year_id)",
    "CREATE TABLE teacher_weekly_timesheet (\n\tid SERIAL NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\tteacher_id INTEGER NOT NULL, \n\tweek_start_date DATE NOT NULL, \n\tstatus timesheetstatus NOT NULL, \n\tsubmitted_at TIMESTAMP WITH TIME ZONE, \n\tapproved_at TIMESTAMP WITH TIME ZONE, \n\tapproved_by_membership_id INTEGER, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_teacher_weekly_timesheet UNIQUE (organization_id, teacher_id, week_start_date), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE CASCADE, \n\tFOREIGN KEY(teacher_id) REFERENCES teacher (id) ON DELETE CASCADE, \n\tFOREIGN KEY(approved_by_membership_id) REFERENCES organization_membership (id) ON DELETE SET NULL\n)",
    "CREATE INDEX ix_teacher_weekly_timesheet_teacher_id ON teacher_weekly_timesheet (teacher_id)",
    "CREATE INDEX ix_teacher_weekly_timesheet_organization_id ON teacher_weekly_timesheet (organization_id)",
    "CREATE INDEX ix_timesheet_org_week ON teacher_weekly_timesheet (organization_id, week_start_date)",
    'CREATE TABLE module (\n\tid SERIAL NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\tname VARCHAR(150) NOT NULL, \n\tcode VARCHAR(50), \n\trequired_minutes INTEGER NOT NULL, \n\t"order" INTEGER NOT NULL, \n\tsubject_id INTEGER NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_module_required_minutes CHECK (required_minutes > 0), \n\tCONSTRAINT ck_module_order_nonnegative CHECK ("order" >= 0), \n\tCONSTRAINT uq_module_order_per_subject UNIQUE (organization_id, subject_id, "order"), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE CASCADE, \n\tFOREIGN KEY(subject_id) REFERENCES subject (id)\n)',
    "CREATE INDEX ix_module_organization_id ON module (organization_id)",
    "CREATE TABLE class_subject_link (\n\tid SERIAL NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\tclass_id INTEGER NOT NULL, \n\tsubject_id INTEGER NOT NULL, \n\tgrade_level INTEGER NOT NULL, \n\tteacher_id INTEGER, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_class_subject_grade UNIQUE (organization_id, class_id, subject_id, grade_level), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE CASCADE, \n\tFOREIGN KEY(class_id) REFERENCES class (id) ON DELETE CASCADE, \n\tFOREIGN KEY(subject_id) REFERENCES subject (id) ON DELETE CASCADE, \n\tFOREIGN KEY(teacher_id) REFERENCES teacher (id) ON DELETE SET NULL\n)",
    "CREATE INDEX ix_class_subject_link_organization_id ON class_subject_link (organization_id)",
    "CREATE INDEX ix_class_subject_link_teacher_id ON class_subject_link (teacher_id)",
    "CREATE INDEX ix_class_subject_link_subject_id ON class_subject_link (subject_id)",
    "CREATE INDEX ix_class_subject_link_class_id ON class_subject_link (class_id)",
    "CREATE TABLE \"constraint\" (\n\tid SERIAL NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\trule_type constrainttype NOT NULL, \n\tclass_id INTEGER, \n\tsubject_id INTEGER, \n\tteacher_id INTEGER, \n\troom_id INTEGER, \n\ttimeslot_id INTEGER, \n\tconstraint_date DATE, \n\tday_of_week INTEGER, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_constraint_day CHECK (day_of_week IS NULL OR day_of_week BETWEEN 0 AND 6), \n\tCONSTRAINT ck_constraint_typed_shape CHECK ((rule_type = 'specific_room' AND class_id IS NOT NULL AND subject_id IS NOT NULL AND room_id IS NOT NULL AND teacher_id IS NULL AND timeslot_id IS NULL AND constraint_date IS NULL AND day_of_week IS NULL) OR (rule_type = 'lock_time' AND class_id IS NOT NULL AND subject_id IS NOT NULL AND timeslot_id IS NOT NULL AND teacher_id IS NULL AND room_id IS NULL AND constraint_date IS NULL AND day_of_week IS NULL) OR (rule_type = 'teacher_preferred' AND teacher_id IS NOT NULL AND timeslot_id IS NOT NULL AND class_id IS NULL AND subject_id IS NULL AND room_id IS NULL AND constraint_date IS NULL AND day_of_week IS NULL) OR (rule_type = 'teacher_unavailable' AND teacher_id IS NOT NULL AND class_id IS NULL AND subject_id IS NULL AND room_id IS NULL AND ((timeslot_id IS NOT NULL AND constraint_date IS NULL AND day_of_week IS NULL) OR (timeslot_id IS NULL AND constraint_date IS NOT NULL AND day_of_week IS NULL) OR (timeslot_id IS NULL AND constraint_date IS NULL AND day_of_week IS NOT NULL) OR (timeslot_id IS NOT NULL AND constraint_date IS NOT NULL AND day_of_week IS NULL)))), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE CASCADE, \n\tFOREIGN KEY(class_id) REFERENCES class (id), \n\tFOREIGN KEY(subject_id) REFERENCES subject (id), \n\tFOREIGN KEY(teacher_id) REFERENCES teacher (id), \n\tFOREIGN KEY(room_id) REFERENCES room (id), \n\tFOREIGN KEY(timeslot_id) REFERENCES timeslot (id)\n)",
    'CREATE INDEX ix_constraint_organization_id ON "constraint" (organization_id)',
    "CREATE TABLE schedule_drafts (\n\tid SERIAL NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\tschool_year_id INTEGER NOT NULL, \n\tgeneration_job_id INTEGER NOT NULL, \n\tstrategy schedulegenerationstrategy NOT NULL, \n\tdraft_state scheduledraftstate NOT NULL, \n\tresult_category schedulegenerationresultcategory NOT NULL, \n\ttrigger_type schedulegenerationtrigger NOT NULL, \n\tgeneration_input_fingerprint VARCHAR(64) NOT NULL, \n\tscheduler_state_version_used INTEGER, \n\tdebt_basis_fingerprint VARCHAR(64), \n\trepair_policy_snapshot_json JSON, \n\trepair_policy_snapshot_hash VARCHAR(64), \n\teditable_start_date DATE, \n\trecovery_escalation_level VARCHAR(50), \n\tadaptation_level VARCHAR(50), \n\tprojected_completion_date DATE NOT NULL, \n\thard_end_date DATE NOT NULL, \n\tsummary_json JSON NOT NULL, \n\tpartial_recovery_blocker_type VARCHAR(50), \n\tmain_blocker_message TEXT, \n\trecommended_actions_json JSON, \n\twarnings_json JSON, \n\tmetrics_json JSON, \n\tstale_reason TEXT, \n\tinvalidated_reason TEXT, \n\tcreated_by_membership_id INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tdecided_by_membership_id INTEGER, \n\tdecided_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_schedule_drafts_generation_job_scope FOREIGN KEY(generation_job_id, organization_id, school_year_id) REFERENCES schedule_generation_job (id, organization_id, school_year_id) ON DELETE RESTRICT, \n\tCONSTRAINT uq_schedule_drafts_generation_job UNIQUE (generation_job_id), \n\tCONSTRAINT uq_schedule_drafts_id_scope UNIQUE (id, organization_id, school_year_id), \n\tCONSTRAINT uq_schedule_drafts_id_job_scope UNIQUE (id, generation_job_id, organization_id, school_year_id), \n\tCONSTRAINT ck_schedule_drafts_completion_by_hard_end CHECK (projected_completion_date <= hard_end_date), \n\tCONSTRAINT ck_schedule_drafts_has_valid_output CHECK (result_category <> 'NO_VALID_OUTPUT'), \n\tCONSTRAINT ck_schedule_drafts_state_version_nonnegative CHECK (scheduler_state_version_used IS NULL OR scheduler_state_version_used >= 0), \n\tCONSTRAINT ck_schedule_drafts_adaptive_editable_start CHECK (strategy = 'COMPLETE_GENERATION' OR editable_start_date IS NOT NULL), \n\tCONSTRAINT ck_schedule_drafts_decision_consistency CHECK ((draft_state = 'PENDING' AND decided_at IS NULL AND decided_by_membership_id IS NULL) OR (draft_state <> 'PENDING' AND decided_at IS NOT NULL)), \n\tCONSTRAINT ck_schedule_drafts_stale_reason CHECK ((draft_state = 'STALE' AND stale_reason IS NOT NULL) OR (draft_state <> 'STALE' AND stale_reason IS NULL)), \n\tCONSTRAINT ck_schedule_drafts_invalidated_reason CHECK ((draft_state = 'INVALIDATED' AND invalidated_reason IS NOT NULL) OR (draft_state <> 'INVALIDATED' AND invalidated_reason IS NULL)), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE CASCADE, \n\tFOREIGN KEY(school_year_id) REFERENCES scheduler_school_year (id) ON DELETE CASCADE, \n\tFOREIGN KEY(created_by_membership_id) REFERENCES organization_membership (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(decided_by_membership_id) REFERENCES organization_membership (id) ON DELETE SET NULL\n)",
    "CREATE UNIQUE INDEX uq_schedule_drafts_pending_year ON schedule_drafts (organization_id, school_year_id) WHERE draft_state = 'PENDING'",
    "CREATE INDEX ix_schedule_drafts_organization_id ON schedule_drafts (organization_id)",
    "CREATE INDEX ix_schedule_drafts_school_year_id ON schedule_drafts (school_year_id)",
    "CREATE TABLE lesson_occurrence (\n\tid SERIAL NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\tactive_schedule_block_id INTEGER, \n\tdate DATE NOT NULL, \n\tclass_id INTEGER, \n\tsubject_id INTEGER, \n\tstatus lessonoccurrencestatus, \n\trevision INTEGER NOT NULL, \n\tis_active BOOLEAN NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcreated_by_membership_id INTEGER, \n\tcreation_source VARCHAR(40), \n\treason VARCHAR(250), \n\trevoked_at TIMESTAMP WITH TIME ZONE, \n\trevoked_by_membership_id INTEGER, \n\trevoked_reason VARCHAR(250), \n\tplanned_timeslot_id INTEGER, \n\tplanned_room_id INTEGER, \n\tplanned_generation_id VARCHAR(100), \n\tplanned_minutes INTEGER NOT NULL, \n\tsubstitute_teacher_id INTEGER, \n\tsubstitute_subject_id INTEGER, \n\tplanned_teacher_id INTEGER, \n\texecuted_teacher_id INTEGER, \n\tplanned_module_id INTEGER, \n\texecuted_module_id INTEGER, \n\tgiven_minutes INTEGER NOT NULL, \n\tdecided_by_membership_id INTEGER, \n\tdecided_at TIMESTAMP WITH TIME ZONE, \n\tcreated_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_occurrence_planned_minutes CHECK (planned_minutes >= 0), \n\tCONSTRAINT ck_occurrence_given_minutes CHECK (given_minutes >= 0), \n\tCONSTRAINT uq_lesson_occurrence_id_org_revision UNIQUE (id, organization_id, revision), \n\tCONSTRAINT uq_lesson_occurrence_active_block_date_revision UNIQUE (organization_id, active_schedule_block_id, date, revision), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE CASCADE, \n\tFOREIGN KEY(class_id) REFERENCES class (id) ON DELETE SET NULL, \n\tFOREIGN KEY(subject_id) REFERENCES subject (id) ON DELETE SET NULL, \n\tFOREIGN KEY(created_by_membership_id) REFERENCES organization_membership (id) ON DELETE SET NULL, \n\tFOREIGN KEY(revoked_by_membership_id) REFERENCES organization_membership (id) ON DELETE SET NULL, \n\tFOREIGN KEY(planned_timeslot_id) REFERENCES timeslot (id) ON DELETE SET NULL, \n\tFOREIGN KEY(planned_room_id) REFERENCES room (id) ON DELETE SET NULL, \n\tFOREIGN KEY(substitute_teacher_id) REFERENCES teacher (id) ON DELETE SET NULL, \n\tFOREIGN KEY(substitute_subject_id) REFERENCES subject (id) ON DELETE SET NULL, \n\tFOREIGN KEY(planned_teacher_id) REFERENCES teacher (id) ON DELETE SET NULL, \n\tFOREIGN KEY(executed_teacher_id) REFERENCES teacher (id) ON DELETE SET NULL, \n\tFOREIGN KEY(planned_module_id) REFERENCES module (id) ON DELETE SET NULL, \n\tFOREIGN KEY(executed_module_id) REFERENCES module (id) ON DELETE SET NULL, \n\tFOREIGN KEY(decided_by_membership_id) REFERENCES organization_membership (id) ON DELETE SET NULL\n)",
    "CREATE INDEX ix_lesson_occurrence_active_schedule_block_id ON lesson_occurrence (active_schedule_block_id)",
    "CREATE INDEX ix_lesson_occurrence_is_active ON lesson_occurrence (is_active)",
    "CREATE INDEX ix_lesson_occurrence_org_active_date ON lesson_occurrence (organization_id, is_active, date)",
    "CREATE INDEX ix_lesson_occurrence_date ON lesson_occurrence (date)",
    "CREATE INDEX ix_lesson_occurrence_organization_id ON lesson_occurrence (organization_id)",
    "CREATE TABLE progress_ledger_entry (\n\tid SERIAL NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\tsource_type VARCHAR(40) NOT NULL, \n\tsource_id INTEGER NOT NULL, \n\tsource_revision INTEGER, \n\tclass_id INTEGER NOT NULL, \n\tmodule_id INTEGER NOT NULL, \n\tcompleted_minutes_delta INTEGER NOT NULL, \n\tdebt_minutes_delta INTEGER NOT NULL, \n\tidempotency_key VARCHAR(160) NOT NULL, \n\tcreated_by_membership_id INTEGER, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\treverses_ledger_entry_id INTEGER, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_progress_ledger_nonzero_delta CHECK (completed_minutes_delta <> 0 OR debt_minutes_delta <> 0), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE CASCADE, \n\tFOREIGN KEY(class_id) REFERENCES class (id), \n\tFOREIGN KEY(module_id) REFERENCES module (id), \n\tFOREIGN KEY(created_by_membership_id) REFERENCES organization_membership (id) ON DELETE SET NULL, \n\tFOREIGN KEY(reverses_ledger_entry_id) REFERENCES progress_ledger_entry (id) ON DELETE SET NULL\n)",
    "CREATE INDEX ix_progress_ledger_entry_source_type ON progress_ledger_entry (source_type)",
    "CREATE UNIQUE INDEX ix_progress_ledger_entry_idempotency_key ON progress_ledger_entry (idempotency_key)",
    "CREATE INDEX ix_progress_ledger_entry_organization_id ON progress_ledger_entry (organization_id)",
    "CREATE INDEX ix_progress_ledger_org_source ON progress_ledger_entry (organization_id, source_type, source_id)",
    "CREATE INDEX ix_progress_ledger_entry_source_id ON progress_ledger_entry (source_id)",
    "CREATE INDEX ix_progress_ledger_entry_module_id ON progress_ledger_entry (module_id)",
    "CREATE INDEX ix_progress_ledger_entry_class_id ON progress_ledger_entry (class_id)",
    "CREATE TABLE scheduler_school_year_state (\n\tid SERIAL NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\tschool_year_id INTEGER NOT NULL, \n\tschool_year_publication_state schoolyearpublicationstate NOT NULL, \n\tactive_schedule_version_id VARCHAR(100), \n\tpending_draft_id INTEGER, \n\tscheduler_state_version INTEGER NOT NULL, \n\tapproved_scheduler_state_version INTEGER, \n\treset_at TIMESTAMP WITH TIME ZONE, \n\treset_by_membership_id INTEGER, \n\tlock_version INTEGER NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_scheduler_school_year_state_year_scope FOREIGN KEY(school_year_id, organization_id) REFERENCES scheduler_school_year (id, organization_id) ON DELETE CASCADE, \n\tCONSTRAINT uq_scheduler_school_year_state_org_year UNIQUE (organization_id, school_year_id), \n\tCONSTRAINT ck_scheduler_school_year_state_version_nonnegative CHECK (scheduler_state_version >= 0), \n\tCONSTRAINT ck_scheduler_school_year_state_lock_version_nonnegative CHECK (lock_version >= 0), \n\tCONSTRAINT ck_scheduler_school_year_state_published_has_version CHECK (school_year_publication_state <> 'PUBLISHED' OR active_schedule_version_id IS NOT NULL), \n\tCONSTRAINT fk_scheduler_school_year_state_pending_draft_scope FOREIGN KEY(pending_draft_id, organization_id, school_year_id) REFERENCES schedule_drafts (id, organization_id, school_year_id), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE CASCADE, \n\tFOREIGN KEY(reset_by_membership_id) REFERENCES organization_membership (id) ON DELETE SET NULL\n)",
    "CREATE INDEX ix_scheduler_school_year_state_school_year_id ON scheduler_school_year_state (school_year_id)",
    "CREATE INDEX ix_scheduler_school_year_state_organization_id ON scheduler_school_year_state (organization_id)",
    "CREATE TABLE schedule_draft_blocks (\n\tid SERIAL NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\tschool_year_id INTEGER NOT NULL, \n\tdraft_id INTEGER NOT NULL, \n\tsource_active_block_id INTEGER, \n\tstable_block_key VARCHAR(64) NOT NULL, \n\tclass_id INTEGER NOT NULL, \n\tsubject_id INTEGER NOT NULL, \n\tteacher_id INTEGER NOT NULL, \n\troom_id INTEGER NOT NULL, \n\troom_type_id roomtype, \n\tdate DATE NOT NULL, \n\ttimeslot_id INTEGER NOT NULL, \n\tduration_minutes INTEGER NOT NULL, \n\tmodule_sequence_index INTEGER, \n\tis_recovery_block BOOLEAN NOT NULL, \n\trecovery_source_occurrence_id INTEGER, \n\trecovery_source_occurrence_revision INTEGER, \n\tchange_type scheduledraftblockchangetype NOT NULL, \n\treason_code VARCHAR(50), \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_schedule_draft_blocks_draft_scope FOREIGN KEY(draft_id, organization_id, school_year_id) REFERENCES schedule_drafts (id, organization_id, school_year_id) ON DELETE CASCADE, \n\tCONSTRAINT uq_schedule_draft_blocks_stable_key UNIQUE (draft_id, stable_block_key), \n\tCONSTRAINT uq_schedule_draft_blocks_id_scope UNIQUE (id, organization_id, school_year_id), \n\tCONSTRAINT uq_schedule_draft_blocks_class_slot UNIQUE (draft_id, class_id, date, timeslot_id), \n\tCONSTRAINT uq_schedule_draft_blocks_teacher_slot UNIQUE (draft_id, teacher_id, date, timeslot_id), \n\tCONSTRAINT uq_schedule_draft_blocks_room_slot UNIQUE (draft_id, room_id, date, timeslot_id), \n\tCONSTRAINT ck_schedule_draft_blocks_duration_positive CHECK (duration_minutes > 0), \n\tCONSTRAINT ck_schedule_draft_blocks_module_sequence_nonnegative CHECK (module_sequence_index IS NULL OR module_sequence_index >= 0), \n\tCONSTRAINT ck_schedule_draft_blocks_recovery_source CHECK ((is_recovery_block AND recovery_source_occurrence_id IS NOT NULL AND recovery_source_occurrence_revision IS NOT NULL) OR (NOT is_recovery_block AND recovery_source_occurrence_id IS NULL AND recovery_source_occurrence_revision IS NULL)), \n\tCONSTRAINT ck_schedule_draft_blocks_recovery_revision_positive CHECK (recovery_source_occurrence_revision IS NULL OR recovery_source_occurrence_revision > 0), \n\tCONSTRAINT ck_schedule_draft_blocks_change_source CHECK ((change_type = 'ADDED' AND source_active_block_id IS NULL) OR (change_type <> 'ADDED' AND source_active_block_id IS NOT NULL)), \n\tCONSTRAINT ck_schedule_draft_blocks_stable_key_nonempty CHECK (length(trim(stable_block_key)) > 0), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE CASCADE, \n\tFOREIGN KEY(school_year_id) REFERENCES scheduler_school_year (id) ON DELETE CASCADE, \n\tFOREIGN KEY(class_id) REFERENCES class (id), \n\tFOREIGN KEY(subject_id) REFERENCES subject (id), \n\tFOREIGN KEY(teacher_id) REFERENCES teacher (id), \n\tFOREIGN KEY(room_id) REFERENCES room (id), \n\tFOREIGN KEY(timeslot_id) REFERENCES timeslot (id), \n\tFOREIGN KEY(recovery_source_occurrence_id) REFERENCES lesson_occurrence (id) ON DELETE RESTRICT\n)",
    "CREATE INDEX ix_schedule_draft_blocks_school_year_id ON schedule_draft_blocks (school_year_id)",
    "CREATE INDEX ix_schedule_draft_blocks_draft_id ON schedule_draft_blocks (draft_id)",
    "CREATE INDEX ix_schedule_draft_blocks_organization_id ON schedule_draft_blocks (organization_id)",
    "CREATE TABLE schedule_diff_entries (\n\tid SERIAL NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\tschool_year_id INTEGER NOT NULL, \n\tgeneration_job_id INTEGER NOT NULL, \n\tdraft_id INTEGER NOT NULL, \n\tclass_id INTEGER NOT NULL, \n\tsubject_id INTEGER NOT NULL, \n\tteacher_id INTEGER NOT NULL, \n\tbefore_active_block_id INTEGER, \n\tafter_draft_block_id INTEGER, \n\tbefore_date DATE, \n\tbefore_timeslot_id INTEGER, \n\tbefore_room_id INTEGER, \n\tafter_date DATE, \n\tafter_timeslot_id INTEGER, \n\tafter_room_id INTEGER, \n\tbefore_snapshot_json JSON, \n\tafter_snapshot_json JSON, \n\tchange_type schedulediffchangetype NOT NULL, \n\timpact_scope schedulediffscope NOT NULL, \n\treason_code VARCHAR(50), \n\treason_message TEXT, \n\trecovery_link_impact_json JSON, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_schedule_diff_entries_draft_job_scope FOREIGN KEY(draft_id, generation_job_id, organization_id, school_year_id) REFERENCES schedule_drafts (id, generation_job_id, organization_id, school_year_id) ON DELETE CASCADE, \n\tCONSTRAINT ck_schedule_diff_entries_sides CHECK ((change_type = 'ADDED' AND before_snapshot_json IS NULL AND after_snapshot_json IS NOT NULL) OR (change_type = 'REMOVED' AND before_snapshot_json IS NOT NULL AND after_snapshot_json IS NULL) OR (change_type NOT IN ('ADDED', 'REMOVED') AND before_snapshot_json IS NOT NULL AND after_snapshot_json IS NOT NULL)), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE CASCADE, \n\tFOREIGN KEY(school_year_id) REFERENCES scheduler_school_year (id) ON DELETE CASCADE, \n\tFOREIGN KEY(class_id) REFERENCES class (id), \n\tFOREIGN KEY(subject_id) REFERENCES subject (id), \n\tFOREIGN KEY(teacher_id) REFERENCES teacher (id), \n\tFOREIGN KEY(after_draft_block_id) REFERENCES schedule_draft_blocks (id) ON DELETE SET NULL, \n\tFOREIGN KEY(before_timeslot_id) REFERENCES timeslot (id) ON DELETE SET NULL, \n\tFOREIGN KEY(before_room_id) REFERENCES room (id) ON DELETE SET NULL, \n\tFOREIGN KEY(after_timeslot_id) REFERENCES timeslot (id) ON DELETE SET NULL, \n\tFOREIGN KEY(after_room_id) REFERENCES room (id) ON DELETE SET NULL\n)",
    "CREATE INDEX ix_schedule_diff_entries_organization_id ON schedule_diff_entries (organization_id)",
    "CREATE INDEX ix_schedule_diff_entries_school_year_id ON schedule_diff_entries (school_year_id)",
    "CREATE INDEX ix_schedule_diff_entries_draft_id ON schedule_diff_entries (draft_id)",
    "CREATE TABLE active_schedule_blocks (\n\tid SERIAL NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\tschool_year_id INTEGER NOT NULL, \n\tschedule_version_id VARCHAR(100) NOT NULL, \n\tstable_block_key VARCHAR(64) NOT NULL, \n\tclass_id INTEGER NOT NULL, \n\tsubject_id INTEGER NOT NULL, \n\tteacher_id INTEGER NOT NULL, \n\troom_id INTEGER NOT NULL, \n\tdate DATE NOT NULL, \n\ttimeslot_id INTEGER NOT NULL, \n\tduration_minutes INTEGER NOT NULL, \n\tsource_draft_block_id INTEGER NOT NULL, \n\tis_recovery_block BOOLEAN NOT NULL, \n\tstatus activescheduleblockstatus NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_active_schedule_blocks_draft_block_scope FOREIGN KEY(source_draft_block_id, organization_id, school_year_id) REFERENCES schedule_draft_blocks (id, organization_id, school_year_id) ON DELETE RESTRICT, \n\tCONSTRAINT uq_active_schedule_blocks_id_scope UNIQUE (id, organization_id, school_year_id), \n\tCONSTRAINT uq_active_schedule_blocks_id_org UNIQUE (id, organization_id), \n\tCONSTRAINT uq_active_schedule_blocks_source_draft_block UNIQUE (source_draft_block_id), \n\tCONSTRAINT uq_active_schedule_blocks_version_stable_key UNIQUE (organization_id, school_year_id, schedule_version_id, stable_block_key), \n\tCONSTRAINT ck_active_schedule_blocks_duration_positive CHECK (duration_minutes > 0), \n\tCONSTRAINT ck_active_schedule_blocks_stable_key_nonempty CHECK (length(trim(stable_block_key)) > 0), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE CASCADE, \n\tFOREIGN KEY(school_year_id) REFERENCES scheduler_school_year (id) ON DELETE CASCADE, \n\tFOREIGN KEY(class_id) REFERENCES class (id), \n\tFOREIGN KEY(subject_id) REFERENCES subject (id), \n\tFOREIGN KEY(teacher_id) REFERENCES teacher (id), \n\tFOREIGN KEY(room_id) REFERENCES room (id), \n\tFOREIGN KEY(timeslot_id) REFERENCES timeslot (id)\n)",
    "CREATE UNIQUE INDEX uq_active_schedule_blocks_class_slot ON active_schedule_blocks (organization_id, school_year_id, class_id, date, timeslot_id) WHERE status = 'ACTIVE'",
    "CREATE UNIQUE INDEX uq_active_schedule_blocks_teacher_slot ON active_schedule_blocks (organization_id, school_year_id, teacher_id, date, timeslot_id) WHERE status = 'ACTIVE'",
    "CREATE INDEX ix_active_schedule_blocks_organization_id ON active_schedule_blocks (organization_id)",
    "CREATE UNIQUE INDEX uq_active_schedule_blocks_room_slot ON active_schedule_blocks (organization_id, school_year_id, room_id, date, timeslot_id) WHERE status = 'ACTIVE'",
    "CREATE INDEX ix_active_schedule_blocks_schedule_version_id ON active_schedule_blocks (schedule_version_id)",
    "CREATE INDEX ix_active_schedule_blocks_school_year_id ON active_schedule_blocks (school_year_id)",
    "CREATE TABLE scheduler_state_version_events (\n\tid SERIAL NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\tschool_year_id INTEGER NOT NULL, \n\tversion_before INTEGER NOT NULL, \n\tversion_after INTEGER NOT NULL, \n\tentity_type VARCHAR(80) NOT NULL, \n\tentity_id VARCHAR(100), \n\toperation schedulerstatechangeoperation NOT NULL, \n\tchange_scope schedulerstatechangescope NOT NULL, \n\tchanged_by_membership_id INTEGER, \n\tchanged_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tbefore_metadata_json JSON, \n\tafter_metadata_json JSON, \n\tmetadata_json JSON, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_scheduler_state_version_events_state_scope FOREIGN KEY(organization_id, school_year_id) REFERENCES scheduler_school_year_state (organization_id, school_year_id) ON DELETE CASCADE, \n\tCONSTRAINT ck_scheduler_state_version_events_versions_nonnegative CHECK (version_before >= 0 AND version_after >= 0), \n\tCONSTRAINT ck_scheduler_state_version_events_increment CHECK ((change_scope = 'FUTURE_IMPACTING' AND version_after = version_before + 1) OR (change_scope <> 'FUTURE_IMPACTING' AND version_after = version_before)), \n\tCONSTRAINT ck_scheduler_state_version_events_entity_type_nonempty CHECK (length(trim(entity_type)) > 0), \n\tFOREIGN KEY(changed_by_membership_id) REFERENCES organization_membership (id) ON DELETE SET NULL\n)",
    "CREATE INDEX ix_scheduler_state_version_events_school_year_id ON scheduler_state_version_events (school_year_id)",
    "CREATE INDEX ix_scheduler_state_version_events_organization_id ON scheduler_state_version_events (organization_id)",
    "CREATE UNIQUE INDEX uq_scheduler_state_version_events_increment ON scheduler_state_version_events (organization_id, school_year_id, version_after) WHERE change_scope = 'FUTURE_IMPACTING'",
    "CREATE TABLE occurrence_operational_event (\n\tid SERIAL NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\toccurrence_id INTEGER, \n\tactive_schedule_block_id INTEGER, \n\tactor_membership_id INTEGER, \n\tevent_type VARCHAR(50) NOT NULL, \n\tresult VARCHAR(50) NOT NULL, \n\tdecision_status VARCHAR(20), \n\tdetail VARCHAR(240), \n\tcreated_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE CASCADE, \n\tFOREIGN KEY(occurrence_id) REFERENCES lesson_occurrence (id) ON DELETE SET NULL, \n\tFOREIGN KEY(active_schedule_block_id) REFERENCES active_schedule_blocks (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(actor_membership_id) REFERENCES organization_membership (id) ON DELETE SET NULL\n)",
    "CREATE INDEX ix_occurrence_operational_event_organization_id ON occurrence_operational_event (organization_id)",
    "CREATE INDEX ix_occurrence_operational_event_occurrence_id ON occurrence_operational_event (occurrence_id)",
    "CREATE INDEX ix_occurrence_operational_event_actor_membership_id ON occurrence_operational_event (actor_membership_id)",
    "CREATE INDEX ix_occurrence_operational_event_created_at ON occurrence_operational_event (created_at)",
    "CREATE INDEX ix_occ_event_org_created ON occurrence_operational_event (organization_id, created_at)",
    "CREATE INDEX ix_occurrence_operational_event_active_schedule_block_id ON occurrence_operational_event (active_schedule_block_id)",
    "CREATE TABLE operational_schedule_block (\n\tid SERIAL NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\tsource_occurrence_id INTEGER NOT NULL, \n\tsource_occurrence_revision INTEGER NOT NULL, \n\tplanned_active_schedule_block_id INTEGER, \n\tdate DATE NOT NULL, \n\ttimeslot_id INTEGER NOT NULL, \n\troom_id INTEGER, \n\tclass_id INTEGER NOT NULL, \n\tteacher_id INTEGER NOT NULL, \n\tsubject_id INTEGER NOT NULL, \n\tmodule_id INTEGER, \n\tstatus operationalblockstatus NOT NULL, \n\texecution_status operationalblockexecutionstatus NOT NULL, \n\tcreated_by_membership_id INTEGER, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tcancelled_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE CASCADE, \n\tFOREIGN KEY(source_occurrence_id) REFERENCES lesson_occurrence (id) ON DELETE CASCADE, \n\tFOREIGN KEY(planned_active_schedule_block_id) REFERENCES active_schedule_blocks (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(timeslot_id) REFERENCES timeslot (id), \n\tFOREIGN KEY(room_id) REFERENCES room (id) ON DELETE SET NULL, \n\tFOREIGN KEY(class_id) REFERENCES class (id), \n\tFOREIGN KEY(teacher_id) REFERENCES teacher (id), \n\tFOREIGN KEY(subject_id) REFERENCES subject (id), \n\tFOREIGN KEY(module_id) REFERENCES module (id) ON DELETE SET NULL, \n\tFOREIGN KEY(created_by_membership_id) REFERENCES organization_membership (id) ON DELETE SET NULL\n)",
    "CREATE INDEX ix_operational_schedule_block_timeslot_id ON operational_schedule_block (timeslot_id)",
    "CREATE INDEX ix_operational_schedule_block_source_occurrence_id ON operational_schedule_block (source_occurrence_id)",
    "CREATE INDEX ix_operational_schedule_block_class_id ON operational_schedule_block (class_id)",
    "CREATE INDEX ix_operational_schedule_block_organization_id ON operational_schedule_block (organization_id)",
    "CREATE INDEX ix_operational_schedule_block_planned_active_schedule_block_id ON operational_schedule_block (planned_active_schedule_block_id)",
    "CREATE INDEX ix_operational_schedule_block_date ON operational_schedule_block (date)",
    "CREATE INDEX ix_operational_schedule_block_subject_id ON operational_schedule_block (subject_id)",
    "CREATE INDEX ix_operational_block_org_class_date ON operational_schedule_block (organization_id, class_id, date)",
    "CREATE INDEX ix_operational_block_org_teacher_date_slot ON operational_schedule_block (organization_id, teacher_id, date, timeslot_id)",
    "CREATE INDEX ix_operational_schedule_block_teacher_id ON operational_schedule_block (teacher_id)",
    "CREATE TABLE lesson_log (\n\tid SERIAL NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\toperational_block_id INTEGER, \n\tactive_schedule_block_id INTEGER, \n\tstatus lessonlogstatus NOT NULL, \n\tversion INTEGER NOT NULL, \n\tsummary TEXT, \n\tnotes TEXT, \n\tlogged_by_membership_id INTEGER, \n\tlogged_at TIMESTAMP WITH TIME ZONE, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_lesson_log_exactly_one_target CHECK ((CASE WHEN operational_block_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN active_schedule_block_id IS NOT NULL THEN 1 ELSE 0 END) = 1), \n\tCONSTRAINT uq_lesson_log_id_org_active_block UNIQUE (id, organization_id, active_schedule_block_id), \n\tCONSTRAINT uq_lesson_log_active_schedule_block UNIQUE (active_schedule_block_id), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE CASCADE, \n\tFOREIGN KEY(operational_block_id) REFERENCES operational_schedule_block (id) ON DELETE CASCADE, \n\tFOREIGN KEY(active_schedule_block_id) REFERENCES active_schedule_blocks (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(logged_by_membership_id) REFERENCES organization_membership (id) ON DELETE SET NULL\n)",
    "CREATE INDEX ix_lesson_log_organization_id ON lesson_log (organization_id)",
    "CREATE UNIQUE INDEX ix_lesson_log_operational_block_id ON lesson_log (operational_block_id)",
    "CREATE INDEX ix_lesson_log_active_schedule_block_id ON lesson_log (active_schedule_block_id)",
    "CREATE TABLE planned_recovery_links (\n\tid SERIAL NOT NULL, \n\torganization_id INTEGER NOT NULL, \n\tschool_year_id INTEGER NOT NULL, \n\tdebt_occurrence_id INTEGER NOT NULL, \n\tdebt_occurrence_revision INTEGER NOT NULL, \n\tplanned_active_block_id INTEGER, \n\tplanned_draft_block_id INTEGER, \n\tplanned_recovery_minutes INTEGER NOT NULL, \n\tdelivered_recovery_minutes INTEGER NOT NULL, \n\tdelivered_lesson_log_id INTEGER, \n\tdelivered_at TIMESTAMP WITH TIME ZONE, \n\tclass_id INTEGER NOT NULL, \n\tsubject_id INTEGER NOT NULL, \n\tteacher_id INTEGER, \n\tstatus plannedrecoverylinkstatus NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_planned_recovery_links_debt_scope FOREIGN KEY(debt_occurrence_id, organization_id, debt_occurrence_revision) REFERENCES lesson_occurrence (id, organization_id, revision) ON DELETE RESTRICT, \n\tCONSTRAINT fk_planned_recovery_links_active_block_scope FOREIGN KEY(planned_active_block_id, organization_id, school_year_id) REFERENCES active_schedule_blocks (id, organization_id, school_year_id) ON DELETE RESTRICT, \n\tCONSTRAINT fk_planned_recovery_links_draft_block_scope FOREIGN KEY(planned_draft_block_id, organization_id, school_year_id) REFERENCES schedule_draft_blocks (id, organization_id, school_year_id) ON DELETE RESTRICT, \n\tCONSTRAINT fk_planned_recovery_links_delivery_evidence FOREIGN KEY(delivered_lesson_log_id, organization_id, planned_active_block_id) REFERENCES lesson_log (id, organization_id, active_schedule_block_id) ON DELETE RESTRICT, \n\tCONSTRAINT uq_planned_recovery_links_active_block UNIQUE (planned_active_block_id), \n\tCONSTRAINT uq_planned_recovery_links_draft_block UNIQUE (planned_draft_block_id), \n\tCONSTRAINT uq_planned_recovery_links_delivery_log UNIQUE (delivered_lesson_log_id), \n\tCONSTRAINT ck_planned_recovery_links_planned_minutes_positive CHECK (planned_recovery_minutes > 0), \n\tCONSTRAINT ck_planned_recovery_links_delivered_minutes_range CHECK (delivered_recovery_minutes >= 0 AND delivered_recovery_minutes <= planned_recovery_minutes), \n\tCONSTRAINT ck_planned_recovery_links_has_target CHECK (planned_active_block_id IS NOT NULL OR planned_draft_block_id IS NOT NULL), \n\tCONSTRAINT ck_planned_recovery_links_delivery_evidence CHECK ((status = 'DELIVERED' AND planned_active_block_id IS NOT NULL AND delivered_recovery_minutes > 0 AND delivered_lesson_log_id IS NOT NULL AND delivered_at IS NOT NULL) OR (status <> 'DELIVERED' AND delivered_recovery_minutes = 0 AND delivered_lesson_log_id IS NULL AND delivered_at IS NULL)), \n\tCONSTRAINT ck_planned_recovery_links_debt_revision_positive CHECK (debt_occurrence_revision > 0), \n\tFOREIGN KEY(organization_id) REFERENCES organization (id) ON DELETE CASCADE, \n\tFOREIGN KEY(school_year_id) REFERENCES scheduler_school_year (id) ON DELETE CASCADE, \n\tFOREIGN KEY(class_id) REFERENCES class (id), \n\tFOREIGN KEY(subject_id) REFERENCES subject (id), \n\tFOREIGN KEY(teacher_id) REFERENCES teacher (id) ON DELETE SET NULL\n)",
    "CREATE INDEX ix_planned_recovery_links_school_year_id ON planned_recovery_links (school_year_id)",
    "CREATE INDEX ix_planned_recovery_links_organization_id ON planned_recovery_links (organization_id)",
    "ALTER TABLE lesson_occurrence ADD CONSTRAINT fk_lesson_occurrence_active_block_scope FOREIGN KEY(active_schedule_block_id, organization_id) REFERENCES active_schedule_blocks (id, organization_id) ON DELETE RESTRICT",
    "ALTER TABLE schedule_diff_entries ADD CONSTRAINT fk_schedule_diff_entries_before_active FOREIGN KEY(before_active_block_id) REFERENCES active_schedule_blocks (id) ON DELETE SET NULL",
    "ALTER TABLE schedule_draft_blocks ADD CONSTRAINT fk_schedule_draft_blocks_source_active FOREIGN KEY(source_active_block_id) REFERENCES active_schedule_blocks (id) ON DELETE RESTRICT",
    "ALTER TABLE teacher ADD CONSTRAINT fk_teacher_organization_membership FOREIGN KEY(organization_membership_id) REFERENCES organization_membership (id)",
    'ALTER TABLE "class_subject_link" ADD CONSTRAINT "uq_class_subject_link_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "availability" ADD CONSTRAINT "uq_availability_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "teacher" ADD CONSTRAINT "uq_teacher_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "organization_membership" ADD CONSTRAINT "uq_organization_membership_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "member_access_operation" ADD CONSTRAINT "uq_member_access_operation_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "class" ADD CONSTRAINT "uq_class_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "room" ADD CONSTRAINT "uq_room_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "subject" ADD CONSTRAINT "uq_subject_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "timeslot" ADD CONSTRAINT "uq_timeslot_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "constraint" ADD CONSTRAINT "uq_constraint_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "organization_settings" ADD CONSTRAINT "uq_organization_settings_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "scheduler_school_year" ADD CONSTRAINT "uq_scheduler_school_year_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "scheduler_school_year_state" ADD CONSTRAINT "uq_scheduler_school_year_state_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "schedule_generation_job" ADD CONSTRAINT "uq_schedule_generation_job_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "schedule_drafts" ADD CONSTRAINT "uq_schedule_drafts_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "schedule_draft_blocks" ADD CONSTRAINT "uq_schedule_draft_blocks_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "schedule_diff_entries" ADD CONSTRAINT "uq_schedule_diff_entries_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "active_schedule_blocks" ADD CONSTRAINT "uq_active_schedule_blocks_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "planned_recovery_links" ADD CONSTRAINT "uq_planned_recovery_links_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "scheduler_state_version_events" ADD CONSTRAINT "uq_scheduler_state_version_events_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "organization_grid_settings" ADD CONSTRAINT "uq_organization_grid_settings_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "school_calendar_event" ADD CONSTRAINT "uq_school_calendar_event_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "lesson_occurrence" ADD CONSTRAINT "uq_lesson_occurrence_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "occurrence_operational_event" ADD CONSTRAINT "uq_occurrence_operational_event_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "operational_schedule_block" ADD CONSTRAINT "uq_operational_schedule_block_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "teacher_endpoint_operational_event" ADD CONSTRAINT "uq_teacher_endpoint_operational_event_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "lesson_log" ADD CONSTRAINT "uq_lesson_log_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "teacher_weekly_timesheet" ADD CONSTRAINT "uq_teacher_weekly_timesheet_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "course" ADD CONSTRAINT "uq_course_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "module" ADD CONSTRAINT "uq_module_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "progress_ledger_entry" ADD CONSTRAINT "uq_progress_ledger_entry_org_id" UNIQUE (organization_id, id)',
    'ALTER TABLE "course_subject_link" ADD CONSTRAINT "fk_course_subject_link_subject_id_org" FOREIGN KEY (organization_id, "subject_id") REFERENCES "subject" (organization_id, "id")',
    'ALTER TABLE "course_subject_link" ADD CONSTRAINT "fk_course_subject_link_course_id_org" FOREIGN KEY (organization_id, "course_id") REFERENCES "course" (organization_id, "id")',
    'ALTER TABLE "teacher_subject_link" ADD CONSTRAINT "fk_teacher_subject_link_teacher_id_org" FOREIGN KEY (organization_id, "teacher_id") REFERENCES "teacher" (organization_id, "id")',
    'ALTER TABLE "teacher_subject_link" ADD CONSTRAINT "fk_teacher_subject_link_subject_id_org" FOREIGN KEY (organization_id, "subject_id") REFERENCES "subject" (organization_id, "id")',
    'ALTER TABLE "class_subject_link" ADD CONSTRAINT "fk_class_subject_link_teacher_id_org" FOREIGN KEY (organization_id, "teacher_id") REFERENCES "teacher" (organization_id, "id")',
    'ALTER TABLE "class_subject_link" ADD CONSTRAINT "fk_class_subject_link_subject_id_org" FOREIGN KEY (organization_id, "subject_id") REFERENCES "subject" (organization_id, "id")',
    'ALTER TABLE "class_subject_link" ADD CONSTRAINT "fk_class_subject_link_class_id_org" FOREIGN KEY (organization_id, "class_id") REFERENCES "class" (organization_id, "id")',
    'ALTER TABLE "availability" ADD CONSTRAINT "fk_availability_timeslot_id_org" FOREIGN KEY (organization_id, "timeslot_id") REFERENCES "timeslot" (organization_id, "id")',
    'ALTER TABLE "availability" ADD CONSTRAINT "fk_availability_teacher_id_org" FOREIGN KEY (organization_id, "teacher_id") REFERENCES "teacher" (organization_id, "id")',
    'ALTER TABLE "teacher" ADD CONSTRAINT "fk_teacher_organization_membership_id_org" FOREIGN KEY (organization_id, "organization_membership_id") REFERENCES "organization_membership" (organization_id, "id")',
    'ALTER TABLE "member_access_operation" ADD CONSTRAINT "fk_member_access_operation_membership_id_org" FOREIGN KEY (organization_id, "membership_id") REFERENCES "organization_membership" (organization_id, "id")',
    'ALTER TABLE "class" ADD CONSTRAINT "fk_class_course_id_org" FOREIGN KEY (organization_id, "course_id") REFERENCES "course" (organization_id, "id")',
    'ALTER TABLE "constraint" ADD CONSTRAINT "fk_constraint_timeslot_id_org" FOREIGN KEY (organization_id, "timeslot_id") REFERENCES "timeslot" (organization_id, "id")',
    'ALTER TABLE "constraint" ADD CONSTRAINT "fk_constraint_teacher_id_org" FOREIGN KEY (organization_id, "teacher_id") REFERENCES "teacher" (organization_id, "id")',
    'ALTER TABLE "constraint" ADD CONSTRAINT "fk_constraint_subject_id_org" FOREIGN KEY (organization_id, "subject_id") REFERENCES "subject" (organization_id, "id")',
    'ALTER TABLE "constraint" ADD CONSTRAINT "fk_constraint_class_id_org" FOREIGN KEY (organization_id, "class_id") REFERENCES "class" (organization_id, "id")',
    'ALTER TABLE "constraint" ADD CONSTRAINT "fk_constraint_room_id_org" FOREIGN KEY (organization_id, "room_id") REFERENCES "room" (organization_id, "id")',
    'ALTER TABLE "schedule_drafts" ADD CONSTRAINT "fk_schedule_drafts_school_year_id_org" FOREIGN KEY (organization_id, "school_year_id") REFERENCES "scheduler_school_year" (organization_id, "id")',
    'ALTER TABLE "schedule_draft_blocks" ADD CONSTRAINT "fk_schedule_draft_blocks_timeslot_id_org" FOREIGN KEY (organization_id, "timeslot_id") REFERENCES "timeslot" (organization_id, "id")',
    'ALTER TABLE "schedule_draft_blocks" ADD CONSTRAINT "fk_schedule_draft_blocks_teacher_id_org" FOREIGN KEY (organization_id, "teacher_id") REFERENCES "teacher" (organization_id, "id")',
    'ALTER TABLE "schedule_draft_blocks" ADD CONSTRAINT "fk_schedule_draft_blocks_source_active_block_id_org" FOREIGN KEY (organization_id, "source_active_block_id") REFERENCES "active_schedule_blocks" (organization_id, "id")',
    'ALTER TABLE "schedule_draft_blocks" ADD CONSTRAINT "fk_schedule_draft_blocks_school_year_id_org" FOREIGN KEY (organization_id, "school_year_id") REFERENCES "scheduler_school_year" (organization_id, "id")',
    'ALTER TABLE "schedule_draft_blocks" ADD CONSTRAINT "fk_schedule_draft_blocks_class_id_org" FOREIGN KEY (organization_id, "class_id") REFERENCES "class" (organization_id, "id")',
    'ALTER TABLE "schedule_draft_blocks" ADD CONSTRAINT "fk_schedule_draft_blocks_room_id_org" FOREIGN KEY (organization_id, "room_id") REFERENCES "room" (organization_id, "id")',
    'ALTER TABLE "schedule_draft_blocks" ADD CONSTRAINT "fk_schedule_draft_blocks_recovery_source_occurrence_id_org" FOREIGN KEY (organization_id, "recovery_source_occurrence_id") REFERENCES "lesson_occurrence" (organization_id, "id")',
    'ALTER TABLE "schedule_draft_blocks" ADD CONSTRAINT "fk_schedule_draft_blocks_subject_id_org" FOREIGN KEY (organization_id, "subject_id") REFERENCES "subject" (organization_id, "id")',
    'ALTER TABLE "schedule_diff_entries" ADD CONSTRAINT "fk_schedule_diff_entries_before_active_block_id_org" FOREIGN KEY (organization_id, "before_active_block_id") REFERENCES "active_schedule_blocks" (organization_id, "id")',
    'ALTER TABLE "schedule_diff_entries" ADD CONSTRAINT "fk_schedule_diff_entries_class_id_org" FOREIGN KEY (organization_id, "class_id") REFERENCES "class" (organization_id, "id")',
    'ALTER TABLE "schedule_diff_entries" ADD CONSTRAINT "fk_schedule_diff_entries_subject_id_org" FOREIGN KEY (organization_id, "subject_id") REFERENCES "subject" (organization_id, "id")',
    'ALTER TABLE "schedule_diff_entries" ADD CONSTRAINT "fk_schedule_diff_entries_after_room_id_org" FOREIGN KEY (organization_id, "after_room_id") REFERENCES "room" (organization_id, "id")',
    'ALTER TABLE "schedule_diff_entries" ADD CONSTRAINT "fk_schedule_diff_entries_school_year_id_org" FOREIGN KEY (organization_id, "school_year_id") REFERENCES "scheduler_school_year" (organization_id, "id")',
    'ALTER TABLE "schedule_diff_entries" ADD CONSTRAINT "fk_schedule_diff_entries_before_room_id_org" FOREIGN KEY (organization_id, "before_room_id") REFERENCES "room" (organization_id, "id")',
    'ALTER TABLE "schedule_diff_entries" ADD CONSTRAINT "fk_schedule_diff_entries_after_draft_block_id_org" FOREIGN KEY (organization_id, "after_draft_block_id") REFERENCES "schedule_draft_blocks" (organization_id, "id")',
    'ALTER TABLE "schedule_diff_entries" ADD CONSTRAINT "fk_schedule_diff_entries_teacher_id_org" FOREIGN KEY (organization_id, "teacher_id") REFERENCES "teacher" (organization_id, "id")',
    'ALTER TABLE "schedule_diff_entries" ADD CONSTRAINT "fk_schedule_diff_entries_after_timeslot_id_org" FOREIGN KEY (organization_id, "after_timeslot_id") REFERENCES "timeslot" (organization_id, "id")',
    'ALTER TABLE "schedule_diff_entries" ADD CONSTRAINT "fk_schedule_diff_entries_before_timeslot_id_org" FOREIGN KEY (organization_id, "before_timeslot_id") REFERENCES "timeslot" (organization_id, "id")',
    'ALTER TABLE "active_schedule_blocks" ADD CONSTRAINT "fk_active_schedule_blocks_timeslot_id_org" FOREIGN KEY (organization_id, "timeslot_id") REFERENCES "timeslot" (organization_id, "id")',
    'ALTER TABLE "active_schedule_blocks" ADD CONSTRAINT "fk_active_schedule_blocks_teacher_id_org" FOREIGN KEY (organization_id, "teacher_id") REFERENCES "teacher" (organization_id, "id")',
    'ALTER TABLE "active_schedule_blocks" ADD CONSTRAINT "fk_active_schedule_blocks_school_year_id_org" FOREIGN KEY (organization_id, "school_year_id") REFERENCES "scheduler_school_year" (organization_id, "id")',
    'ALTER TABLE "active_schedule_blocks" ADD CONSTRAINT "fk_active_schedule_blocks_room_id_org" FOREIGN KEY (organization_id, "room_id") REFERENCES "room" (organization_id, "id")',
    'ALTER TABLE "active_schedule_blocks" ADD CONSTRAINT "fk_active_schedule_blocks_subject_id_org" FOREIGN KEY (organization_id, "subject_id") REFERENCES "subject" (organization_id, "id")',
    'ALTER TABLE "active_schedule_blocks" ADD CONSTRAINT "fk_active_schedule_blocks_class_id_org" FOREIGN KEY (organization_id, "class_id") REFERENCES "class" (organization_id, "id")',
    'ALTER TABLE "planned_recovery_links" ADD CONSTRAINT "fk_planned_recovery_links_school_year_id_org" FOREIGN KEY (organization_id, "school_year_id") REFERENCES "scheduler_school_year" (organization_id, "id")',
    'ALTER TABLE "planned_recovery_links" ADD CONSTRAINT "fk_planned_recovery_links_teacher_id_org" FOREIGN KEY (organization_id, "teacher_id") REFERENCES "teacher" (organization_id, "id")',
    'ALTER TABLE "planned_recovery_links" ADD CONSTRAINT "fk_planned_recovery_links_subject_id_org" FOREIGN KEY (organization_id, "subject_id") REFERENCES "subject" (organization_id, "id")',
    'ALTER TABLE "planned_recovery_links" ADD CONSTRAINT "fk_planned_recovery_links_class_id_org" FOREIGN KEY (organization_id, "class_id") REFERENCES "class" (organization_id, "id")',
    'ALTER TABLE "lesson_occurrence" ADD CONSTRAINT "fk_lesson_occurrence_class_id_org" FOREIGN KEY (organization_id, "class_id") REFERENCES "class" (organization_id, "id")',
    'ALTER TABLE "lesson_occurrence" ADD CONSTRAINT "fk_lesson_occurrence_subject_id_org" FOREIGN KEY (organization_id, "subject_id") REFERENCES "subject" (organization_id, "id")',
    'ALTER TABLE "lesson_occurrence" ADD CONSTRAINT "fk_lesson_occurrence_substitute_teacher_id_org" FOREIGN KEY (organization_id, "substitute_teacher_id") REFERENCES "teacher" (organization_id, "id")',
    'ALTER TABLE "lesson_occurrence" ADD CONSTRAINT "fk_lesson_occurrence_planned_timeslot_id_org" FOREIGN KEY (organization_id, "planned_timeslot_id") REFERENCES "timeslot" (organization_id, "id")',
    'ALTER TABLE "lesson_occurrence" ADD CONSTRAINT "fk_lesson_occurrence_planned_room_id_org" FOREIGN KEY (organization_id, "planned_room_id") REFERENCES "room" (organization_id, "id")',
    'ALTER TABLE "lesson_occurrence" ADD CONSTRAINT "fk_lesson_occurrence_planned_teacher_id_org" FOREIGN KEY (organization_id, "planned_teacher_id") REFERENCES "teacher" (organization_id, "id")',
    'ALTER TABLE "lesson_occurrence" ADD CONSTRAINT "fk_lesson_occurrence_planned_module_id_org" FOREIGN KEY (organization_id, "planned_module_id") REFERENCES "module" (organization_id, "id")',
    'ALTER TABLE "lesson_occurrence" ADD CONSTRAINT "fk_lesson_occurrence_executed_module_id_org" FOREIGN KEY (organization_id, "executed_module_id") REFERENCES "module" (organization_id, "id")',
    'ALTER TABLE "lesson_occurrence" ADD CONSTRAINT "fk_lesson_occurrence_executed_teacher_id_org" FOREIGN KEY (organization_id, "executed_teacher_id") REFERENCES "teacher" (organization_id, "id")',
    'ALTER TABLE "lesson_occurrence" ADD CONSTRAINT "fk_lesson_occurrence_substitute_subject_id_org" FOREIGN KEY (organization_id, "substitute_subject_id") REFERENCES "subject" (organization_id, "id")',
    'ALTER TABLE "occurrence_operational_event" ADD CONSTRAINT "fk_occurrence_operational_event_active_schedule_block_id_org" FOREIGN KEY (organization_id, "active_schedule_block_id") REFERENCES "active_schedule_blocks" (organization_id, "id")',
    'ALTER TABLE "occurrence_operational_event" ADD CONSTRAINT "fk_occurrence_operational_event_occurrence_id_org" FOREIGN KEY (organization_id, "occurrence_id") REFERENCES "lesson_occurrence" (organization_id, "id")',
    'ALTER TABLE "operational_schedule_block" ADD CONSTRAINT "fk_operational_schedule_block_module_id_org" FOREIGN KEY (organization_id, "module_id") REFERENCES "module" (organization_id, "id")',
    'ALTER TABLE "operational_schedule_block" ADD CONSTRAINT "fk_operational_schedule_block_source_occurrence_id_org" FOREIGN KEY (organization_id, "source_occurrence_id") REFERENCES "lesson_occurrence" (organization_id, "id")',
    'ALTER TABLE "operational_schedule_block" ADD CONSTRAINT "fk_operational_schedule_block_timeslot_id_org" FOREIGN KEY (organization_id, "timeslot_id") REFERENCES "timeslot" (organization_id, "id")',
    'ALTER TABLE "operational_schedule_block" ADD CONSTRAINT "fk_operational_schedule_block_subject_id_org" FOREIGN KEY (organization_id, "subject_id") REFERENCES "subject" (organization_id, "id")',
    'ALTER TABLE "operational_schedule_block" ADD CONSTRAINT "fk_operational_schedule_block_room_id_org" FOREIGN KEY (organization_id, "room_id") REFERENCES "room" (organization_id, "id")',
    'ALTER TABLE "operational_schedule_block" ADD CONSTRAINT "fk_operational_schedule_block_teacher_id_org" FOREIGN KEY (organization_id, "teacher_id") REFERENCES "teacher" (organization_id, "id")',
    'ALTER TABLE "operational_schedule_block" ADD CONSTRAINT "fk_operational_block_planned_active_org" FOREIGN KEY (organization_id, "planned_active_schedule_block_id") REFERENCES "active_schedule_blocks" (organization_id, "id")',
    'ALTER TABLE "operational_schedule_block" ADD CONSTRAINT "fk_operational_schedule_block_class_id_org" FOREIGN KEY (organization_id, "class_id") REFERENCES "class" (organization_id, "id")',
    'ALTER TABLE "lesson_log" ADD CONSTRAINT "fk_lesson_log_active_schedule_block_id_org" FOREIGN KEY (organization_id, "active_schedule_block_id") REFERENCES "active_schedule_blocks" (organization_id, "id")',
    'ALTER TABLE "lesson_log" ADD CONSTRAINT "fk_lesson_log_operational_block_id_org" FOREIGN KEY (organization_id, "operational_block_id") REFERENCES "operational_schedule_block" (organization_id, "id")',
    'ALTER TABLE "teacher_weekly_timesheet" ADD CONSTRAINT "fk_teacher_weekly_timesheet_teacher_id_org" FOREIGN KEY (organization_id, "teacher_id") REFERENCES "teacher" (organization_id, "id")',
    'ALTER TABLE "module" ADD CONSTRAINT "fk_module_subject_id_org" FOREIGN KEY (organization_id, "subject_id") REFERENCES "subject" (organization_id, "id")',
    'ALTER TABLE "progress_ledger_entry" ADD CONSTRAINT "fk_progress_ledger_entry_module_id_org" FOREIGN KEY (organization_id, "module_id") REFERENCES "module" (organization_id, "id")',
    'ALTER TABLE "progress_ledger_entry" ADD CONSTRAINT "fk_progress_ledger_entry_class_id_org" FOREIGN KEY (organization_id, "class_id") REFERENCES "class" (organization_id, "id")',
    'ALTER TABLE "progress_ledger_entry" ADD CONSTRAINT "fk_progress_ledger_entry_reverses_ledger_entry_id_org" FOREIGN KEY (organization_id, "reverses_ledger_entry_id") REFERENCES "progress_ledger_entry" (organization_id, "id")',
    'ALTER TABLE "organization_membership" ADD CONSTRAINT "fk_organization_membership_created_by_membership_id_org" FOREIGN KEY (organization_id, "created_by_membership_id") REFERENCES "organization_membership" (organization_id, "id")',
    'ALTER TABLE "organization_membership" ADD CONSTRAINT "fk_organization_membership_updated_by_membership_id_org" FOREIGN KEY (organization_id, "updated_by_membership_id") REFERENCES "organization_membership" (organization_id, "id")',
    'ALTER TABLE "member_access_operation" ADD CONSTRAINT "fk_member_access_operation_created_by_membership_id_org" FOREIGN KEY (organization_id, "created_by_membership_id") REFERENCES "organization_membership" (organization_id, "id")',
    'ALTER TABLE "scheduler_school_year_state" ADD CONSTRAINT "fk_scheduler_school_year_state_reset_by_membership_id_org" FOREIGN KEY (organization_id, "reset_by_membership_id") REFERENCES "organization_membership" (organization_id, "id")',
    'ALTER TABLE "schedule_generation_job" ADD CONSTRAINT "fk_schedule_generation_job_requested_by_membership_id_org" FOREIGN KEY (organization_id, "requested_by_membership_id") REFERENCES "organization_membership" (organization_id, "id")',
    'ALTER TABLE "schedule_drafts" ADD CONSTRAINT "fk_schedule_drafts_created_by_membership_id_org" FOREIGN KEY (organization_id, "created_by_membership_id") REFERENCES "organization_membership" (organization_id, "id")',
    'ALTER TABLE "schedule_drafts" ADD CONSTRAINT "fk_schedule_drafts_decided_by_membership_id_org" FOREIGN KEY (organization_id, "decided_by_membership_id") REFERENCES "organization_membership" (organization_id, "id")',
    'ALTER TABLE "scheduler_state_version_events" ADD CONSTRAINT "fk_scheduler_state_version_events_changed_by_membership_id_org" FOREIGN KEY (organization_id, "changed_by_membership_id") REFERENCES "organization_membership" (organization_id, "id")',
    'ALTER TABLE "lesson_occurrence" ADD CONSTRAINT "fk_lesson_occurrence_created_by_membership_id_org" FOREIGN KEY (organization_id, "created_by_membership_id") REFERENCES "organization_membership" (organization_id, "id")',
    'ALTER TABLE "lesson_occurrence" ADD CONSTRAINT "fk_lesson_occurrence_revoked_by_membership_id_org" FOREIGN KEY (organization_id, "revoked_by_membership_id") REFERENCES "organization_membership" (organization_id, "id")',
    'ALTER TABLE "lesson_occurrence" ADD CONSTRAINT "fk_lesson_occurrence_decided_by_membership_id_org" FOREIGN KEY (organization_id, "decided_by_membership_id") REFERENCES "organization_membership" (organization_id, "id")',
    'ALTER TABLE "occurrence_operational_event" ADD CONSTRAINT "fk_occurrence_operational_event_actor_membership_id_org" FOREIGN KEY (organization_id, "actor_membership_id") REFERENCES "organization_membership" (organization_id, "id")',
    'ALTER TABLE "operational_schedule_block" ADD CONSTRAINT "fk_operational_schedule_block_created_by_membership_id_org" FOREIGN KEY (organization_id, "created_by_membership_id") REFERENCES "organization_membership" (organization_id, "id")',
    'ALTER TABLE "teacher_endpoint_operational_event" ADD CONSTRAINT "fk_teacher_endpoint_operational_event_actor_membership_id_org" FOREIGN KEY (organization_id, "actor_membership_id") REFERENCES "organization_membership" (organization_id, "id")',
    'ALTER TABLE "lesson_log" ADD CONSTRAINT "fk_lesson_log_logged_by_membership_id_org" FOREIGN KEY (organization_id, "logged_by_membership_id") REFERENCES "organization_membership" (organization_id, "id")',
    'ALTER TABLE "teacher_weekly_timesheet" ADD CONSTRAINT "fk_teacher_weekly_timesheet_approved_by_membership_id_org" FOREIGN KEY (organization_id, "approved_by_membership_id") REFERENCES "organization_membership" (organization_id, "id")',
    'ALTER TABLE "progress_ledger_entry" ADD CONSTRAINT "fk_progress_ledger_entry_created_by_membership_id_org" FOREIGN KEY (organization_id, "created_by_membership_id") REFERENCES "organization_membership" (organization_id, "id")',
    "CREATE SCHEMA app_security AUTHORIZATION cronos_auth_definer",
    "CREATE FUNCTION app_security.current_organization_id() RETURNS integer\nLANGUAGE sql STABLE\nAS $$\n  SELECT CASE\n    WHEN current_setting('app.current_organization_id', true) ~ '^[1-9][0-9]{0,9}$'\n     AND current_setting('app.current_organization_id', true)::numeric <= 2147483647\n    THEN current_setting('app.current_organization_id', true)::integer\n    ELSE NULL\n  END\n$$",
    "CREATE FUNCTION app_security.resolve_principal(\n  requested_clerk_user_id text,\n  requested_clerk_org_id text\n) RETURNS TABLE (\n  account_id integer,\n  clerk_user_id text,\n  organization_id integer,\n  membership_id integer,\n  can_admin boolean,\n  can_teach boolean,\n  teacher_id integer\n)\nLANGUAGE sql STABLE SECURITY DEFINER\nSET search_path = pg_catalog, public\nAS $$\n  SELECT u.id, u.clerk_user_id, m.organization_id, m.id,\n         m.can_admin, m.can_teach, t.id\n  FROM public.\"user\" AS u\n  JOIN public.organization_membership AS m ON m.account_id = u.id\n  JOIN public.organization AS o ON o.id = m.organization_id\n  LEFT JOIN public.teacher AS t ON t.organization_membership_id = m.id\n  WHERE u.clerk_user_id = requested_clerk_user_id\n    AND o.clerk_org_id = requested_clerk_org_id\n    AND m.lifecycle_status = 'active'\n    AND m.access_status = 'active'\n  LIMIT 1\n$$",
    "ALTER FUNCTION app_security.resolve_principal(text, text) OWNER TO cronos_auth_definer",
    """CREATE FUNCTION app_security.bootstrap_founder(
  requested_clerk_user_id text,
  requested_clerk_org_id text,
  requested_organization_name text,
  requested_email text,
  requested_profile_name text,
  requested_membership_id text
) RETURNS TABLE (account_id integer, organization_id integer, membership_id integer)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_organization_id integer;
  v_account_id integer;
  v_membership_id integer;
  v_email text := lower(coalesce(nullif(trim(requested_email), ''),
                                 requested_clerk_user_id || '@clerk.local'));
BEGIN
  PERFORM pg_advisory_xact_lock(hashtext(requested_clerk_org_id));
  INSERT INTO public.organization (name, clerk_org_id, plan_status)
  VALUES (requested_organization_name, requested_clerk_org_id, 'active')
  ON CONFLICT (clerk_org_id) DO UPDATE
    SET name = EXCLUDED.name, plan_status = 'active'
  RETURNING id INTO v_organization_id;

  SELECT u.id INTO v_account_id
  FROM public."user" u
  WHERE u.clerk_user_id = requested_clerk_user_id OR lower(u.email) = v_email
  ORDER BY (u.clerk_user_id = requested_clerk_user_id) DESC
  LIMIT 1;

  IF v_account_id IS NULL THEN
    INSERT INTO public."user" (
      name, email, clerk_user_id, clerk_profile_name,
      last_clerk_sync_at, created_at, updated_at
    ) VALUES (
      requested_profile_name, v_email, requested_clerk_user_id,
      requested_profile_name, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
    ) RETURNING id INTO v_account_id;
  ELSE
    UPDATE public."user" SET
      clerk_user_id = requested_clerk_user_id,
      name = coalesce(requested_profile_name, name),
      clerk_profile_name = requested_profile_name,
      last_clerk_sync_at = CURRENT_TIMESTAMP,
      updated_at = CURRENT_TIMESTAMP
    WHERE id = v_account_id;
  END IF;

  SELECT m.id INTO v_membership_id
  FROM public.organization_membership m
  WHERE m.organization_id = v_organization_id AND m.account_id = v_account_id;

  IF v_membership_id IS NULL AND EXISTS (
    SELECT 1 FROM public.organization_membership existing
    WHERE existing.organization_id = v_organization_id
  ) THEN
    RETURN;
  END IF;

  IF v_membership_id IS NULL THEN
    INSERT INTO public.organization_membership (
      organization_id, account_id, organization_display_name,
      lifecycle_status, access_status, can_admin, can_teach,
      clerk_membership_id, created_by_membership_id, updated_by_membership_id,
      lock_version, created_at, updated_at
    ) VALUES (
      v_organization_id, v_account_id, requested_organization_name,
      'active', 'active', TRUE, FALSE,
      requested_membership_id, v_account_id, v_account_id,
      1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
    ) RETURNING id INTO v_membership_id;
  ELSE
    UPDATE public.organization_membership SET
      lifecycle_status = 'active', access_status = 'active',
      can_admin = TRUE,
      clerk_membership_id = coalesce(requested_membership_id, clerk_membership_id),
      access_error_category = NULL, access_error_safe_message = NULL,
      updated_at = CURRENT_TIMESTAMP
    WHERE id = v_membership_id;
  END IF;

  RETURN QUERY SELECT v_account_id, v_organization_id, v_membership_id;
END
$$""",
    "ALTER FUNCTION app_security.bootstrap_founder(text, text, text, text, text, text) OWNER TO cronos_auth_definer",
    """CREATE FUNCTION app_security.ensure_organization(requested_clerk_org_id text, requested_name text)
RETURNS TABLE (id integer)
LANGUAGE sql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  INSERT INTO public.organization (name, clerk_org_id, plan_status)
  VALUES (requested_name, requested_clerk_org_id, 'active')
  ON CONFLICT (clerk_org_id) DO UPDATE
    SET name = EXCLUDED.name, plan_status = 'active'
  RETURNING organization.id
$$""",
    "ALTER FUNCTION app_security.ensure_organization(text, text) OWNER TO cronos_auth_definer",
    """CREATE FUNCTION app_security.ensure_pending_account(
  requested_organization_id integer, requested_email text, requested_name text
) RETURNS TABLE (id integer)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE v_account_id integer;
BEGIN
  IF current_setting('app.current_organization_id', true)
       IS DISTINCT FROM requested_organization_id::text THEN
    RAISE insufficient_privilege USING MESSAGE = 'Tenant context mismatch';
  END IF;
  SELECT u.id INTO v_account_id
  FROM public."user" u
  WHERE lower(u.email) = lower(requested_email)
  LIMIT 1;
  IF v_account_id IS NULL THEN
    INSERT INTO public."user" (email, name, created_at, updated_at)
    VALUES (
      lower(requested_email), requested_name,
      CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
    )
    RETURNING public."user".id INTO v_account_id;
  END IF;
  RETURN QUERY SELECT v_account_id;
END
$$""",
    "ALTER FUNCTION app_security.ensure_pending_account(integer, text, text) OWNER TO cronos_auth_definer",
    """CREATE FUNCTION app_security.update_pending_account_email(
  requested_organization_id integer, requested_account_id integer,
  requested_email text
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  IF current_setting('app.current_organization_id', true)
       IS DISTINCT FROM requested_organization_id::text THEN
    RAISE insufficient_privilege USING MESSAGE = 'Tenant context mismatch';
  END IF;
  UPDATE public."user" u
  SET email = lower(requested_email), updated_at = CURRENT_TIMESTAMP
  WHERE u.id = requested_account_id
    AND EXISTS (
      SELECT 1 FROM public.organization_membership m
      WHERE m.organization_id = requested_organization_id
        AND m.account_id = u.id AND m.access_status <> 'active'
    );
  RETURN FOUND;
END
$$""",
    "ALTER FUNCTION app_security.update_pending_account_email(integer, integer, text) OWNER TO cronos_auth_definer",
    """CREATE FUNCTION app_security.ensure_user(
  requested_clerk_user_id text, requested_email text, requested_name text,
  requested_role text, requested_organization_id integer, requested_teacher_id integer
) RETURNS TABLE (id integer, organization_id integer)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_account_id integer;
  v_membership_id integer;
BEGIN
  SELECT u.id, m.id INTO v_account_id, v_membership_id
  FROM public."user" u
  JOIN public.organization_membership m ON m.account_id = u.id
  WHERE m.organization_id = requested_organization_id
    AND (u.clerk_user_id = requested_clerk_user_id
         OR (u.clerk_user_id IS NULL AND lower(u.email) = lower(requested_email)))
  LIMIT 1;
  IF v_account_id IS NULL THEN RETURN; END IF;
  UPDATE public."user" SET clerk_user_id = requested_clerk_user_id,
    email = coalesce(nullif(lower(requested_email), ''), email),
    name = coalesce(requested_name, name), clerk_profile_name = requested_name,
    last_clerk_sync_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
  WHERE public."user".id = v_account_id;
  UPDATE public.organization_membership SET lifecycle_status = 'active',
    access_status = 'active', updated_at = CURRENT_TIMESTAMP
  WHERE public.organization_membership.id = v_membership_id;
  RETURN QUERY SELECT v_account_id, requested_organization_id;
END
$$""",
    "ALTER FUNCTION app_security.ensure_user(text, text, text, text, integer, integer) OWNER TO cronos_auth_definer",
    """CREATE FUNCTION app_security.update_user_profile(
  requested_clerk_user_id text, requested_email text, requested_name text,
  requested_role text, requested_teacher_id integer
) RETURNS TABLE (id integer, organization_id integer)
LANGUAGE sql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  WITH updated AS (
    UPDATE public."user" SET
      email = coalesce(nullif(lower(requested_email), ''), email),
      name = coalesce(requested_name, name), clerk_profile_name = requested_name,
      last_clerk_sync_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
    WHERE clerk_user_id = requested_clerk_user_id
    RETURNING public."user".id
  )
  SELECT updated.id, min(m.organization_id) FROM updated
  JOIN public.organization_membership m ON m.account_id = updated.id
  GROUP BY updated.id
$$""",
    "ALTER FUNCTION app_security.update_user_profile(text, text, text, text, integer) OWNER TO cronos_auth_definer",
    """CREATE FUNCTION app_security.deactivate_user(requested_clerk_user_id text)
RETURNS boolean
LANGUAGE sql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  WITH account AS (
    SELECT id FROM public."user" WHERE clerk_user_id = requested_clerk_user_id
  ), changed AS (
    UPDATE public.organization_membership m
    SET lifecycle_status = 'archived', access_status = 'none', updated_at = CURRENT_TIMESTAMP
    FROM account a
    WHERE m.account_id = a.id
      AND NOT (m.can_admin AND NOT EXISTS (
        SELECT 1 FROM public.organization_membership other
        WHERE other.organization_id = m.organization_id
          AND other.id <> m.id AND other.can_admin
          AND other.lifecycle_status = 'active' AND other.access_status = 'active'
      ))
    RETURNING m.id
  ) SELECT EXISTS (SELECT 1 FROM changed)
$$""",
    "ALTER FUNCTION app_security.deactivate_user(text) OWNER TO cronos_auth_definer",
    """CREATE FUNCTION app_security.deactivate_organization(requested_clerk_org_id text)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE v_organization_id integer;
BEGIN
  UPDATE public.organization SET plan_status = 'inactive'
  WHERE clerk_org_id = requested_clerk_org_id RETURNING id INTO v_organization_id;
  IF v_organization_id IS NULL THEN RETURN FALSE; END IF;
  UPDATE public.organization_membership
  SET lifecycle_status = 'archived', access_status = 'none', updated_at = CURRENT_TIMESTAMP
  WHERE organization_id = v_organization_id;
  RETURN TRUE;
END
$$""",
    "ALTER FUNCTION app_security.deactivate_organization(text) OWNER TO cronos_auth_definer",
    "REVOKE ALL ON SCHEMA app_security FROM PUBLIC",
    "REVOKE ALL ON ALL FUNCTIONS IN SCHEMA app_security FROM PUBLIC",
    "GRANT USAGE ON SCHEMA app_security TO cronos_app",
    "GRANT EXECUTE ON FUNCTION app_security.resolve_principal(text, text) TO cronos_app",
    "GRANT EXECUTE ON FUNCTION app_security.bootstrap_founder(text, text, text, text, text, text) TO cronos_app",
    "GRANT EXECUTE ON FUNCTION app_security.ensure_organization(text, text) TO cronos_app",
    "GRANT EXECUTE ON FUNCTION app_security.ensure_pending_account(integer, text, text) TO cronos_app",
    "GRANT EXECUTE ON FUNCTION app_security.update_pending_account_email(integer, integer, text) TO cronos_app",
    "GRANT EXECUTE ON FUNCTION app_security.ensure_user(text, text, text, text, integer, integer) TO cronos_app",
    "GRANT EXECUTE ON FUNCTION app_security.update_user_profile(text, text, text, text, integer) TO cronos_app",
    "GRANT EXECUTE ON FUNCTION app_security.deactivate_user(text) TO cronos_app",
    "GRANT EXECUTE ON FUNCTION app_security.deactivate_organization(text) TO cronos_app",
    "GRANT EXECUTE ON FUNCTION app_security.current_organization_id() TO cronos_app",
    'ALTER TABLE "active_schedule_blocks" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "active_schedule_blocks" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "active_schedule_blocks" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "availability" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "availability" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "availability" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "class" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "class" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "class" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "class_subject_link" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "class_subject_link" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "class_subject_link" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "constraint" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "constraint" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "constraint" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "course" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "course" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "course" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "course_subject_link" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "course_subject_link" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "course_subject_link" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "lesson_log" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "lesson_log" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "lesson_log" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "lesson_occurrence" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "lesson_occurrence" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "lesson_occurrence" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "member_access_operation" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "member_access_operation" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "member_access_operation" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "module" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "module" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "module" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "occurrence_operational_event" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "occurrence_operational_event" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "occurrence_operational_event" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "operational_schedule_block" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "operational_schedule_block" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "operational_schedule_block" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "organization_grid_settings" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "organization_grid_settings" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "organization_grid_settings" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "organization_membership" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "organization_membership" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "organization_membership" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "organization_settings" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "organization_settings" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "organization_settings" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "planned_recovery_links" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "planned_recovery_links" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "planned_recovery_links" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "progress_ledger_entry" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "progress_ledger_entry" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "progress_ledger_entry" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "room" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "room" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "room" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "schedule_diff_entries" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "schedule_diff_entries" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "schedule_diff_entries" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "schedule_draft_blocks" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "schedule_draft_blocks" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "schedule_draft_blocks" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "schedule_drafts" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "schedule_drafts" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "schedule_drafts" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "schedule_generation_job" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "schedule_generation_job" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "schedule_generation_job" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "scheduler_school_year" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "scheduler_school_year" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "scheduler_school_year" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "scheduler_school_year_state" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "scheduler_school_year_state" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "scheduler_school_year_state" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "scheduler_state_version_events" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "scheduler_state_version_events" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "scheduler_state_version_events" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "school_calendar_event" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "school_calendar_event" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "school_calendar_event" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "subject" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "subject" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "subject" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "teacher" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "teacher" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "teacher" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "teacher_endpoint_operational_event" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "teacher_endpoint_operational_event" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "teacher_endpoint_operational_event" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "teacher_subject_link" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "teacher_subject_link" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "teacher_subject_link" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "teacher_weekly_timesheet" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "teacher_weekly_timesheet" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "teacher_weekly_timesheet" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "timeslot" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "timeslot" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "timeslot" TO cronos_app USING (organization_id = app_security.current_organization_id()) WITH CHECK (organization_id = app_security.current_organization_id())',
    'ALTER TABLE "organization" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "organization" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_isolation" ON "organization" TO cronos_app USING (id = app_security.current_organization_id()) WITH CHECK (id = app_security.current_organization_id())',
    'ALTER TABLE "user" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "user" FORCE ROW LEVEL SECURITY',
    'CREATE POLICY "tenant_membership_accounts" ON "user" TO cronos_app USING (EXISTS (SELECT 1 FROM organization_membership m WHERE m.account_id = id AND m.organization_id = app_security.current_organization_id()))',
    "GRANT USAGE ON SCHEMA public TO cronos_app, cronos_auth_definer",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO cronos_app",
    'REVOKE INSERT, UPDATE, DELETE ON TABLE "user" FROM cronos_app',
    "REVOKE ALL PRIVILEGES ON TABLE alembic_version FROM cronos_app",
    "REVOKE UPDATE, DELETE ON schedule_draft_blocks, schedule_diff_entries, scheduler_state_version_events, occurrence_operational_event, progress_ledger_entry FROM cronos_app",
    "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cronos_app",
    'GRANT SELECT, INSERT, UPDATE ON "user", organization, organization_membership TO cronos_auth_definer',
    "GRANT SELECT ON teacher TO cronos_auth_definer",
    "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cronos_auth_definer",
]

DOWNGRADE_SQL = [
    "DROP SCHEMA IF EXISTS app_security CASCADE",
    "ALTER TABLE lesson_occurrence DROP CONSTRAINT fk_lesson_occurrence_active_block_scope",
    "ALTER TABLE schedule_diff_entries DROP CONSTRAINT fk_schedule_diff_entries_before_active",
    "ALTER TABLE schedule_draft_blocks DROP CONSTRAINT fk_schedule_draft_blocks_source_active",
    "ALTER TABLE teacher DROP CONSTRAINT fk_teacher_organization_membership",
    "DROP TABLE planned_recovery_links",
    "DROP TABLE lesson_log",
    "DROP TABLE operational_schedule_block",
    "DROP TABLE occurrence_operational_event",
    "DROP TABLE scheduler_state_version_events",
    "DROP TABLE active_schedule_blocks",
    "DROP TABLE schedule_diff_entries",
    "DROP TABLE schedule_draft_blocks",
    "DROP TABLE scheduler_school_year_state",
    "DROP TABLE progress_ledger_entry",
    "DROP TABLE lesson_occurrence",
    "DROP TABLE schedule_drafts",
    'DROP TABLE "constraint"',
    "DROP TABLE class_subject_link",
    "DROP TABLE module",
    "DROP TABLE teacher_weekly_timesheet",
    "DROP TABLE schedule_generation_job",
    "DROP TABLE class",
    "DROP TABLE member_access_operation",
    "DROP TABLE availability",
    "DROP TABLE teacher_subject_link",
    "DROP TABLE course_subject_link",
    "DROP TABLE course",
    "DROP TABLE teacher_endpoint_operational_event",
    "DROP TABLE school_calendar_event",
    "DROP TABLE organization_grid_settings",
    "DROP TABLE scheduler_school_year",
    "DROP TABLE organization_settings",
    "DROP TABLE timeslot",
    "DROP TABLE subject",
    "DROP TABLE room",
    "DROP TABLE clerk_webhook_event",
    "DROP TABLE organization_membership",
    "DROP TABLE teacher",
    'DROP TABLE "user"',
    "DROP TABLE organization",
    "DROP TYPE organizationplanstatus",
    "DROP TYPE membershiplifecyclestatus",
    "DROP TYPE membershipaccessstatus",
    "DROP TYPE teacheraccessmode",
    "DROP TYPE clerkinvitationstatus",
    "DROP TYPE memberaccessoperationtype",
    "DROP TYPE memberaccessoperationstatus",
    "DROP TYPE clerkwebhookprocessingstatus",
    "DROP TYPE roomtype",
    "DROP TYPE constrainttype",
    "DROP TYPE schoolyearpublicationstate",
    "DROP TYPE schedulegenerationstrategy",
    "DROP TYPE schedulegenerationtrigger",
    "DROP TYPE schedulegenerationjobstatus",
    "DROP TYPE schedulegenerationresultcategory",
    "DROP TYPE scheduledraftstate",
    "DROP TYPE scheduledraftblockchangetype",
    "DROP TYPE schedulediffchangetype",
    "DROP TYPE schedulediffscope",
    "DROP TYPE activescheduleblockstatus",
    "DROP TYPE plannedrecoverylinkstatus",
    "DROP TYPE schedulerstatechangeoperation",
    "DROP TYPE schedulerstatechangescope",
    "DROP TYPE calendareventtype",
    "DROP TYPE calendareventsource",
    "DROP TYPE lessonoccurrencestatus",
    "DROP TYPE operationalblockstatus",
    "DROP TYPE operationalblockexecutionstatus",
    "DROP TYPE lessonlogstatus",
    "DROP TYPE timesheetstatus",
]


def upgrade() -> None:
    for statement in UPGRADE_SQL:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_SQL:
        if statement.startswith("DROP TABLE "):
            statement += " CASCADE"
        op.execute(statement)
