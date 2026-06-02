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
from app.services import lesson_log_service, occurrence_service
from test_occurrence_shared import full_setup, substitution_setup, SyncTestSession


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
            schemas.LessonOccurrenceUpdate(status=LessonOccurrenceStatus.GAP, version=occurrence.version),
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
                version=occurrence.version,
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
        # V4: substitute module no longer gets ClassProgress row on SUBSTITUTED decision.
        # Hours are credited when the substitute teacher registers "Aula Dada" via LessonLog COMPLETED.
        substitute_progress = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == full_setup["class_id"],
                models.ClassProgress.module_id == full_setup["substitute_module_id"],
            )
        ).scalar_one_or_none()

        assert planned_progress.hours_completed == pytest.approx(0.0)
        assert planned_progress.hours_debt == pytest.approx(2.0)
        # V4: substitute module should not have any progress yet
        assert substitute_progress is None or substitute_progress.hours_completed == pytest.approx(0.0)

        debts = occurrence_service.get_debts_sync(sync_db, organization_id)
        assert debts.total_gaps == 1
        assert debts.total_hours_owed == pytest.approx(2.0)

    def test_cancel_completed_operational_substitution_compensates_log_progress(self, sync_db, full_setup):
        organization_id = full_setup["organization_id"]
        occurrence = self._prepare_open_occurrence(sync_db, full_setup)

        updated = occurrence_service.update_occurrence_sync(
            sync_db, occurrence.id, organization_id,
            schemas.LessonOccurrenceUpdate(
                status=LessonOccurrenceStatus.SUBSTITUTED,
                version=occurrence.version,
                substitute_teacher_id=full_setup["substitute_teacher_id"],
                substitute_subject_id=full_setup["substitute_subject_id"],
            ),
            decided_by_user_id=full_setup["admin_id"],
        )

        block = sync_db.execute(
            select(models.OperationalScheduleBlock).where(
                models.OperationalScheduleBlock.source_occurrence_id == occurrence.id,
                models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
            )
        ).scalar_one()

        lesson_log_service.upsert_operational_lesson_log_sync(
            sync_db,
            organization_id,
            full_setup["admin_id"],
            block.id,
            schemas.LessonLogCreate(status=models.LessonLogStatus.COMPLETED, summary="Substituicao", notes=""),
        )

        substitute_progress = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == full_setup["class_id"],
                models.ClassProgress.module_id == full_setup["substitute_module_id"],
            )
        ).scalar_one()
        assert substitute_progress.hours_completed == pytest.approx(2.0)

        occurrence_service.cancel_occurrence_sync(
            sync_db,
            organization_id,
            occurrence.id,
            full_setup["admin_id"],
            version=updated.version,
            cancel_completed_substitute_log=True,
        )
        sync_db.expire_all()

        cancelled_block = sync_db.get(models.OperationalScheduleBlock, block.id)
        op_log = sync_db.execute(
            select(models.LessonLog).where(models.LessonLog.operational_block_id == block.id)
        ).scalar_one()
        substitute_progress = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == full_setup["class_id"],
                models.ClassProgress.module_id == full_setup["substitute_module_id"],
            )
        ).scalar_one()

        assert cancelled_block.status == models.OperationalBlockStatus.CANCELLED
        assert cancelled_block.execution_status == models.OperationalBlockExecutionStatus.CANCELLED
        assert op_log.status == models.LessonLogStatus.PENDING
        assert substitute_progress.hours_completed == pytest.approx(0.0)

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
            schemas.LessonOccurrenceUpdate(status=LessonOccurrenceStatus.GAP, version=occurrence.version),
            decided_by_user_id=full_setup["admin_id"],
        )

        assert updated.date == future_date
        assert updated.status == LessonOccurrenceStatus.GAP

        debts = occurrence_service.get_debts_sync(sync_db, organization_id)
        assert debts.total_gaps == 1
        assert debts.total_hours_owed == pytest.approx(2.0)
        assert debts.total_gaps_overdue == 0
        assert debts.total_hours_owed_overdue == pytest.approx(0.0)

    def test_redecision_gap_to_substituted_allowed(self, sync_db, full_setup):
        """WBS V3 Fase 2: GAP→SUBSTITUTED now allowed (re-decision)."""
        organization_id = full_setup["organization_id"]
        occurrence = self._prepare_open_occurrence(sync_db, full_setup)

        # First decide as GAP
        decided_gap = occurrence_service.update_occurrence_sync(
            sync_db, occurrence.id, organization_id,
            schemas.LessonOccurrenceUpdate(status=LessonOccurrenceStatus.GAP, version=occurrence.version),
            decided_by_user_id=full_setup["admin_id"],
        )

        # Re-decide as SUBSTITUTED — should succeed
        updated = occurrence_service.update_occurrence_sync(
            sync_db, occurrence.id, organization_id,
            schemas.LessonOccurrenceUpdate(
                status=LessonOccurrenceStatus.SUBSTITUTED,
                version=decided_gap.version,
                substitute_teacher_id=full_setup["substitute_teacher_id"],
                substitute_subject_id=full_setup["substitute_subject_id"],
            ),
            decided_by_user_id=full_setup["admin_id"],
        )
        assert updated.status == LessonOccurrenceStatus.SUBSTITUTED

    def test_idempotent_duplicate_submission_does_not_duplicate_accounting(self, sync_db, full_setup):
        organization_id = full_setup["organization_id"]
        occurrence = self._prepare_open_occurrence(sync_db, full_setup)
        payload = schemas.LessonOccurrenceUpdate(status=LessonOccurrenceStatus.GAP, version=occurrence.version)

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
                schemas.LessonOccurrenceUpdate(status=LessonOccurrenceStatus.GAP, version=occurrence.version),
                decided_by_user_id=full_setup["admin_id"],
            )
        assert exc_info.value.status_code == 404

    def test_update_occurrence_rolls_back_on_mid_operation_error(self, sync_db, full_setup, monkeypatch):
        organization_id = full_setup["organization_id"]
        occurrence = self._prepare_open_occurrence(sync_db, full_setup)

        original = occurrence_service._apply_module_delta

        def _explode_on_first_module_delta(*args, **kwargs):
            raise RuntimeError("forced-mid-operation-error")

        monkeypatch.setattr(occurrence_service, "_apply_module_delta", _explode_on_first_module_delta)

        with pytest.raises(RuntimeError):
            occurrence_service.update_occurrence_sync(
                sync_db, occurrence.id, organization_id,
                schemas.LessonOccurrenceUpdate(
                    status=LessonOccurrenceStatus.SUBSTITUTED,
                    version=occurrence.version,
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

        assert reloaded_occurrence.status is None
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


class TestGivenWithCompletedLogPreventsDoubleCredit:
    """GIVEN decision must not double-credit when LessonLog.COMPLETED already exists."""

    def test_given_does_not_double_credit_when_lesson_log_completed(self, sync_db, full_setup):
        from app.models import LessonLogStatus
        organization_id = full_setup["organization_id"]
        output = sync_db.get(models.ScheduleOutput, full_setup["schedule_output_id"])

        occurrence, _ = occurrence_service.create_occurrence_from_block_sync(
            sync_db, organization_id, output.id,
        )

        # Simulate an equivalent completed LessonLog and its already-applied progress.
        llog = models.LessonLog(
            organization_id=organization_id,
            schedule_output_id=output.id,
            status=LessonLogStatus.COMPLETED,
            summary="Aula dada",
            logged_by_user_id=full_setup["teacher_id"],
        )
        sync_db.add(llog)
        occurrence_service._apply_state_accounting(
            sync_db,
            organization_id=organization_id,
            class_id=full_setup["class_id"],
            status=LessonOccurrenceStatus.GIVEN,
            planned_module_id=full_setup["module_id"],
            executed_module_id=full_setup["module_id"],
            planned_hours=2.0,
            direction=1,
        )
        sync_db.flush()

        # Record progress before admin decision
        progress_before = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == full_setup["class_id"],
                models.ClassProgress.module_id == full_setup["module_id"],
            )
        ).scalar_one_or_none()
        hours_before = float(progress_before.hours_completed) if progress_before else 0.0

        occurrence_service.update_occurrence_sync(
            sync_db, occurrence.id, organization_id,
            schemas.LessonOccurrenceUpdate(status=LessonOccurrenceStatus.GIVEN, version=occurrence.version),
            decided_by_user_id=full_setup["admin_id"],
        )

        # Progress should NOT increase — the LessonLog.COMPLETED already credited it
        progress_after = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == full_setup["class_id"],
                models.ClassProgress.module_id == full_setup["module_id"],
            )
        ).scalar_one()
        assert progress_after.hours_completed == pytest.approx(hours_before)


