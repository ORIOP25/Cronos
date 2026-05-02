import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.db.database import ASYNC_DB_URL, Base
from app.services import occurrence_service
from app.services.operational_seed_service import seed_operational_scenarios_sync

SYNC_TEST_URL = ASYNC_DB_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
sync_test_engine = create_engine(SYNC_TEST_URL, echo=False)
SyncTestSession = sessionmaker(bind=sync_test_engine, autocommit=False, autoflush=False)


def _reset_schema() -> None:
    Base.metadata.drop_all(bind=sync_test_engine)
    Base.metadata.create_all(bind=sync_test_engine)


def test_operational_seed_covers_required_step6_scenarios():
    _reset_schema()
    db = SyncTestSession()

    try:
        payload = seed_operational_scenarios_sync(db)
        signature = payload["signature"]
        runtime = payload["runtime"]

        assert signature["organization_count"] == 2
        assert signature["scenario_codes"] == [
            "multi_eligible_substitution",
            "no_eligible_fallback_gap",
        ]

        multi_recommendations = occurrence_service.get_substitute_recommendations_sync(
            db,
            organization_id=runtime["org_a_id"],
            occurrence_id=runtime["multi_eligible_occurrence_id"],
        )
        assert len(multi_recommendations) >= 2
        assert multi_recommendations[0].teacher_id == runtime["expected_first_recommendation_teacher_id"]

        no_eligible_recommendations = occurrence_service.get_substitute_recommendations_sync(
            db,
            organization_id=runtime["org_a_id"],
            occurrence_id=runtime["no_eligible_occurrence_id"],
        )
        assert no_eligible_recommendations == []

        no_eligible_occurrence = db.get(models.LessonOccurrence, runtime["no_eligible_occurrence_id"])
        assert no_eligible_occurrence is not None
        assert no_eligible_occurrence.status == models.LessonOccurrenceStatus.GAP

        with pytest.raises(occurrence_service.OccurrenceServiceError) as exc_info:
            occurrence_service.get_substitute_recommendations_sync(
                db,
                organization_id=runtime["org_b_id"],
                occurrence_id=runtime["multi_eligible_occurrence_id"],
            )
        assert exc_info.value.status_code == 404
    finally:
        db.close()


def test_operational_seed_is_reproducible_across_repeated_runs():
    signatures = []

    for _ in range(3):
        _reset_schema()
        db = SyncTestSession()
        try:
            payload = seed_operational_scenarios_sync(db)
            signatures.append(payload["signature"])
        finally:
            db.close()

    assert signatures[0] == signatures[1] == signatures[2]
