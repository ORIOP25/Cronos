"""
Testes de Elegibilidade e Ranking de Substituições
Parte de test_occurrences.py (split).
"""
import pytest
from datetime import date, datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from app import models, schemas
from app.models import LessonOccurrenceStatus
from app.services import occurrence_service
from test_occurrence_shared import full_setup, SyncTestSession, substitution_setup


class TestSubstitutionEligibilityAndRanking:
    """Cobre WBS 2.1 e 2.2: elegibilidade e ranking determinístico."""

    def _prepare_occurrence(self, sync_db, setup):
        occurrence, _ = occurrence_service.create_occurrence_from_block_sync(
            sync_db, setup["organization_id"], setup["schedule_output_id"],
        )
        return occurrence

    def test_valid_substitution_same_class_different_subject(self, sync_db, substitution_setup):
        occurrence = self._prepare_occurrence(sync_db, substitution_setup)

        updated = occurrence_service.update_occurrence_sync(
            sync_db, occurrence.id, substitution_setup["organization_id"],
            schemas.LessonOccurrenceUpdate(
                status=LessonOccurrenceStatus.SUBSTITUTED,
                version=occurrence.version,
                substitute_teacher_id=substitution_setup["substitute_teacher_id"],
                substitute_subject_id=substitution_setup["substitute_subject_id"],
            ),
            decided_by_user_id=substitution_setup["admin_id"],
        )

        assert updated.status == LessonOccurrenceStatus.SUBSTITUTED
        assert updated.substitute_teacher_id == substitution_setup["substitute_teacher_id"]

    def test_invalid_same_subject_teacher_from_other_class(self, sync_db, substitution_setup):
        occurrence = self._prepare_occurrence(sync_db, substitution_setup)

        with pytest.raises(occurrence_service.OccurrenceServiceError) as exc_info:
            occurrence_service.update_occurrence_sync(
                sync_db, occurrence.id, substitution_setup["organization_id"],
                schemas.LessonOccurrenceUpdate(
                    status=LessonOccurrenceStatus.SUBSTITUTED,
                    version=occurrence.version,
                    substitute_teacher_id=substitution_setup["teacher_same_subject_other_class_id"],
                    substitute_subject_id=substitution_setup["subject_id"],
                ),
                decided_by_user_id=substitution_setup["admin_id"],
            )
        assert exc_info.value.status_code == 409

    def test_invalid_substitution_slot_conflict(self, sync_db, substitution_setup):
        occurrence = self._prepare_occurrence(sync_db, substitution_setup)

        with pytest.raises(occurrence_service.OccurrenceServiceError) as exc_info:
            occurrence_service.update_occurrence_sync(
                sync_db, occurrence.id, substitution_setup["organization_id"],
                schemas.LessonOccurrenceUpdate(
                    status=LessonOccurrenceStatus.SUBSTITUTED,
                    version=occurrence.version,
                    substitute_teacher_id=substitution_setup["conflict_teacher_id"],
                    substitute_subject_id=substitution_setup["conflict_subject_id"],
                ),
                decided_by_user_id=substitution_setup["admin_id"],
            )
        assert exc_info.value.status_code == 409
        assert "conflito" in exc_info.value.detail.lower()

    def test_invalid_substitution_when_teacher_already_substituting_same_slot(
        self, sync_db, substitution_setup,
    ):
        occurrence = self._prepare_occurrence(sync_db, substitution_setup)
        source_output = sync_db.get(models.ScheduleOutput, substitution_setup["schedule_output_id"])
        assert source_output is not None

        blocking_lesson = models.Lesson(
            organization_id=substitution_setup["organization_id"],
            class_id=substitution_setup["class_id"],
            subject_id=substitution_setup["substitute_subject_id"],
            teacher_id=substitution_setup["substitute_teacher_id"],
        )
        sync_db.add(blocking_lesson)
        sync_db.flush()

        blocking_output = models.ScheduleOutput(
            organization_id=substitution_setup["organization_id"],
            lesson_id=blocking_lesson.id,
            timeslot_id=source_output.timeslot_id,
            room_id=source_output.room_id,
            generation_id="gen-block-existing-substitution",
            date=source_output.date,
            is_draft=False,
        )
        sync_db.add(blocking_output)
        sync_db.flush()

        sync_db.add(models.LessonOccurrence(
            organization_id=substitution_setup["organization_id"],
            schedule_output_id=blocking_output.id,
            date=source_output.date,
            status=LessonOccurrenceStatus.SUBSTITUTED,
            planned_hours=2.0,
            substitute_teacher_id=substitution_setup["substitute_teacher_id"],
            substitute_subject_id=substitution_setup["substitute_subject_id"],
            planned_teacher_id=substitution_setup["substitute_teacher_id"],
            executed_teacher_id=substitution_setup["substitute_teacher_id"],
            planned_module_id=substitution_setup["substitute_module_id"],
            executed_module_id=substitution_setup["substitute_module_id"],
            hours_given=2.0,
            decided_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        ))
        sync_db.commit()

        with pytest.raises(occurrence_service.OccurrenceServiceError) as exc_info:
            occurrence_service.update_occurrence_sync(
                sync_db, occurrence.id, substitution_setup["organization_id"],
                schemas.LessonOccurrenceUpdate(
                    status=LessonOccurrenceStatus.SUBSTITUTED,
                    version=occurrence.version,
                    substitute_teacher_id=substitution_setup["substitute_teacher_id"],
                    substitute_subject_id=substitution_setup["substitute_subject_id"],
                ),
                decided_by_user_id=substitution_setup["admin_id"],
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == occurrence_service.ERR_SUBSTITUTE_SLOT_CONFLICT

    def test_invalid_substitution_different_tenant(self, sync_db, substitution_setup):
        occurrence = self._prepare_occurrence(sync_db, substitution_setup)

        with pytest.raises(occurrence_service.OccurrenceServiceError) as exc_info:
            occurrence_service.update_occurrence_sync(
                sync_db, occurrence.id, substitution_setup["organization_id"],
                schemas.LessonOccurrenceUpdate(
                    status=LessonOccurrenceStatus.SUBSTITUTED,
                    version=occurrence.version,
                    substitute_teacher_id=substitution_setup["other_tenant_teacher_id"],
                    substitute_subject_id=substitution_setup["other_tenant_subject_id"],
                ),
                decided_by_user_id=substitution_setup["admin_id"],
            )
        assert exc_info.value.status_code == 409

    def test_recommendation_ranking_reproducible(self, sync_db, substitution_setup):
        occurrence = self._prepare_occurrence(sync_db, substitution_setup)

        first = occurrence_service.get_substitute_recommendations_sync(
            sync_db, organization_id=substitution_setup["organization_id"], occurrence_id=occurrence.id,
        )
        second = occurrence_service.get_substitute_recommendations_sync(
            sync_db, organization_id=substitution_setup["organization_id"], occurrence_id=occurrence.id,
        )
        assert [(r.teacher_id, r.subject_id, r.rank) for r in first] == [
            (r.teacher_id, r.subject_id, r.rank) for r in second
        ]

    def test_recommendation_tie_break_by_teacher_id(self, sync_db, substitution_setup):
        occurrence = self._prepare_occurrence(sync_db, substitution_setup)
        recs = occurrence_service.get_substitute_recommendations_sync(
            sync_db, organization_id=substitution_setup["organization_id"], occurrence_id=occurrence.id,
        )
        assert len(recs) >= 2
        expected_first = min(
            substitution_setup["substitute_teacher_id"], substitution_setup["candidate_b_teacher_id"],
        )
        assert recs[0].teacher_id == expected_first

    def test_recommendation_criteria3_applies_when_criteria1_2_tie(self, sync_db, substitution_setup):
        occurrence = self._prepare_occurrence(sync_db, substitution_setup)
        schedule_output = sync_db.get(models.ScheduleOutput, substitution_setup["schedule_output_id"])
        assert schedule_output is not None

        candidate_b_module_id = sync_db.execute(
            select(models.Module.id).where(
                models.Module.subject_id == substitution_setup["candidate_b_subject_id"]
            )
        ).scalar_one()

        older_date = occurrence.date - timedelta(days=10)
        newer_date = occurrence.date - timedelta(days=3)

        so_old = models.ScheduleOutput(
            organization_id=substitution_setup["organization_id"],
            lesson_id=schedule_output.lesson_id,
            timeslot_id=schedule_output.timeslot_id,
            room_id=schedule_output.room_id,
            generation_id="gen-step2-old",
            date=older_date,
            is_draft=False,
        )
        so_new = models.ScheduleOutput(
            organization_id=substitution_setup["organization_id"],
            lesson_id=schedule_output.lesson_id,
            timeslot_id=schedule_output.timeslot_id,
            room_id=schedule_output.room_id,
            generation_id="gen-step2-new",
            date=newer_date,
            is_draft=False,
        )
        sync_db.add_all([so_old, so_new])
        sync_db.flush()

        sync_db.add(models.LessonOccurrence(
            organization_id=substitution_setup["organization_id"],
            schedule_output_id=so_old.id, date=older_date,
            status=LessonOccurrenceStatus.SUBSTITUTED,
            planned_hours=2.0,
            substitute_teacher_id=substitution_setup["candidate_b_teacher_id"],
            substitute_subject_id=substitution_setup["candidate_b_subject_id"],
            planned_teacher_id=substitution_setup["teacher_id"],
            executed_teacher_id=substitution_setup["candidate_b_teacher_id"],
            planned_module_id=substitution_setup["module_id"],
            executed_module_id=candidate_b_module_id,
            hours_given=2.0,
        ))
        sync_db.add(models.LessonOccurrence(
            organization_id=substitution_setup["organization_id"],
            schedule_output_id=so_new.id, date=newer_date,
            status=LessonOccurrenceStatus.SUBSTITUTED,
            planned_hours=2.0,
            substitute_teacher_id=substitution_setup["substitute_teacher_id"],
            substitute_subject_id=substitution_setup["substitute_subject_id"],
            planned_teacher_id=substitution_setup["teacher_id"],
            executed_teacher_id=substitution_setup["substitute_teacher_id"],
            planned_module_id=substitution_setup["module_id"],
            executed_module_id=substitution_setup["substitute_module_id"],
            hours_given=2.0,
        ))
        sync_db.commit()

        recs = occurrence_service.get_substitute_recommendations_sync(
            sync_db, organization_id=substitution_setup["organization_id"], occurrence_id=occurrence.id,
        )
        assert recs[0].teacher_id == substitution_setup["candidate_b_teacher_id"]

    def test_recommendation_empty_when_no_eligible(self, sync_db, substitution_setup):
        occurrence = self._prepare_occurrence(sync_db, substitution_setup)

        sync_db.query(models.Availability).filter(
            models.Availability.timeslot_id == substitution_setup["timeslot_id"]
        ).update({models.Availability.score: models.PreferenceLevel.IMPOSSIBLE.value})
        sync_db.commit()

        recs = occurrence_service.get_substitute_recommendations_sync(
            sync_db, organization_id=substitution_setup["organization_id"], occurrence_id=occurrence.id,
        )
        assert recs == []

    def test_concurrent_substitution_confirmations_only_one_wins(self, substitution_setup):
        organization_id = substitution_setup["organization_id"]
        admin_id = substitution_setup["admin_id"]

        seed_db = SyncTestSession()
        try:
            occurrence, _ = occurrence_service.create_occurrence_from_block_sync(
                seed_db, organization_id, substitution_setup["schedule_output_id"],
            )
            occurrence_id = occurrence.id
        finally:
            seed_db.close()

        candidate_pairs = [
            (substitution_setup["substitute_teacher_id"], substitution_setup["substitute_subject_id"]),
            (substitution_setup["candidate_b_teacher_id"], substitution_setup["candidate_b_subject_id"]),
        ]

        def _attempt_confirm(candidate):
            teacher_id, subject_id = candidate
            db_local = SyncTestSession()
            try:
                updated = occurrence_service.update_occurrence_sync(
                    db_local, occurrence_id, organization_id,
                    schemas.LessonOccurrenceUpdate(
                        status=LessonOccurrenceStatus.SUBSTITUTED,
                        version=1,
                        substitute_teacher_id=teacher_id, substitute_subject_id=subject_id,
                    ),
                    decided_by_user_id=admin_id,
                )
                return {"ok": True, "teacher_id": updated.executed_teacher_id}
            except occurrence_service.OccurrenceServiceError as exc:
                return {"ok": False, "status_code": exc.status_code, "detail": exc.detail}
            finally:
                db_local.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(_attempt_confirm, pair) for pair in candidate_pairs]
            results = [future.result() for future in futures]

        # V5: optimistic concurrency allows only the first confirmation with
        # the original version to win; the stale concurrent update is rejected.
        success = [r for r in results if r["ok"]]
        failures = [r for r in results if not r["ok"]]
        assert len(success) == 1
        assert len(failures) == 1
        assert failures[0]["status_code"] == 409

        verify_db = SyncTestSession()
        try:
            final_occurrence = verify_db.get(models.LessonOccurrence, occurrence_id)
            assert final_occurrence is not None
            assert final_occurrence.status == LessonOccurrenceStatus.SUBSTITUTED
            assert final_occurrence.executed_teacher_id == success[0]["teacher_id"]
        finally:
            verify_db.close()
