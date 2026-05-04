"""
Testes de Máquina de Estados e Contabilização
Parte de test_occurrences.py (split).
"""
import pytest
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from app import models, schemas
from app.models import LessonOccurrenceStatus
from app.services import occurrence_service
from test_occurrence_shared import full_setup, SyncTestSession


class TestOccurrenceStateMachineAndAccounting:
    """Cobre WBS 1.1, 1.2 e 1.3 (transições, contabilização e auditoria)."""

    def _load_occurrence(self, sync_db, schedule_output_id: int):
        return sync_db.execute(
            select(models.LessonOccurrence).where(
                models.LessonOccurrence.schedule_output_id == schedule_output_id
            )
        ).scalar_one()

    def _prepare_open_occurrence(self, sync_db, full_setup):
        occurrence, _ = occurrence_service.create_occurrence_from_block_sync(
            sync_db, full_setup["organization_id"], full_setup["schedule_output_id"],
        )
        return occurrence

    def test_concurrent_create_occurrence_command_keeps_single_row(self, full_setup):
        organization_id = full_setup["organization_id"]
        schedule_output_id = full_setup["schedule_output_id"]

        def _attempt_create():
            db_local = SyncTestSession()
            try:
                occurrence, created_now = occurrence_service.create_occurrence_from_block_sync(
                    db_local, organization_id=organization_id, schedule_output_id=schedule_output_id,
                )
                return {"id": occurrence.id, "created_now": created_now}
            finally:
                db_local.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [pool.submit(_attempt_create).result() for _ in range(2)]

        created_count = sum(1 for item in results if item["created_now"])
        assert created_count == 1
        assert results[0]["id"] == results[1]["id"]

        verify_db = SyncTestSession()
        try:
            occurrences = verify_db.execute(
                select(models.LessonOccurrence).where(
                    models.LessonOccurrence.organization_id == organization_id,
                    models.LessonOccurrence.schedule_output_id == schedule_output_id,
                )
            ).scalars().all()
            assert len(occurrences) == 1
        finally:
            verify_db.close()

    def test_given_to_gap_updates_accounting_and_audit(self, sync_db, full_setup):
        organization_id = full_setup["organization_id"]
        occurrence = self._prepare_open_occurrence(sync_db, full_setup)

        updated = occurrence_service.update_occurrence_sync(
            sync_db, occurrence.id, organization_id,
            schemas.LessonOccurrenceUpdate(status=LessonOccurrenceStatus.GAP),
            decided_by_user_id=full_setup["admin_id"],
        )

        assert updated.status == LessonOccurrenceStatus.GAP
        assert updated.decided_by_user_id == full_setup["admin_id"]
        assert updated.decided_at is not None
        assert updated.planned_teacher_id == full_setup["teacher_id"]
        assert updated.executed_teacher_id is None
        assert updated.hours_given == pytest.approx(0.0)

        progress = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == full_setup["class_id"],
                models.ClassProgress.module_id == full_setup["module_id"],
            )
        ).scalar_one()
        assert progress.hours_completed == pytest.approx(0.0)
        assert progress.hours_debt == pytest.approx(2.0)

    def test_given_to_substituted_moves_progress_and_creates_debt(self, sync_db, full_setup):
        organization_id = full_setup["organization_id"]
        occurrence = self._prepare_open_occurrence(sync_db, full_setup)

        updated = occurrence_service.update_occurrence_sync(
            sync_db, occurrence.id, organization_id,
            schemas.LessonOccurrenceUpdate(
                status=LessonOccurrenceStatus.SUBSTITUTED,
                substitute_teacher_id=full_setup["substitute_teacher_id"],
                substitute_subject_id=full_setup["substitute_subject_id"],
            ),
            decided_by_user_id=full_setup["admin_id"],
        )

        assert updated.status == LessonOccurrenceStatus.SUBSTITUTED
        assert updated.executed_teacher_id == full_setup["substitute_teacher_id"]
        assert updated.executed_module_id == full_setup["substitute_module_id"]

        planned_progress = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == full_setup["class_id"],
                models.ClassProgress.module_id == full_setup["module_id"],
            )
        ).scalar_one()
        substitute_progress = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == full_setup["class_id"],
                models.ClassProgress.module_id == full_setup["substitute_module_id"],
            )
        ).scalar_one()

        assert planned_progress.hours_completed == pytest.approx(0.0)
        assert planned_progress.hours_debt == pytest.approx(2.0)
        assert substitute_progress.hours_completed == pytest.approx(2.0)
        assert substitute_progress.hours_debt == pytest.approx(0.0)

        debts = occurrence_service.get_debts_sync(sync_db, organization_id)
        assert debts.total_gaps == 1
        assert debts.total_hours_owed == pytest.approx(2.0)

    def test_future_gap_is_counted_immediately_in_debts(self, sync_db, full_setup):
        organization_id = full_setup["organization_id"]
        future_date = date.today() + timedelta(days=7)

        future_output = models.ScheduleOutput(
            organization_id=organization_id,
            lesson_id=full_setup["lesson_id"],
            timeslot_id=full_setup["timeslot_id"],
            room_id=full_setup["room_id"],
            generation_id="future-gap-debt-001",
            date=future_date,
            is_draft=False,
        )
        sync_db.add(future_output)
        sync_db.commit()

        occurrence, _ = occurrence_service.create_occurrence_from_block_sync(
            sync_db, organization_id, future_output.id,
        )

        updated = occurrence_service.update_occurrence_sync(
            sync_db, occurrence.id, organization_id,
            schemas.LessonOccurrenceUpdate(status=LessonOccurrenceStatus.GAP),
            decided_by_user_id=full_setup["admin_id"],
        )

        assert updated.date == future_date
        assert updated.status == LessonOccurrenceStatus.GAP

        debts = occurrence_service.get_debts_sync(sync_db, organization_id)
        assert debts.total_gaps == 1
        assert debts.total_hours_owed == pytest.approx(2.0)
        assert debts.total_gaps_overdue == 0
        assert debts.total_hours_owed_overdue == pytest.approx(0.0)

    def test_invalid_transition_gap_to_substituted_fails(self, sync_db, full_setup):
        organization_id = full_setup["organization_id"]
        occurrence = self._prepare_open_occurrence(sync_db, full_setup)

        occurrence_service.update_occurrence_sync(
            sync_db, occurrence.id, organization_id,
            schemas.LessonOccurrenceUpdate(status=LessonOccurrenceStatus.GAP),
            decided_by_user_id=full_setup["admin_id"],
        )

        with pytest.raises(occurrence_service.OccurrenceServiceError) as exc_info:
            occurrence_service.update_occurrence_sync(
                sync_db, occurrence.id, organization_id,
                schemas.LessonOccurrenceUpdate(
                    status=LessonOccurrenceStatus.SUBSTITUTED,
                    substitute_teacher_id=full_setup["substitute_teacher_id"],
                    substitute_subject_id=full_setup["substitute_subject_id"],
                ),
                decided_by_user_id=full_setup["admin_id"],
            )
        assert exc_info.value.status_code == 409

    def test_idempotent_duplicate_submission_does_not_duplicate_accounting(self, sync_db, full_setup):
        organization_id = full_setup["organization_id"]
        occurrence = self._prepare_open_occurrence(sync_db, full_setup)
        payload = schemas.LessonOccurrenceUpdate(status=LessonOccurrenceStatus.GAP)

        occurrence_service.update_occurrence_sync(
            sync_db, occurrence.id, organization_id, payload,
            decided_by_user_id=full_setup["admin_id"],
        )
        occurrence_service.update_occurrence_sync(
            sync_db, occurrence.id, organization_id, payload,
            decided_by_user_id=full_setup["admin_id"],
        )

        progress = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == full_setup["class_id"],
                models.ClassProgress.module_id == full_setup["module_id"],
            )
        ).scalar_one()
        assert progress.hours_completed == pytest.approx(0.0)
        assert progress.hours_debt == pytest.approx(2.0)

    def test_update_occurrence_blocks_cross_tenant_access(self, sync_db, full_setup):
        organization_id = full_setup["organization_id"]
        occurrence = self._prepare_open_occurrence(sync_db, full_setup)

        with pytest.raises(occurrence_service.OccurrenceServiceError) as exc_info:
            occurrence_service.update_occurrence_sync(
                sync_db, occurrence.id, organization_id + 999,
                schemas.LessonOccurrenceUpdate(status=LessonOccurrenceStatus.GAP),
                decided_by_user_id=full_setup["admin_id"],
            )
        assert exc_info.value.status_code == 404

    def test_update_occurrence_rolls_back_on_mid_operation_error(self, sync_db, full_setup, monkeypatch):
        organization_id = full_setup["organization_id"]
        occurrence = self._prepare_open_occurrence(sync_db, full_setup)

        original = occurrence_service._apply_module_delta
        calls = {"count": 0}

        def _explode_on_second_module_delta(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 2:
                raise RuntimeError("forced-mid-operation-error")
            return original(*args, **kwargs)

        monkeypatch.setattr(occurrence_service, "_apply_module_delta", _explode_on_second_module_delta)

        with pytest.raises(RuntimeError):
            occurrence_service.update_occurrence_sync(
                sync_db, occurrence.id, organization_id,
                schemas.LessonOccurrenceUpdate(
                    status=LessonOccurrenceStatus.SUBSTITUTED,
                    substitute_teacher_id=full_setup["substitute_teacher_id"],
                    substitute_subject_id=full_setup["substitute_subject_id"],
                ),
                decided_by_user_id=full_setup["admin_id"],
            )

        sync_db.expire_all()

        reloaded_occurrence = self._load_occurrence(sync_db, full_setup["schedule_output_id"])
        reloaded_planned_progress = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == full_setup["class_id"],
                models.ClassProgress.module_id == full_setup["module_id"],
            )
        ).scalar_one_or_none()
        reloaded_executed_progress = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == full_setup["class_id"],
                models.ClassProgress.module_id == full_setup["substitute_module_id"],
            )
        ).scalar_one_or_none()

        assert reloaded_occurrence.status == LessonOccurrenceStatus.GIVEN
        assert reloaded_occurrence.decided_at is None
        assert reloaded_planned_progress is None
        assert reloaded_executed_progress is None

    def test_cannot_delete_occurrence_history(self, sync_db, full_setup):
        occurrence = self._prepare_open_occurrence(sync_db, full_setup)
        sync_db.delete(occurrence)
        with pytest.raises(ValueError):
            sync_db.commit()
        sync_db.rollback()
        still_exists = self._load_occurrence(sync_db, full_setup["schedule_output_id"])
        assert still_exists is not None
