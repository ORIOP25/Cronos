"""W06 solver evidence: AdaptiveRecovery over the reabrir master/detail search."""

from dataclasses import replace
from datetime import date, time

import pytest

from app.scheduler.composition import repair_published_schedule
from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import (
    CandidateSchedule,
    ScheduledLesson,
    SchedulingStrategy,
)
from app.scheduler.domain.diagnostics import DiagnosisCode
from app.scheduler.domain.oracle import enumerate_candidates
from app.scheduler.domain.projection import ModuleSlice
from app.scheduler.domain.recovery import (
    RecoveryPolicy,
    recovery_vector,
)
from app.scheduler.infrastructure.placement_model import (
    _scope_cache_key,
    _window_scopes,
    solve_placement,
)
from app.scheduler.lab.fixtures import (
    AssignmentSpec,
    FixtureSpec,
    build_fixture,
    build_snapshot,
)
from tests.unit.test_scheduler_w04_w05_regressions_v1 import ORIGIN

TZ = "Europe/Lisbon"
DAY0, DAY1, DAY2 = (
    date(2026, 9, 21),
    date(2026, 9, 22),
    date(2026, 9, 23),
)
PERIODS = (
    (DAY0, time(9), time(10)),
    (DAY1, time(9), time(10)),
    (DAY2, time(9), time(10)),
)
PERIODS_NORM = tuple(normalize_period(day, start, end, TZ) for day, start, end in PERIODS)
GRID = ((0, time(9), time(10)), (1, time(9), time(10)), (2, time(9), time(10)))

POLICY = RecoveryPolicy(
    version="laboratory-example",
    daily_slopes=tuple(range(1, 12)),
    disruption_weight=1,
    move_cost=10,
    insert_cost=12,
    remove_cost=15,
    room_change_cost=3,
    urgency_horizon_days=4,
    urgency_slope=1,
    recurrence_penalty=1,
)


def _spec(*, strategy=SchedulingStrategy.ADAPTIVE_RECOVERY, **overrides) -> FixtureSpec:
    values = dict(
        strategy=strategy,
        origin=ORIGIN,
        preferred_end_date=date(2026, 10, 2),
        hard_end_date=date(2026, 10, 16),
        timezone_name=TZ,
        grid_slots=GRID,
        periods=PERIODS,
        assignments=(
            AssignmentSpec(1, 7, (60,), (500,)),
            AssignmentSpec(2, 8, (60,), (501,)),
        ),
    )
    values.update(overrides)
    return FixtureSpec(**values)


def _baseline_lesson(identity, assignment_id, when, room, teacher):
    return ScheduledLesson(
        lesson_id=identity,
        assignment_id=assignment_id,
        period=when,
        room_id=room,
        credit_minutes=when.duration_minutes,
        slices=(ModuleSlice(identity, 1, 0, when.duration_minutes),),
        teacher_id=teacher,
    )


def test_presence_rules_keep_the_protected_lesson_unchanged():
    from app.scheduler.domain.candidate import TeacherPresenceRule

    spec = _spec(unavailable=(("teacher", 8, (DAY1, time(9), time(10))),))
    snapshot = replace(
        build_snapshot(spec),
        teacher_presence=(
            TeacherPresenceRule(
                teacher_id=7, lunch_required=False, minimum_minutes=60, max_gap_minutes=600
            ),
        ),
    )
    frozen = _baseline_lesson(1, 1, normalize_period(DAY0, time(9), time(10), TZ), 500, 7)
    protected = replace(snapshot, protected_lessons=(frozen,), protected_dates=frozenset({DAY0}))

    result = repair_published_schedule(
        protected, PERIODS_NORM, CandidateSchedule((frozen,)), POLICY, time_limit_seconds=5
    )

    assert result.outcome == "COMPLETE"
    assert frozen in result.candidate.lessons
    assert result.report is not None and result.report.valid


