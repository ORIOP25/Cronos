"""Fast, autonomous oracle for the construction refactor (S1).

The frozen candidate below is the observable contract of the base commit. It is
a literal taken from the technical specification, never regenerated from the
current output. This file reads no artifact and no filesystem.
"""

from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from time import monotonic

import pytest

from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import (
    CandidateSchedule,
    GridSlot,
    PlanningSnapshot,
    ScheduledLesson,
    SchedulingStrategy,
)
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.domain.capacity import residual_minutes
from app.scheduler.domain.priorities import DEFAULT_LEVELS, PriorityWeights
from app.scheduler.domain.projection import ModuleSlice
from app.scheduler.domain.serialization import candidate_digest, candidate_to_dict, payload_digest
from app.scheduler.infrastructure.constructive import construct_schedule
from app.scheduler.infrastructure.recovery_construction import construct_recovery
from app.scheduler.lab.fixtures import AssignmentSpec, FixtureSpec, build_snapshot

TIMEZONE = "Europe/Lisbon"

SPEC = FixtureSpec(
    strategy=SchedulingStrategy.COMPLETE_GENERATION,
    origin=date(2026, 9, 21),
    preferred_end_date=date(2026, 10, 30),
    hard_end_date=date(2026, 11, 30),
    timezone_name=TIMEZONE,
    grid_slots=((0, time(9), time(10)), (2, time(9), time(10))),
    periods=(
        (date(2026, 9, 21), time(9), time(10)),
        (date(2026, 9, 23), time(9), time(10)),
    ),
    assignments=(AssignmentSpec(1, 100, (100,), (500, 501)),),
)
BASE_PERIODS = tuple(
    normalize_period(day, start, end, SPEC.timezone_name) for day, start, end in SPEC.periods
)
BASE_TYPED_CANDIDATE = CandidateSchedule(
    lessons=(
        ScheduledLesson(
            lesson_id=1_000_001,
            assignment_id=1,
            period=BASE_PERIODS[0],
            room_id=500,
            credit_minutes=60,
            slices=(ModuleSlice(1_000_001, 1, 0, 60),),
        ),
        ScheduledLesson(
            lesson_id=1_000_002,
            assignment_id=1,
            period=BASE_PERIODS[1],
            room_id=500,
            credit_minutes=40,
            slices=(ModuleSlice(1_000_002, 1, 60, 40),),
        ),
    )
)

# Exact typed projection, in lesson order, with only the slices sorted. Values
# come from the S1 specification: two lessons, assignment 1, room 500, credits
# 60/40, one module (1) with offsets 0/60, and no source, teacher or classes.
BASE_LESSONS = [
    [
        1_000_001,
        1,
        ["2026-09-21", "09:00", "10:00", TIMEZONE],
        500,
        60,
        [[1, 0, 60]],
        None,
        None,
        None,
    ],
    [
        1_000_002,
        1,
        ["2026-09-23", "09:00", "10:00", TIMEZONE],
        500,
        40,
        [[1, 60, 40]],
        None,
        None,
        None,
    ],
]
BASE_CANDIDATE = {"lessons": BASE_LESSONS}
WEIGHTED_TYPED_CANDIDATE = CandidateSchedule(
    lessons=tuple(replace(lesson, room_id=501) for lesson in BASE_TYPED_CANDIDATE.lessons)
)
WEIGHTED_CANDIDATE = {"lessons": [row[:3] + [501] + row[4:] for row in BASE_LESSONS]}


def base_inputs() -> tuple[PlanningSnapshot, tuple]:
    snapshot = build_snapshot(SPEC)
    periods = tuple(
        normalize_period(day, start, end, SPEC.timezone_name) for day, start, end in SPEC.periods
    )
    return snapshot, periods


def base_candidate(weights: PriorityWeights | None = None):
    snapshot, periods = base_inputs()
    return construct_schedule(snapshot, periods, weights=weights, deadline=None)


@pytest.mark.parametrize(
    "weights,expected,projection",
    (
        (None, BASE_TYPED_CANDIDATE, BASE_CANDIDATE),
        (PriorityWeights(DEFAULT_LEVELS), WEIGHTED_TYPED_CANDIDATE, WEIGHTED_CANDIDATE),
    ),
    ids=("unweighted", "default-weights"),
)
def test_construction_candidate_matches_base_fixture(weights, expected, projection):
    snapshot, _periods = base_inputs()
    candidate = base_candidate(weights)

    assert candidate is not None
    actual_rooms = [(lesson.lesson_id, lesson.room_id) for lesson in candidate.lessons]
    expected_rooms = [(lesson.lesson_id, lesson.room_id) for lesson in expected.lessons]
    assert candidate == expected, f"rooms actual={actual_rooms} expected={expected_rooms}"
    assert candidate_to_dict(candidate) == projection
    assert candidate_digest(candidate) == payload_digest(projection)
    assert validate_candidate(snapshot, candidate).valid is True


