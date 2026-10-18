"""A teacher with a presence minimum is constructed without the exact model.

Iris rule: at least three hours per presence, a free lunch and at most one hour
of gap. Greedy construction must book a whole presence run, so the constructive
route (and the adaptive recovery that relies on it) completes the schedule.
"""

from dataclasses import replace
from datetime import time

from app.scheduler.domain.candidate import LunchRule, SchedulingStrategy, TeacherPresenceRule
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.infrastructure import search
from app.scheduler.infrastructure.constructive import construct_schedule
from app.scheduler.infrastructure.search import search_adaptive_schedule
from app.scheduler.lab.recovery import laboratory_policy
from app.scheduler.lab.typology import build_typology_fixture

IRIS_TEACHER_ID = 1001
LUNCH_RULE = LunchRule(time(12), time(14), 60)


def iris_rule(*, lunch_required: bool) -> TeacherPresenceRule:
    return TeacherPresenceRule(
        teacher_id=IRIS_TEACHER_ID,
        lunch_required=lunch_required,
        minimum_minutes=180,
        max_gap_minutes=60,
    )


def test_a_presence_with_a_lunch_break_books_a_full_run_in_construction():
    fixture = build_typology_fixture(12)
    snapshot = replace(
        fixture.snapshot, teacher_presence=(iris_rule(lunch_required=True),), lunch_rule=LUNCH_RULE
    )

    candidate = construct_schedule(snapshot, fixture.periods)

    assert candidate is not None
    assert validate_candidate(snapshot, candidate).valid is True


def test_a_presence_without_lunch_books_a_full_run_in_construction():
    fixture = build_typology_fixture(12)
    snapshot = replace(
        fixture.snapshot, teacher_presence=(iris_rule(lunch_required=False),), lunch_rule=LUNCH_RULE
    )

    candidate = construct_schedule(snapshot, fixture.periods)

    assert candidate is not None
    assert validate_candidate(snapshot, candidate).valid is True


def test_adaptive_recovery_repairs_a_presence_rule_without_the_exact_model(monkeypatch):
    fixture = build_typology_fixture(12)
    snapshot = replace(
        fixture.snapshot,
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        baseline_lessons=fixture.witness.lessons,
        teacher_presence=(iris_rule(lunch_required=True),),
        lunch_rule=LUNCH_RULE,
    )

    def exact_model_must_not_run(*_args, **_kwargs):
        raise AssertionError("The exact placement model must not run.")

    monkeypatch.setattr(search, "solve_placement", exact_model_must_not_run)

    outcome = search_adaptive_schedule(
        snapshot,
        fixture.periods,
        fixture.witness,
        laboratory_policy(snapshot),
        time_limit_seconds=300,
        stop_at_first_complete=True,
    )

    assert outcome.status == "COMPLETE"
    assert validate_candidate(snapshot, outcome.candidate).valid is True
