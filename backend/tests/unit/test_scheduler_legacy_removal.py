from app import models


def test_scheduler_metadata_excludes_retired_scheduler_tables_and_pointers():
    retired_tables = {
        "schedule_drafts",
        "schedule_draft_blocks",
        "schedule_diff_entries",
        "active_schedule_blocks",
        "planned_recovery_links",
    }
    assert retired_tables.isdisjoint(models.Base.metadata.tables)
    for model, retired_columns in (
        (models.SchedulerSchoolYearState, {"pending_draft_id"}),
        (models.LessonOccurrence, {"active_schedule_block_id"}),
        (models.OperationalScheduleBlock, {"planned_active_schedule_block_id"}),
        (models.LessonLog, {"active_schedule_block_id"}),
    ):
        assert retired_columns.isdisjoint(model.__table__.columns.keys())
    for table in models.Base.metadata.tables.values():
        assert all(
            fk.target_fullname.split(".")[0] not in retired_tables for fk in table.foreign_keys
        )
