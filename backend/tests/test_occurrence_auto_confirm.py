"""
Testes de Auto-Confirmação e Dívidas
Parte de test_occurrences.py (split).
"""
import pytest
from datetime import date, timedelta

from sqlalchemy import select

from app import models
from app.models import LessonOccurrenceStatus
from app.services import occurrence_service
from test_occurrence_shared import full_setup


class TestAutoConfirmService:
    """Testa o cron de confirmação automática diária."""

    def test_auto_confirm_creates_given_record(self, sync_db, full_setup):
        organization_id = full_setup["organization_id"]
        today = date.today()

        count = occurrence_service.auto_confirm_daily_sync(sync_db, organization_id, today)
        assert count == 1

        occurrence = sync_db.execute(
            select(models.LessonOccurrence).where(
                models.LessonOccurrence.schedule_output_id == full_setup["schedule_output_id"]
            )
        ).scalar_one_or_none()

        assert occurrence is not None
        assert occurrence.status == LessonOccurrenceStatus.GIVEN
        assert occurrence.hours_given == pytest.approx(2.0)

    def test_auto_confirm_skips_existing_occurrence(self, sync_db, full_setup):
        organization_id = full_setup["organization_id"]
        today = date.today()
        output_id = full_setup["schedule_output_id"]

        manual = models.LessonOccurrence(
            organization_id=organization_id,
            schedule_output_id=output_id, date=today,
            status=LessonOccurrenceStatus.GAP, hours_given=0.0,
        )
        sync_db.add(manual)
        sync_db.commit()

        count = occurrence_service.auto_confirm_daily_sync(sync_db, organization_id, today)
        assert count == 0

        all_occurrences = list(
            sync_db.execute(
                select(models.LessonOccurrence).where(
                    models.LessonOccurrence.schedule_output_id == output_id
                )
            ).scalars()
        )
        assert len(all_occurrences) == 1
        assert all_occurrences[0].status == LessonOccurrenceStatus.GAP

    def test_get_debts_empty_when_no_gaps(self, sync_db, full_setup):
        organization_id = full_setup["organization_id"]
        result = occurrence_service.get_debts_sync(sync_db, organization_id)
        assert result.total_gaps == 0
        assert result.total_hours_owed == pytest.approx(0.0)
        assert result.total_gaps_overdue == 0
        assert result.total_hours_owed_overdue == pytest.approx(0.0)
        assert result.items == []

    def test_get_debts_counts_gap_occurrences(self, sync_db, full_setup):
        organization_id = full_setup["organization_id"]
        today = date.today()
        output_id = full_setup["schedule_output_id"]

        gap = models.LessonOccurrence(
            organization_id=organization_id,
            schedule_output_id=output_id, date=today,
            status=LessonOccurrenceStatus.GAP, hours_given=2.0,
        )
        sync_db.add(gap)
        sync_db.commit()

        result = occurrence_service.get_debts_sync(sync_db, organization_id)
        assert result.total_gaps == 1
        assert result.total_hours_owed == pytest.approx(2.0)
        assert result.total_gaps_overdue == 1
        assert result.total_hours_owed_overdue == pytest.approx(2.0)
        assert len(result.items) == 1

    def test_get_occurrence_returns_none_for_wrong_org(self, sync_db, full_setup):
        """Verify cross-tenant isolation: different org_id returns None."""
        occurrence_id = full_setup.get("occurrence_id")
        if occurrence_id is None:
            # Create an occurrence first
            occurrence, _ = occurrence_service.create_occurrence_from_block_sync(
                sync_db, full_setup["organization_id"], full_setup["schedule_output_id"],
            )
            occurrence_id = occurrence.id
        result = occurrence_service.get_occurrence_sync(sync_db, occurrence_id, organization_id=9999)
        assert result is None