class TestSubstitutedToGapRedecision:
    """SUBSTITUTED -> GAP redecision cancels operational block and compensates accounting."""

    def test_substituted_to_gap_redecision_cancels_block(self, sync_db, full_setup, substitution_setup):
        organization_id = full_setup["organization_id"]
        output = sync_db.get(models.ScheduleOutput, full_setup["schedule_output_id"])

        # Create and decide SUBSTITUTED
        occurrence, _ = occurrence_service.create_occurrence_from_block_sync(
            sync_db, organization_id, output.id,
        )
        decided = occurrence_service.update_occurrence_sync(
            sync_db, occurrence.id, organization_id,
            schemas.LessonOccurrenceUpdate(
                status=LessonOccurrenceStatus.SUBSTITUTED,
                version=occurrence.version,
                substitute_teacher_id=substitution_setup["substitute_teacher_id"],
                substitute_subject_id=substitution_setup["substitute_subject_id"],
            ),
            decided_by_user_id=full_setup["admin_id"],
        )

        # Verify operational block exists
        block = sync_db.execute(
            select(models.OperationalScheduleBlock).where(
                models.OperationalScheduleBlock.source_occurrence_id == occurrence.id,
                models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
            )
        ).scalar_one_or_none()
        assert block is not None

        # Redecide to GAP
        updated = occurrence_service.update_occurrence_sync(
            sync_db, occurrence.id, organization_id,
            schemas.LessonOccurrenceUpdate(
                status=LessonOccurrenceStatus.GAP,
                version=decided.version,
            ),
            decided_by_user_id=full_setup["admin_id"],
        )
        assert updated.status == LessonOccurrenceStatus.GAP

        # Operational block should be cancelled
        block_after = sync_db.execute(
            select(models.OperationalScheduleBlock).where(
                models.OperationalScheduleBlock.source_occurrence_id == occurrence.id,
                models.OperationalScheduleBlock.source_occurrence_revision == occurrence.revision,
            )
        ).scalar_one()
        assert block_after.status == models.OperationalBlockStatus.CANCELLED

        # Debt should be on the planned module (GAP creates debt)
        planned_progress = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == full_setup["class_id"],
                models.ClassProgress.module_id == full_setup["module_id"],
            )
        ).scalar_one()
        assert planned_progress.hours_debt == pytest.approx(2.0)

    def test_substituted_to_gap_blocks_if_completed_log(self, sync_db, full_setup, substitution_setup):
        """SUBSTITUTED->GAP should block if substitute already completed the log and timesheet is open."""
        from app.models import LessonLogStatus
        organization_id = full_setup["organization_id"]
        output = sync_db.get(models.ScheduleOutput, full_setup["schedule_output_id"])

        # Create and decide SUBSTITUTED
        occurrence, _ = occurrence_service.create_occurrence_from_block_sync(
            sync_db, organization_id, output.id,
        )
        decided = occurrence_service.update_occurrence_sync(
            sync_db, occurrence.id, organization_id,
            schemas.LessonOccurrenceUpdate(
                status=LessonOccurrenceStatus.SUBSTITUTED,
                version=occurrence.version,
                substitute_teacher_id=substitution_setup["substitute_teacher_id"],
                substitute_subject_id=substitution_setup["substitute_subject_id"],
            ),
            decided_by_user_id=full_setup["admin_id"],
        )

        # Substitute marks the operational block as COMPLETED
        block = sync_db.execute(
            select(models.OperationalScheduleBlock).where(
                models.OperationalScheduleBlock.source_occurrence_id == occurrence.id,
                models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
            )
        ).scalar_one()
        from app.services import lesson_log_service
        lesson_log_service.upsert_operational_lesson_log_sync(
            sync_db, organization_id, full_setup["admin_id"], block.id,
            schemas.LessonLogCreate(status=LessonLogStatus.COMPLETED, summary="Aula substituta"),
        )

        # Redecide to GAP without cancel_completed_substitute_log should fail
        with pytest.raises(occurrence_service.OccurrenceServiceError) as exc_info:
            occurrence_service.update_occurrence_sync(
                sync_db, occurrence.id, organization_id,
                schemas.LessonOccurrenceUpdate(
                    status=LessonOccurrenceStatus.GAP,
                    version=decided.version,
                ),
                decided_by_user_id=full_setup["admin_id"],
            )
        assert exc_info.value.status_code == 409
        assert "SUBSTITUTE_LOG_LOCKED" in exc_info.value.detail