def test_projector_detects_slice_order_only_difference():
    """Typed equality preserves raw slice order; the projection and digest sort it."""
    period = normalize_period(date(2026, 9, 21), time(9), time(10), TIMEZONE)
    first = ScheduledLesson(
        lesson_id=1,
        assignment_id=1,
        period=period,
        room_id=500,
        credit_minutes=50,
        slices=(
            ModuleSlice(1, 1, 0, 20),
            ModuleSlice(1, 2, 0, 30),
        ),
    )
    reversed_slices = replace(first, slices=tuple(reversed(first.slices)))
    original = CandidateSchedule(lessons=(first,))
    reordered = CandidateSchedule(lessons=(reversed_slices,))

    assert original != reordered
    assert candidate_to_dict(original) == candidate_to_dict(reordered)
    assert candidate_digest(original) == candidate_digest(reordered)


@pytest.mark.parametrize(
    "cancelled,deadline,generation_events,recovery_events",
    (
        (False, 2, ["cancel", "clock"], ["clock", "cancel"]),
        (True, 2, ["cancel"], ["clock", "cancel"]),
        (False, 0, ["cancel", "clock"], ["clock"]),
    ),
)
def test_construction_and_recovery_keep_interruption_short_circuit_order(
    monkeypatch, cancelled, deadline, generation_events, recovery_events
):
    from app.scheduler.infrastructure import constructive, recovery_construction

    events = []

    def cancel():
        events.append("cancel")
        return cancelled

    def clock():
        events.append("clock")
        return 1

    monkeypatch.setattr(constructive, "monotonic", clock)
    monkeypatch.setattr(recovery_construction, "monotonic", clock)
    assert constructive._interrupted(deadline, cancel) is (cancelled or deadline == 0)
    assert events == generation_events
    events.clear()
    assert recovery_construction._interrupted(deadline, cancel) is (cancelled or deadline == 0)
    assert events == recovery_events


@pytest.mark.parametrize("change", ("order", "room", "value"))
def test_construction_oracle_detects_candidate_mutations(change):
    lessons = BASE_TYPED_CANDIDATE.lessons
    if change == "order":
        mutated = CandidateSchedule(tuple(reversed(lessons)))
    else:
        field = {"room_id": 501} if change == "room" else {"credit_minutes": 59}
        mutated = CandidateSchedule((replace(lessons[0], **field), lessons[1]))
    assert mutated != BASE_TYPED_CANDIDATE
    assert candidate_digest(mutated) != payload_digest(BASE_CANDIDATE)


def test_construction_campaign_profiles_cover_c01_to_c23():
    from tests._support.construction_snapshot import campaign_profiles

    profiles = campaign_profiles()
    assert tuple(profiles) == tuple(f"C{index:02d}" for index in range(1, 24))
    assert profiles["C01"] == PriorityWeights(DEFAULT_LEVELS)
    assert profiles["C03"].teacher_gaps == 4
    assert profiles["C17"].weekly_stability == 4
    assert profiles["C18"].subject_pace == 0
    assert profiles["C21"].class_gaps == 0
    assert profiles["C21"].class_same_room == 4
    assert all(weights.finish_early == 4 for weights in profiles.values())
    assert profiles["C20"].update_stability == 2


def test_construction_campaign_records_immutable_quality(monkeypatch):
    from app.scheduler.domain.quality import SearchEvidence, measure_initial_quality
    from app.scheduler.domain.results import SearchOutcome
    from tests._support import construction_snapshot

    snapshot, _periods = base_inputs()
    frozen = SearchOutcome(
        "COMPLETE",
        BASE_TYPED_CANDIDATE,
        2,
        SearchEvidence("FIXTURE", (), 0, "FIXTURE"),
        "Frozen fixture",
        0.0,
        {},
        measure_initial_quality(snapshot, BASE_TYPED_CANDIDATE),
    )
    monkeypatch.setattr(construction_snapshot, "campaign_inputs", lambda _profile: base_inputs())
    monkeypatch.setattr(
        construction_snapshot, "search_complete_schedule", lambda *_args, **_kwargs: frozen
    )
    record = construction_snapshot.run_profile("C01")
    assert record["status"] == "COMPLETE"
    assert record["quality"]["completion_dates"] == {"1": "2026-09-23"}
    assert len(record["typed_candidate"]["lessons"]) == 2