def test_recovery_respects_a_teacher_presence_minimum():
    from app.scheduler.domain.candidate import TeacherPresenceRule
    from app.scheduler.domain.candidate_validation import validate_candidate

    spec = _spec(
        assignments=(
            AssignmentSpec(1, 7, (120,), (500,)),
            AssignmentSpec(2, 8, (60,), (501,)),
        ),
        periods=(
            (DAY0, time(9), time(10)),
            (DAY0, time(10), time(11)),
            (DAY1, time(9), time(10)),
        ),
        grid_slots=((0, time(9), time(10)), (0, time(10), time(11)), (1, time(9), time(10))),
    )
    snapshot = replace(
        build_snapshot(spec),
        teacher_presence=(
            TeacherPresenceRule(
                teacher_id=7, lunch_required=False, minimum_minutes=120, max_gap_minutes=600
            ),
        ),
    )
    periods = tuple(normalize_period(day, start, end, TZ) for day, start, end in spec.periods)

    result = repair_published_schedule(
        snapshot, periods, CandidateSchedule(()), POLICY, time_limit_seconds=10
    )

    assert result.outcome == "COMPLETE"
    assert result.candidate is not None
    assert validate_candidate(snapshot, result.candidate).valid
    # The teacher's only two lessons land on the same day, meeting the minimum.
    teacher_lessons = [row for row in result.candidate.lessons if row.assignment_id == 1]
    assert len({row.period.school_date for row in teacher_lessons}) == 1


def test_t20_a_teacher_reassignment_is_repaired_instead_of_kept():
    spec = _spec(
        unavailable=(("teacher", 8, (DAY0, time(9), time(10))),),
        assignments=(
            AssignmentSpec(1, 8, (60,), (500,)),
            AssignmentSpec(2, 9, (60,), (501,)),
        ),
    )
    snapshot = build_snapshot(spec)
    baseline = CandidateSchedule(
        (_baseline_lesson(1, 1, normalize_period(DAY0, time(9), time(10), TZ), 500, 7),)
    )

    result = repair_published_schedule(
        snapshot, PERIODS_NORM, baseline, POLICY, time_limit_seconds=5
    )

    assert result.outcome == "COMPLETE"
    assert result.report is not None and result.report.valid
    assert result.baseline is not None and not result.baseline.valid
    assert DiagnosisCode.BASELINE_STALE in {row.code for row in result.diagnoses}
    placed = [row for row in result.candidate.lessons if row.assignment_id == 1]
    assert placed and all(row.period.school_date != DAY0 for row in placed)


def test_a_stale_baseline_is_reported_even_when_repair_succeeds():
    stray = _spec(
        assignments=(
            AssignmentSpec(1, 7, (60,), (500,)),
            AssignmentSpec(2, 8, (60,), (501,)),
        )
    )
    base_fixture = build_fixture("stray-base", stray)
    baseline = CandidateSchedule(base_fixture.witness.lessons[:1])

    result = repair_published_schedule(
        base_fixture.snapshot, base_fixture.periods, baseline, POLICY, time_limit_seconds=5
    )

    assert result.outcome == "COMPLETE"
    assert result.baseline is not None
    assert result.baseline.missing_minutes == 60