class TestCompletedSubstitutionRedecision:
    """Tests for redecision after substitution is already completed."""

    def test_substituted_to_substituted_identical_is_idempotent(self, sync_db, full_setup, substitution_setup):
        """SUBSTITUTED -> SUBSTITUTED with same teacher/subject is idempotent."""
        organization_id = full_setup["organization_id"]
        output = sync_db.get(models.ScheduleOutput, full_setup["schedule_output_id"])

        occurrence, _ = occurrence_service.create_occurrence_from_block_sync(
            sync_db, organization_id, output.id,
        )
        occurrence_service.update_occurrence_sync(
            sync_db, occurrence.id, organization_id,
            schemas.LessonOccurrenceUpdate(
                status=LessonOccurrenceStatus.SUBSTITUTED,
                version=occurrence.version,
                substitute_teacher_id=substitution_setup["substitute_teacher_id"],
                substitute_subject_id=substitution_setup["substitute_subject_id"],
            ),
            decided_by_user_id=full_setup["admin_id"],
        )

        # Idempotent retry with same payload
        result = occurrence_service.update_occurrence_sync(
            sync_db, occurrence.id, organization_id,
            schemas.LessonOccurrenceUpdate(
                status=LessonOccurrenceStatus.SUBSTITUTED,
                version=occurrence.version,
                substitute_teacher_id=substitution_setup["substitute_teacher_id"],
                substitute_subject_id=substitution_setup["substitute_subject_id"],
            ),
            decided_by_user_id=full_setup["admin_id"],
        )
        assert result.status == LessonOccurrenceStatus.SUBSTITUTED

    def test_substituted_to_substituted_different_teacher_blocked_if_completed(self, sync_db, full_setup, substitution_setup):
        """SUBSTITUTED -> SUBSTITUTED with different teacher is blocked if completed log exists."""
        from app.models import LessonLogStatus
        organization_id = full_setup["organization_id"]
        output = sync_db.get(models.ScheduleOutput, full_setup["schedule_output_id"])

        occurrence, _ = occurrence_service.create_occurrence_from_block_sync(
            sync_db, organization_id, output.id,
        )
        occurrence_service.update_occurrence_sync(
            sync_db, occurrence.id, organization_id,
            schemas.LessonOccurrenceUpdate(
                status=LessonOccurrenceStatus.SUBSTITUTED,
                version=occurrence.version,
                substitute_teacher_id=substitution_setup["substitute_teacher_id"],
                substitute_subject_id=substitution_setup["substitute_subject_id"],
            ),
            decided_by_user_id=full_setup["admin_id"],
        )

        # Substitute completes the block
        block = sync_db.execute(
            select(models.OperationalScheduleBlock).where(
                models.OperationalScheduleBlock.source_occurrence_id == occurrence.id,
                models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
            )
        ).scalar_one()
        from app.services import lesson_log_service
        lesson_log_service.upsert_operational_lesson_log_sync(
            sync_db, organization_id, full_setup["admin_id"], block.id,
            schemas.LessonLogCreate(status=LessonLogStatus.COMPLETED, summary="done"),
        )

        # Try to change to a different substitute → should be blocked
        with pytest.raises(occurrence_service.OccurrenceServiceError) as exc_info:
            occurrence_service.update_occurrence_sync(
                sync_db, occurrence.id, organization_id,
                schemas.LessonOccurrenceUpdate(
                    status=LessonOccurrenceStatus.SUBSTITUTED,
                    version=occurrence.version + 1,
                    substitute_teacher_id=substitution_setup["candidate_b_teacher_id"],
                    substitute_subject_id=substitution_setup["candidate_b_subject_id"],
                ),
                decided_by_user_id=full_setup["admin_id"],
            )
        assert exc_info.value.status_code == 409