def test_construction_updates_do_not_double_count_completed_or_protected_credit():
    """180 = executed 60 + protected 60 + residual 60, over three periods of 60."""
    origin = date(2026, 9, 14)
    periods = tuple(
        normalize_period(origin + timedelta(weeks=offset), time(9), time(10), TIMEZONE)
        for offset in range(3)
    )
    protected = ScheduledLesson(
        lesson_id=1_000_001,
        assignment_id=1,
        period=periods[0],
        room_id=500,
        credit_minutes=60,
        slices=(ModuleSlice(1_000_001, 1, 60, 60),),
    )
    snapshot = PlanningSnapshot(
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        origin=origin,
        preferred_end_date=date(2027, 6, 15),
        hard_end_date=date(2027, 7, 30),
        timezone_name=TIMEZONE,
        grid_slots=(GridSlot(0, time(9), time(10)),),
        assignments=(AssignmentSpec(1, 100, (180,), (500,)).to_assignment(1),),
        executed_minutes={1: {1: 60}},
        blocked_dates=frozenset(),
        unavailable=(),
        protected_lessons=(protected,),
        baseline_lessons=(protected,),
        protected_dates=frozenset({periods[0].school_date}),
        now_utc=datetime(2026, 9, 14, tzinfo=UTC),
        reserved_lesson_ids=frozenset({protected.lesson_id}),
        priority_weights=PriorityWeights(DEFAULT_LEVELS),
    )

    assert residual_minutes(snapshot, 1) == 60
    candidate = construct_recovery(snapshot, periods, deadline=monotonic() + 30, weights=None)

    assert candidate is not None
    assert validate_candidate(snapshot, candidate).valid is True
    assert protected in candidate.lessons
    new = [row for row in candidate.lessons if row.lesson_id != protected.lesson_id]
    assert len(new) == 1
    assert new[0].credit_minutes == 60
    assert [(row.module_id, row.offset_minutes, row.credit_minutes) for row in new[0].slices] == [
        (1, 120, 60)
    ]
    assert sum(row.credit_minutes for row in candidate.lessons) == 120
    assert 60 + sum(row.credit_minutes for row in candidate.lessons) == 180


def test_construction_updates_do_not_read_update_stability():
    from tests._support.construction_snapshot import without_update_stability_reads

    snapshot, periods = base_inputs()
    recovery = replace(snapshot, strategy=SchedulingStrategy.ADAPTIVE_RECOVERY)
    reference = None
    for level in range(5):
        weights = PriorityWeights({**DEFAULT_LEVELS, "update_stability": level})
        with without_update_stability_reads():
            generated = construct_schedule(snapshot, periods, weights=weights)
            retained = construct_recovery(
                recovery, periods, weights=weights, deadline=monotonic() + 30
            )
        assert generated is not None
        assert retained is not None
        assert generated == WEIGHTED_TYPED_CANDIDATE
        assert validate_candidate(snapshot, generated).valid
        assert validate_candidate(recovery, retained).valid
        pair = generated, retained
        if reference is None:
            reference = pair
        assert pair == reference


@pytest.mark.parametrize(
    ("profile", "status", "with_candidate", "accepted"),
    (
        ("C23", "INCONCLUSIVE", False, True),
        ("C23", "COMPLETE", True, False),
        ("C23", "INCONCLUSIVE", True, False),
        ("C01", "INCONCLUSIVE", False, False),
    ),
)
def test_construction_campaign_c23_requires_exact_terminal_outcome(
    monkeypatch, profile, status, with_candidate, accepted
):
    from app.scheduler.domain.quality import SearchEvidence, measure_initial_quality
    from app.scheduler.domain.results import SearchOutcome
    from tests._support import construction_snapshot

    result = SearchOutcome(
        status,
        BASE_TYPED_CANDIDATE if with_candidate else None,
        None,
        SearchEvidence("ANNUAL_QUOTA_SEARCH", (), 0, "SEARCH_STOPPED"),
        "The search stopped before a complete candidate or a proof.",
        0.0,
        {},
        measure_initial_quality(base_inputs()[0], BASE_TYPED_CANDIDATE) if with_candidate else None,
    )
    monkeypatch.setattr(construction_snapshot, "campaign_inputs", lambda _profile: base_inputs())
    monkeypatch.setattr(
        construction_snapshot, "search_complete_schedule", lambda *_args, **_kwargs: result
    )
    if accepted:
        record = construction_snapshot.run_profile(profile)
        assert record["status"] == "INCONCLUSIVE"
        assert record["candidate"] is None
        assert record["typed_candidate"] is None
        assert record["quality"] is None
        assert record["evidence"]["objective_scope"] == "ANNUAL_QUOTA_SEARCH"
        assert record["evidence"]["stop_reason"] == "SEARCH_STOPPED"
    else:
        with pytest.raises(AssertionError):
            construction_snapshot.run_profile(profile)