def test_a_local_infeasibility_reopens_weeks_and_finds_the_witness():
    """C04: the only joint position needs moving an earlier lesson."""
    next_week = date(2026, 9, 28)
    spec = _spec(
        grid_slots=((0, time(9), time(10)), (0, time(9, 30), time(10, 30))),
        periods=(
            (DAY0, time(9), time(10)),
            (DAY0, time(9, 30), time(10, 30)),
            (next_week, time(9), time(10)),
        ),
        assignments=(
            AssignmentSpec(1, 7, (60,), (500,)),
            AssignmentSpec(2, 7, (60,), (501,)),
        ),
    )
    snapshot = build_snapshot(spec)
    baseline = CandidateSchedule(
        (
            _baseline_lesson(1, 1, normalize_period(DAY0, time(9), time(10), TZ), 500, 7),
            _baseline_lesson(2, 2, normalize_period(DAY0, time(9, 30), time(10, 30), TZ), 501, 7),
        )
    )

    periods = tuple(normalize_period(day, start, end, TZ) for day, start, end in spec.periods)
    result = repair_published_schedule(snapshot, periods, baseline, POLICY, time_limit_seconds=10)

    assert result.outcome == "COMPLETE"
    assert result.report is not None and result.report.valid
    assert result.evidence is not None and result.evidence.rounds >= 2
    weeks = {(row.period.school_date - ORIGIN).days // 7 for row in result.candidate.lessons}
    assert weeks == {0, 1}


@pytest.mark.parametrize("seed", range(6))
def test_the_repair_matches_the_enumerated_adaptive_optimum(seed):
    """T15-T18 at solver level: the returned vector is the enumerated minimum.

    Each seed blocks a real class, teacher or room at a real period: classes
    1-2, teachers 7-8 and rooms 500-501 are the identifiers of the fixture.
    """
    base = build_fixture("adaptive-base", _spec())
    baseline = base.witness
    kind = ("class", "teacher", "room")[seed % 3]
    resource_id = {
        "class": (1, 2)[(seed // 3) % 2],
        "teacher": (7, 8)[(seed // 3) % 2],
        "room": (500, 501)[(seed // 3) % 2],
    }[kind]
    unavailable = ((kind, resource_id, PERIODS[seed % len(PERIODS)]),)
    perturbed = build_fixture("adaptive-perturbed-" + str(seed), _spec(unavailable=unavailable))

    result = repair_published_schedule(
        perturbed.snapshot, perturbed.periods, baseline, POLICY, time_limit_seconds=10
    )

    oracle = enumerate_candidates(perturbed.snapshot, perturbed.periods)
    assert oracle.feasible
    best = min(
        recovery_vector(perturbed.snapshot, baseline, candidate, POLICY)
        for candidate in oracle.candidates
    )
    assert result.outcome == "COMPLETE"
    assert result.report is not None and result.report.valid
    assert recovery_vector(perturbed.snapshot, baseline, result.candidate, POLICY) == best


def test_the_repair_cache_is_bound_to_the_baseline_salt():
    fixture = build_fixture("cache-salt", _spec())
    cache = {}

    first = solve_placement(
        fixture.snapshot, fixture.periods, time_limit_seconds=5, reuse=cache, cache_salt="a"
    )
    second = solve_placement(
        fixture.snapshot, fixture.periods, time_limit_seconds=5, reuse=cache, cache_salt="a"
    )
    third = solve_placement(
        fixture.snapshot, fixture.periods, time_limit_seconds=5, reuse=cache, cache_salt="b"
    )

    assert first.status == second.status == third.status == "COMPLETE"
    assert any(stage.reused for stage in second.evidence.stages)
    assert all(not stage.reused for stage in third.evidence.stages)


def test_the_cache_key_changes_with_the_salt():
    from app.scheduler.infrastructure.annual_model import plan_annual_quotas

    fixture = build_fixture("cache-key", _spec())
    plan = plan_annual_quotas(fixture.snapshot, fixture.periods, time_limit_seconds=5)
    assert plan.distribution is not None
    window = _window_scopes(fixture.snapshot, fixture.periods, plan.distribution)[0]

    assert _scope_cache_key(window, "a") != _scope_cache_key(window, "b")


def test_an_interrupted_repair_stage_is_never_certified(monkeypatch):
    from app.scheduler.infrastructure import placement_model

    spec = _spec(unavailable=(("room", 500, (DAY0, time(9), time(10))),))
    fixture = build_fixture("repair-freeze", spec)
    stale = CandidateSchedule(
        (_baseline_lesson(1, 1, normalize_period(DAY0, time(9), time(10), TZ), 500, 7),)
    )
    original = placement_model._solve_scope

    def with_safety(state, **kwargs):
        status, selections, records, _stop = original(state, **kwargs)
        return status, selections, records, placement_model.STOP_SAFETY

    monkeypatch.setattr(placement_model, "_solve_scope", with_safety)

    result = repair_published_schedule(
        fixture.snapshot,
        fixture.periods,
        stale,
        POLICY,
        time_limit_seconds=10,
    )

    assert result.outcome == "COMPLETE"
    assert result.evidence is not None
    assert result.evidence.certified_stages == 0


def test_repair_respects_the_editable_frontier_and_protected_dates():
    spec = _spec(protected_dates=frozenset({DAY0}))
    snapshot = build_snapshot(spec)
    baseline = CandidateSchedule(
        (
            _baseline_lesson(1, 1, normalize_period(DAY0, time(9), time(10), TZ), 500, 7),
            _baseline_lesson(2, 2, normalize_period(DAY1, time(9), time(10), TZ), 501, 8),
        )
    )

    result = repair_published_schedule(
        snapshot, PERIODS_NORM, baseline, POLICY, time_limit_seconds=5
    )

    assert result.outcome == "COMPLETE"
    assert result.report is not None and result.report.valid
    for lesson in result.candidate.lessons:
        assert lesson.period.school_date != DAY0


def test_repair_uses_the_global_room_matching_after_movements():
    spec = _spec(
        assignments=(
            AssignmentSpec(1, 7, (120,), (500, 501)),
            AssignmentSpec(2, 8, (60,), (501,)),
        ),
        unavailable=(("room", 500, (DAY0, time(9), time(10))),),
    )
    snapshot = build_snapshot(spec)
    baseline = CandidateSchedule(
        (
            _baseline_lesson(1, 1, normalize_period(DAY0, time(9), time(10), TZ), 500, 7),
            _baseline_lesson(2, 1, normalize_period(DAY1, time(9), time(10), TZ), 500, 7),
        )
    )

    result = repair_published_schedule(
        snapshot, PERIODS_NORM, baseline, POLICY, time_limit_seconds=10
    )

    assert result.outcome == "COMPLETE"
    assert result.report is not None and result.report.valid
    occupied: set[tuple] = set()
    for lesson in result.candidate.lessons:
        key = (lesson.room_id, lesson.period.start_utc, lesson.period.end_utc)
        assert key not in occupied
        occupied.add(key)


def test_the_repair_prunes_by_the_incumbent_week_allowing_the_same_week(monkeypatch):
    from app.scheduler.infrastructure import search

    base = build_fixture("prune-base", _spec())
    baseline = base.witness
    spec = _spec(
        unavailable=(("teacher", 7, (DAY0, time(9), time(10))),),
    )
    fixture = build_fixture("prune-repair", spec)
    limits: list[int | None] = []
    original = search.plan_annual_quotas

    def recording(*args, **kwargs):
        limits.append(kwargs.get("latest_week_limit"))
        return original(*args, **kwargs)

    monkeypatch.setattr(search, "plan_annual_quotas", recording)

    result = repair_published_schedule(
        fixture.snapshot, fixture.periods, baseline, POLICY, time_limit_seconds=10
    )

    assert result.outcome == "COMPLETE"
    assert result.evidence is not None
    incumbent_week = result.evidence.relaxation_incumbent or 0
    assert limits and limits[0] is None
    assert all(limit is not None for limit in limits[1:])
    assert all(limit >= incumbent_week for limit in limits[1:])


def test_stabilization_returns_a_lesson_to_its_published_position():
    from time import monotonic

    from app.scheduler.infrastructure.search import _SearchProfile, _stabilize_recovery

    base = build_fixture("stability-base", _spec())
    snapshot = replace(
        base.snapshot,
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        baseline_lessons=base.witness.lessons,
    )
    target = next(lesson for lesson in base.witness.lessons if lesson.assignment_id == 1)
    moved = CandidateSchedule(
        tuple(
            replace(
                lesson,
                period=PERIODS_NORM[2] if lesson.lesson_id == target.lesson_id else lesson.period,
                source_lesson_id=lesson.lesson_id,
            )
            for lesson in base.witness.lessons
        )
    )
    profile = _SearchProfile(baseline=base.witness, policy=POLICY)

    stabilized = _stabilize_recovery(
        snapshot, PERIODS_NORM, profile, moved, deadline=monotonic() + 5
    )

    by_source = {
        lesson.source_lesson_id: lesson
        for lesson in stabilized.lessons
        if lesson.source_lesson_id is not None
    }
    assert by_source[target.lesson_id].period == target.period
    assert recovery_vector(snapshot, base.witness, stabilized, POLICY) < recovery_vector(
        snapshot, base.witness, moved, POLICY
    )


def test_an_explicit_cancellation_never_returns_a_partial_repair():
    fixture = build_fixture("repair-cancel", _spec())

    result = repair_published_schedule(
        fixture.snapshot,
        fixture.periods,
        fixture.witness,
        POLICY,
        should_cancel=lambda: True,
        time_limit_seconds=5,
    )

    assert result.outcome == "CANCELLED"
    assert result.candidate is None
    assert result.budget is not None


def test_the_exploration_controller_can_finish_with_an_explicit_reason():
    from app.scheduler.domain.stop import ExplorationPolicy

    spec = _spec(unavailable=(("room", 500, (DAY0, time(9), time(10))),))
    fixture = build_fixture("repair-controller", spec)
    stale = CandidateSchedule(
        (_baseline_lesson(1, 1, normalize_period(DAY0, time(9), time(10), TZ), 500, 7),)
    )
    exploration = ExplorationPolicy(
        version="laboratory-example",
        minimum_exploration_seconds=0.0,
        gain_window_seconds=0.0,
        minimum_significant_gain_days=1,
        corpus_expected_gain_days=0,
        minimum_solutions=1,
    )

    result = repair_published_schedule(
        fixture.snapshot,
        fixture.periods,
        stale,
        POLICY,
        exploration=exploration,
        time_limit_seconds=10,
    )

    assert result.outcome == "COMPLETE"
    assert result.evidence is not None
    assert result.evidence.stop_reason == "LOW_EXPECTED_RETURN"
