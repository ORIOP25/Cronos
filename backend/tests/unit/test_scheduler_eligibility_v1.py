from datetime import date

import pytest

from app.scheduler.domain.eligibility import (
    EligibilityFacts,
    EligibilityReason,
    generation_eligibility,
)


def facts(**overrides):
    values = {
        "school_today": date(2026, 9, 28),
        "planning_revision": 4,
        "last_completed_planning_revision": 4,
        "last_successful_generation_date": date(2026, 9, 1),
        "last_attempt_incomplete": False,
        "active_job": False,
    }
    return EligibilityFacts(**(values | overrides))


def test_t21_normal_execution_does_not_unlock_generation_but_planning_change_does():
    # input_revision is intentionally absent: normal execution cannot create this reason.
    assert not generation_eligibility(facts()).can_generate
    changed = generation_eligibility(facts(planning_revision=5))

    assert changed.can_generate
    assert changed.reasons == (EligibilityReason.PLANNING_CHANGE,)


def test_t22_renewal_begins_after_28_local_calendar_days():
    not_yet = generation_eligibility(facts())
    eligible = generation_eligibility(facts(school_today=date(2026, 9, 29)))

    assert not not_yet.can_generate
    assert eligible.reasons == (EligibilityReason.PERIODIC_RENEWAL,)


def test_failure_allows_retry_without_resetting_renewal_clock():
    failed = generation_eligibility(facts(last_attempt_incomplete=True))
    completed = generation_eligibility(
        facts(
            school_today=date(2026, 9, 29),
            last_successful_generation_date=date(2026, 9, 29),
        )
    )

    assert failed.reasons == (EligibilityReason.RETRY_INCOMPLETE,)
    assert not completed.can_generate


def test_first_generation_and_active_job_are_distinct():
    first = generation_eligibility(
        facts(last_completed_planning_revision=None, last_successful_generation_date=None)
    )
    queued = generation_eligibility(
        facts(
            last_completed_planning_revision=None,
            last_successful_generation_date=None,
            active_job=True,
        )
    )

    assert first.reasons == (EligibilityReason.FIRST_GENERATION,)
    assert first.can_generate
    assert queued.reasons == (EligibilityReason.FIRST_GENERATION,)
    assert not queued.can_generate
    assert queued.blocker == EligibilityReason.ACTIVE_JOB


def test_rejection_without_new_data_has_no_new_reason():
    assert not generation_eligibility(facts()).can_generate


def test_clock_and_revision_regression_are_rejected():
    with pytest.raises(ValueError):
        generation_eligibility(facts(school_today=date(2026, 8, 31)))
    with pytest.raises(ValueError):
        generation_eligibility(facts(planning_revision=3))
