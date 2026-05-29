"""
Testes de Schema — LessonOccurrence
Parte de test_occurrences.py (split).
"""
import pytest
from datetime import date, timedelta

from sqlalchemy import event

from app import models, schemas
from app.models import LessonOccurrenceStatus
from app.services import schedule_service
from test_occurrence_shared import full_setup, SyncTestSession, occurrence_service


class TestLessonOccurrenceSchemas:
    """Validação das regras Pydantic dos schemas de Sprint 2."""

    def test_create_occurrence_command_default_action_valid(self):
        payload = schemas.LessonOccurrenceCreate(schedule_output_id=10)
        assert payload.action == "CREATE_OCCURRENCE"

    def test_create_occurrence_command_rejects_unknown_action(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            schemas.LessonOccurrenceCreate(action="OPEN_OCCURRENCE", schedule_output_id=10)


class TestWeekSchedulePerformance:
    """Valida leitura semanal com custo estável (sem padrão N+1)."""

    def test_get_week_schedule_sync_avoids_n_plus_one_for_active_modules(self, sync_db, full_setup):
        organization_id = full_setup["organization_id"]
        class_id = full_setup["class_id"]
        room_id = full_setup["room_id"]
        timeslot_id = full_setup["timeslot_id"]
        week_start = date.today() - timedelta(days=date.today().weekday())

        for idx in range(12):
            teacher = models.Teacher(name=f"Perf Prof {idx}", organization_id=organization_id)
            sync_db.add(teacher)
            sync_db.flush()

            subject = models.Subject(
                name=f"Perf Subject {idx}",
                organization_id=organization_id,
                required_room_type=models.RoomType.normal,
            )
            sync_db.add(subject)
            sync_db.flush()

            sync_db.add(models.Module(
                name=f"Perf Module {idx}", hours_total=20, order=1, subject_id=subject.id,
            ))
            sync_db.flush()

            lesson = models.Lesson(
                organization_id=organization_id,
                class_id=class_id, subject_id=subject.id, teacher_id=teacher.id,
            )
            sync_db.add(lesson)
            sync_db.flush()

            sync_db.add(models.ScheduleOutput(
                organization_id=organization_id, lesson_id=lesson.id,
                timeslot_id=timeslot_id, room_id=room_id,
                generation_id=f"perf-gen-{idx}", date=week_start + timedelta(days=idx % 5),
                is_draft=False,
            ))

        sync_db.commit()

        bind = sync_db.get_bind()
        counter = {"count": 0}

        def _before_cursor_execute(*_args, **_kwargs):
            counter["count"] += 1

        event.listen(bind, "before_cursor_execute", _before_cursor_execute)
        try:
            slots = schedule_service.get_week_schedule_sync(
                sync_db, organization_id=organization_id, week_start=week_start, class_id=class_id,
            )
        finally:
            event.remove(bind, "before_cursor_execute", _before_cursor_execute)

        assert len(slots) >= 10
        assert counter["count"] <= 8

    def test_update_status_gap_valid(self):
        payload = schemas.LessonOccurrenceUpdate(status=LessonOccurrenceStatus.GAP, version=1)
        assert payload.status == LessonOccurrenceStatus.GAP
        assert payload.substitute_teacher_id is None

    def test_update_status_given_valid(self):
        payload = schemas.LessonOccurrenceUpdate(status=LessonOccurrenceStatus.GIVEN, version=1)
        assert payload.status == LessonOccurrenceStatus.GIVEN

    def test_update_status_requires_version(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            schemas.LessonOccurrenceUpdate(status=LessonOccurrenceStatus.GAP)

    def test_update_status_substituted_requires_teacher(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError) as exc_info:
            schemas.LessonOccurrenceUpdate(
                status=LessonOccurrenceStatus.SUBSTITUTED,
                version=1,
                substitute_teacher_id=None, substitute_subject_id=7,
            )
        errors = exc_info.value.errors()
        assert any("substitute_teacher_id" in str(e) for e in errors)

    def test_update_status_substituted_requires_subject(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError) as exc_info:
            schemas.LessonOccurrenceUpdate(
                status=LessonOccurrenceStatus.SUBSTITUTED,
                version=1,
                substitute_teacher_id=42, substitute_subject_id=None,
            )
        errors = exc_info.value.errors()
        assert any("substitute_subject_id" in str(e) for e in errors)

    def test_update_status_substituted_with_teacher_valid(self):
        payload = schemas.LessonOccurrenceUpdate(
            status=LessonOccurrenceStatus.SUBSTITUTED,
            version=1,
            substitute_teacher_id=42, substitute_subject_id=7,
        )
        assert payload.substitute_teacher_id == 42

    def test_update_status_gap_rejects_substitute_fields(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            schemas.LessonOccurrenceUpdate(
                status=LessonOccurrenceStatus.GAP,
                version=1,
                substitute_teacher_id=1, substitute_subject_id=2,
            )

    def test_debt_item_schema(self):
        item = schemas.DebtItem(
            class_id=1, class_name="TINF 24/27",
            subject_id=2, subject_name="Programação",
            teacher_id=3, teacher_name="Prof. Silva",
            gap_occurrences=3, hours_owed=6.0,
        )
        assert item.hours_owed == pytest.approx(6.0)
        assert item.gap_occurrences_overdue == 0
        assert item.hours_owed_overdue == pytest.approx(0.0)

    def test_debt_list_read_schema(self):
        debt_list = schemas.DebtListRead(
            total_gaps=2, total_hours_owed=4.0,
            as_of_date=date.today(), items=[],
        )
        assert debt_list.total_gaps == 2

    def test_available_substitute_schema(self):
        sub = schemas.AvailableSubstituteRead(
            teacher_id=1, teacher_name="Prof. Maria",
            subject_id=2, subject_name="Matemática",
            class_id=3, class_name="10A",
        )
        assert sub.teacher_id == 1
