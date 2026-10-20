"""Weighted constructive behavior for schedule-priority risk cases."""

from dataclasses import replace
from datetime import date, time, timedelta

from app.scheduler.domain.availability_priority import AvailabilityLedger
from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    GridSlot,
    HomeRoom,
    LunchRule,
    PlanningSnapshot,
    ScheduledLesson,
    SchedulingStrategy,
    Unavailability,
    UnavailableResource,
)
from app.scheduler.domain.priorities import (
    CRITERION_KEYS,
    DEFAULT_LEVELS,
    UNIT_COSTS,
    PriorityWeights,
)
from app.scheduler.domain.priority_value import option_value
from app.scheduler.domain.projection import ModuleRequirement, ModuleSlice
from app.scheduler.infrastructure import constructive
from app.scheduler.infrastructure.constructive import (
    _gap_minutes,
    _gap_option_measure,
    _joined_shift_gain,
    _select_period,
    construct_schedule,
)
from app.scheduler.lab.typology import build_joint_typology_fixture

TZ = "Europe/Lisbon"
MONDAY = date(2026, 9, 14)


def weights(**changes):
    levels = dict(DEFAULT_LEVELS)
    levels.update(changes)
    return PriorityWeights(levels)


def assignment(identity, teacher_id, class_id, minutes=60, room_id=None):
    return Assignment(
        identity,
        (class_id,),
        identity,
        teacher_id,
        frozenset({room_id or identity + 100}),
        (ModuleRequirement(identity * 10, 1, minutes),),
    )


def make_snapshot(assignments, periods, *, soft=(), unavailable=()):
    days = tuple(sorted({period.school_date for period in periods}))
    slots = tuple(
        sorted(
            {
                GridSlot(period.school_date.weekday(), period.start_local, period.end_local)
                for period in periods
            },
            key=lambda slot: (slot.day_of_week, slot.start_local),
        )
    )
    return PlanningSnapshot(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=days[0],
        preferred_end_date=days[-1],
        hard_end_date=days[-1],
        timezone_name=TZ,
        grid_slots=slots,
        assignments=tuple(assignments),
        executed_minutes={},
        blocked_dates=frozenset(),
        unavailable=tuple(unavailable),
        soft_unavailable=tuple(soft),
    )


def period(day_offset, hour):
    day = MONDAY + timedelta(days=day_offset)
    return normalize_period(day, time(hour), time(hour + 1), TZ)


def test_option_value_combines_finish_and_teacher_gap_minutes_as_integer_costs():
    selected = weights(finish_early=1, teacher_gaps=4)

    value = option_value(selected, {"finish_early": 60, "teacher_gaps": -60})

    assert value == 1 * UNIT_COSTS["finish_early"] * 60 - 8 * UNIT_COSTS["teacher_gaps"] * 60
    assert option_value(selected, {"finish_early": 60, "teacher_gaps": 0}) == 60


def test_joint_assignment_weekly_score_counts_each_class_reference(monkeypatch):
    assignments = (
        assignment(1, teacher_id=1, class_id=1),
        assignment(2, teacher_id=2, class_id=2),
        replace(assignment(3, teacher_id=3, class_id=1), class_ids=(1, 2)),
    )
    periods = (period(7, 9), period(7, 10))
    school = make_snapshot(assignments, periods)
    previous_period = period(0, 9)
    reference = CandidateSchedule(
        tuple(
            ScheduledLesson(
                identity,
                identity,
                previous_period,
                identity + 100,
                60,
                (ModuleSlice(identity * 10, 1, 0, 60),),
            )
            for identity in (1, 2)
        )
    )
    levels = dict.fromkeys(CRITERION_KEYS, 0)
    levels["weekly_stability"] = 4
    selected_weights = PriorityWeights(levels)
    captured = {}
    original_select = constructive._select_period

    def capture_scores(options, *, deadline, scores=None):
        period_options = {row.assignment_id for row, _rooms in options}
        if not captured and 3 in period_options:
            captured.update(scores or {})
        return original_select(options, deadline=deadline, scores=scores)

    monkeypatch.setattr(constructive, "_select_period", capture_scores)

    candidate = construct_schedule(
        school,
        periods,
        weekly_reference=reference,
        weights=selected_weights,
    )

    assert candidate is not None
    assert captured[(3, 103)][1] == option_value(selected_weights, {"weekly_stability": -120})


def test_joint_weekly_score_cancels_one_match_and_one_mismatch():
    periods = (period(0, 9),)
    row = replace(assignment(3, teacher_id=3, class_id=1), class_ids=(1, 2))
    school = make_snapshot((row,), periods)

    measures = constructive._option_measures(
        school,
        row,
        periods[0],
        credit=60,
        needed_evitar=frozenset(),
        occupancy={
            ("teacher", 3, MONDAY): [],
            ("class", 1, MONDAY): [],
            ("class", 2, MONDAY): [],
        },
        day_slots=school.grid_slots,
        counts_teacher_single_lessons=False,
        weekly_assignment_ids=(3, 2),
        pace_lag=None,
    )

    assert measures.get("weekly_stability", 0) == 0


def test_gap_priority_counts_empty_grid_slots_and_ignores_lunch_break_minutes():
    slots = (
        GridSlot(0, time(9), time(10)),
        GridSlot(0, time(10), time(11)),
        GridSlot(0, time(11), time(12)),
        GridSlot(0, time(14), time(15)),
        GridSlot(0, time(15), time(16)),
    )

    assert _gap_minutes(((11 * 60, 12 * 60), (14 * 60, 15 * 60)), slots) == 0
    assert _gap_minutes(((11 * 60, 12 * 60), (15 * 60, 16 * 60)), slots) == 60


def test_a_lesson_that_continues_its_neighbour_earns_its_credit_in_the_gap_measure():
    slots = (
        GridSlot(0, time(9), time(10)),
        GridSlot(0, time(10), time(11)),
        GridSlot(0, time(11), time(12)),
        GridSlot(0, time(14), time(15)),
    )
    nine = (9 * 60, 10 * 60)
    ten = (10 * 60, 11 * 60)
    afternoon = (14 * 60, 15 * 60)

    # T06: "aula seguida à anterior" is positive, so an adjacent lesson earns its credit.
    assert _gap_option_measure((nine,), ten, slots, credit=60) == 60
    # A lesson that leaves a gap keeps the gap delta alone (T06, I05).
    assert _gap_option_measure((nine,), afternoon, slots, credit=60) == -120


def test_teacher_gap_option_counts_the_last_lunch_slot_for_a_dispensed_teacher():
    from dataclasses import replace

    from app.scheduler.domain.candidate import TeacherPresenceRule

    grid_intervals = (
        (time(12, 30), time(12, 40)),
        (time(12, 40), time(12, 50)),
        (time(12, 50), time(13, 0)),
        (time(13, 0), time(13, 10)),
        (time(13, 10), time(13, 20)),
    )
    periods = tuple(normalize_period(MONDAY, start, end, TZ) for start, end in grid_intervals)
    row = assignment(1, teacher_id=1, class_id=1)
    school = replace(
        make_snapshot((row,), periods),
        lunch_rule=LunchRule(time(12, 30), time(13, 30), 30),
        teacher_presence=(TeacherPresenceRule(1, lunch_required=False),),
    )
    measures = constructive._option_measures(
        school,
        row,
        periods[2],
        credit=10,
        needed_evitar=frozenset(),
        occupancy={
            ("teacher", 1, MONDAY): [
                (start.hour * 60 + start.minute, end.hour * 60 + end.minute)
                for start, end in (grid_intervals[0], grid_intervals[-1])
            ],
            ("class", 1, MONDAY): [],
        },
        day_slots=school.grid_slots,
        counts_teacher_single_lessons=False,
        weekly_assignment_ids=(),
        pace_lag=None,
    )

    assert measures["teacher_gaps"] == 10


def test_a_special_room_lesson_is_not_penalized_for_an_ineligible_home_room():
    periods = (period(0, 9), period(0, 10))
    row = replace(
        assignment(1, teacher_id=1, class_id=1),
        eligible_room_ids=frozenset({2}),
        needs_special_room=True,
    )
    school = replace(
        make_snapshot((row,), periods),
        home_rooms=(HomeRoom(1, 1),),
    )
    ignored_levels = dict.fromkeys(DEFAULT_LEVELS, 0)
    ignored_levels["finish_early"] = 1
    selected_levels = dict(ignored_levels, class_same_room=4)

    ignored = construct_schedule(school, periods, weights=PriorityWeights(ignored_levels))
    selected = construct_schedule(school, periods, weights=PriorityWeights(selected_levels))

    assert ignored is not None and selected is not None
    assert ignored.lessons[0].period == periods[0]
    assert selected.lessons[0].period == periods[0]


BREAK_GRID = tuple(
    GridSlot(0, time(hour, minute), time(hour + 1, minute))
    for hour, minute in ((9, 0), (10, 10), (11, 20), (12, 30), (13, 30), (14, 40))
)
PILOT_LUNCH = LunchRule(time(12, 30), time(14, 30), 60)


def minutes(hour, minute=0):
    return (hour * 60 + minute, hour * 60 + minute + 60)


def test_a_lesson_after_a_ten_minute_break_still_continues_its_neighbour():
    # A 10-minute break between grid slots does not make the next lesson a new start.
    assert _gap_option_measure((minutes(9),), minutes(10, 10), BREAK_GRID, credit=60) == 60


def test_the_lunch_hour_inside_the_window_is_not_a_free_period():
    morning, afternoon = minutes(11, 20), minutes(14, 40)

    # 12:30 and 13:30 are empty: one hour is lunch, the other is a free period.
    assert _gap_minutes((morning, afternoon), BREAK_GRID, PILOT_LUNCH) == 60
    # With 13:30 taught, the empty 12:30 is the lunch hour itself.
    assert _gap_minutes((morning, minutes(13, 30), afternoon), BREAK_GRID, PILOT_LUNCH) == 0
    # Without a lunch rule both empty hours are free periods, as before.
    assert _gap_minutes((morning, afternoon), BREAK_GRID) == 120


def test_constructive_gap_does_not_discount_lunch_fragments_separated_by_a_lesson():
    grid = tuple(
        GridSlot(0, time(start_hour, start_minute), time(end_hour, end_minute))
        for start_hour, start_minute, end_hour, end_minute in (
            (11, 20, 12, 0),
            (12, 0, 12, 40),
            (12, 40, 12, 50),
            (12, 50, 13, 30),
            (13, 30, 14, 30),
        )
    )
    intervals = (
        (11 * 60 + 20, 12 * 60),
        (12 * 60 + 40, 12 * 60 + 50),
        (13 * 60 + 30, 14 * 60 + 30),
    )

    assert _gap_minutes(intervals, grid, LunchRule(time(12), time(14), 60)) == 80


def test_joining_a_single_lesson_shift_is_rewarded_and_opening_one_is_not_penalised():
    lunch = LunchRule(time(12), time(14), 60)
    nine = (9 * 60, 10 * 60)
    ten = (10 * 60, 11 * 60)
    eleven = (11 * 60, 12 * 60)

    assert _joined_shift_gain((), nine, lunch, lunch_required=True) == 0
    assert _joined_shift_gain((nine,), ten, lunch, lunch_required=True) == 1
    assert _joined_shift_gain((nine, ten), eleven, lunch, lunch_required=True) == 0


def test_all_zero_priorities_spread_one_lesson_every_other_week():
    dates = (0, 7, 14, 21)
    periods = tuple(period(offset, 9) for offset in dates)
    row = assignment(1, teacher_id=1, class_id=1, minutes=120)
    ignored = weights(**{key: 0 for key in DEFAULT_LEVELS})

    result = construct_schedule(make_snapshot((row,), periods), periods, weights=ignored)

    assert [lesson.period.school_date for lesson in result.lessons] == [
        periods[1].school_date,
        periods[3].school_date,
    ]


def test_finish_early_priority_uses_first_two_weeks():
    dates = (0, 7, 14, 21)
    periods = tuple(period(offset, 9) for offset in dates)
    row = assignment(1, teacher_id=1, class_id=1, minutes=120)
    selected = weights(
        finish_early=4, **{key: 0 for key in DEFAULT_LEVELS if key != "finish_early"}
    )

    result = construct_schedule(make_snapshot((row,), periods), periods, weights=selected)

    assert [lesson.period.school_date for lesson in result.lessons] == [
        periods[0].school_date,
        periods[1].school_date,
    ]


def test_necessity_uses_a_strict_pacing_inequality():
    periods = tuple(period(offset, 9) for offset in (0, 7, 14, 21))
    row = assignment(1, teacher_id=1, class_id=1, minutes=120)
    snapshot = make_snapshot((row,), periods)
    ledger = AvailabilityLedger.build(snapshot, {1: periods}, {1: 120})

    assert ledger.is_necessary(row, periods[0]) is False
    assert ledger.is_necessary(row, periods[1]) is True
    ledger.place(row, 60)
    assert ledger.is_necessary(row, periods[2]) is False
    assert ledger.is_necessary(row, periods[3]) is True


def test_teacher_avoid_prefers_the_empty_hour_when_enabled_but_is_ignored_at_zero():
    periods = (period(0, 9), period(0, 10))
    row = assignment(1, teacher_id=1, class_id=1)
    avoid = (Unavailability(UnavailableResource.TEACHER, 1, periods[0]),)
    selected = weights(finish_early=1, teacher_preferences=4)
    ignored = weights(finish_early=1, teacher_preferences=0)

    preferred_result = construct_schedule(
        make_snapshot((row,), periods, soft=avoid), periods, weights=selected
    )
    ignored_result = construct_schedule(
        make_snapshot((row,), periods, soft=avoid), periods, weights=ignored
    )

    assert preferred_result.lessons[0].period == periods[1]
    assert ignored_result.lessons[0].period == periods[0]


def test_necessary_option_is_not_penalized_for_teacher_avoid():
    periods = tuple(period(day, hour) for day in range(5) for hour in (9, 10))
    row = assignment(1, teacher_id=1, class_id=1)
    avoid = tuple(
        Unavailability(UnavailableResource.TEACHER, 1, periods[day * 2]) for day in range(5)
    )
    impossible = tuple(
        Unavailability(UnavailableResource.TEACHER, 1, periods[day * 2 + 1]) for day in range(5)
    )
    selected = weights(finish_early=1, teacher_preferences=4)

    result = construct_schedule(
        make_snapshot((row,), periods, soft=avoid, unavailable=impossible),
        periods,
        weights=selected,
    )

    assert result.lessons[0].period == periods[0]


def test_period_selection_keeps_necessary_option_ahead_of_higher_value_option():
    periods = (period(0, 9), period(0, 10))
    necessary = assignment(1, teacher_id=1, class_id=1)
    optional = assignment(2, teacher_id=1, class_id=2)
    unavailable = (Unavailability(UnavailableResource.CLASS, 1, periods[1]),)
    selected = weights(finish_early=0, teacher_gaps=0, class_gaps=0)

    result = construct_schedule(
        make_snapshot((necessary, optional), periods, unavailable=unavailable),
        periods,
        weights=selected,
    )

    assert (
        next(lesson for lesson in result.lessons if lesson.period == periods[0]).assignment_id == 1
    )


def test_period_selection_prioritizes_necessary_options_before_value():
    necessary = assignment(1, teacher_id=1, class_id=1)
    optional = assignment(2, teacher_id=1, class_id=2)

    selected = _select_period(
        [(necessary, (101,)), (optional, (102,))],
        deadline=None,
        scores={(1, 101): (True, -10, 10), (2, 102): (False, 50, 1)},
    )

    assert [row.assignment_id for row, _room in selected] == [1]


def test_period_selection_uses_value_when_no_option_is_necessary():
    lower_value = assignment(1, teacher_id=1, class_id=1)
    higher_value = assignment(2, teacher_id=1, class_id=2)

    selected = _select_period(
        [(lower_value, (101,)), (higher_value, (102,))],
        deadline=None,
        scores={(1, 101): (False, -10, 1), (2, 102): (False, 50, 100)},
    )

    assert [row.assignment_id for row, _room in selected] == [2]


def test_period_repair_is_bounded_by_deterministic_time_so_the_schedule_repeats(monkeypatch):
    """I03: the repair solve must not stop on wall-clock time, or runs under load differ."""
    recorded = []
    solver_class = constructive.cp_model.CpSolver

    class RecordingSolver(solver_class):
        def Solve(self, model):
            recorded.append(
                (self.parameters.max_time_in_seconds, self.parameters.max_deterministic_time)
            )
            return super().Solve(model)

    monkeypatch.setattr(constructive.cp_model, "CpSolver", RecordingSolver)
    first = assignment(1, teacher_id=1, class_id=1)
    second = assignment(2, teacher_id=1, class_id=2)

    _select_period(
        [(first, (101,)), (second, (102,))],
        deadline=None,
        scores={(1, 101): (False, 5, 1), (2, 102): (False, 5, 1)},
    )

    assert len(recorded) == 1
    wall_limit, deterministic_limit = recorded[0]
    assert wall_limit == float("inf")
    assert deterministic_limit > 0


def test_unweighted_period_repair_keeps_its_wall_clock_limit(monkeypatch):
    """I02: without weights the repair solve keeps the 0.1 s limit it had before priorities."""
    recorded = []
    solver_class = constructive.cp_model.CpSolver

    class RecordingSolver(solver_class):
        def Solve(self, model):
            recorded.append(
                (self.parameters.max_time_in_seconds, self.parameters.max_deterministic_time)
            )
            return super().Solve(model)

    monkeypatch.setattr(constructive.cp_model, "CpSolver", RecordingSolver)
    joint = Assignment(1, (1, 2), 1, 1, frozenset({101}), (ModuleRequirement(10, 1, 60),))
    first = assignment(2, teacher_id=2, class_id=1)
    second = assignment(3, teacher_id=3, class_id=2)

    _select_period([(joint, (101,)), (first, (102,)), (second, (103,))], deadline=None)

    assert recorded == [(0.1, float("inf"))]


def test_weighted_joint_construction_repeats_the_same_schedule():
    """I03: the weighted period repair stops on deterministic time, so runs repeat."""
    fixture = build_joint_typology_fixture(12)
    weights = PriorityWeights(DEFAULT_LEVELS)

    first = construct_schedule(fixture.snapshot, fixture.periods, weights=weights)
    second = construct_schedule(fixture.snapshot, fixture.periods, weights=weights)

    assert first is not None
    assert repr(first.lessons) == repr(second.lessons)


def test_urgency_order_survives_capacities_too_large_for_raw_minute_coefficients():
    """The objective ranks urgencies, so huge capacities cannot overflow the model."""
    # Raw minutes give coefficients near 4e18 each: their sum leaves int64 and CP-SAT
    # rejects the model, so the greedy fill would keep the less urgent option 1.
    later = assignment(1, teacher_id=1, class_id=1)
    earlier = assignment(2, teacher_id=1, class_id=2)
    other = assignment(3, teacher_id=3, class_id=3)
    huge = 22 * 10**13

    selected = _select_period(
        [(later, (101,)), (earlier, (102,)), (other, (103,))],
        deadline=None,
        scores={
            (1, 101): (True, 1000, huge),
            (2, 102): (True, 1000, 1),
            (3, 103): (True, 1000, huge),
        },
    )

    assert sorted(row.assignment_id for row, _room in selected) == [2, 3]


def test_availability_order_precedes_value_only_for_necessary_options():
    later = assignment(1, teacher_id=1, class_id=1)
    earlier = assignment(2, teacher_id=1, class_id=2)

    selected = _select_period(
        [(later, (101,)), (earlier, (102,))],
        deadline=None,
        scores={(1, 101): (True, 40, 20), (2, 102): (True, -10, 10)},
    )

    assert [row.assignment_id for row, _room in selected] == [2]


def test_a_fill_pass_follows_the_priorities_when_empty_hours_left_both_passes_short(
    monkeypatch,
):
    """T11: before giving up the priorities, one pass fills every teachable hour."""
    calls = []
    built = object()

    def fake_pass(*_args, strict, fill=False, **_kwargs):
        calls.append((strict, fill))
        return (built if fill else None), 1

    monkeypatch.setattr(constructive, "_construct_pass", fake_pass)
    result = construct_schedule(None, (), weights=PriorityWeights(DEFAULT_LEVELS))

    assert result is built
    assert calls == [(True, False), (False, False), (False, True)]
    # Without weights there is no fill pass: the legacy flow stays as it was (I02).
    calls.clear()
    assert construct_schedule(None, ()) is None
    assert calls == [(True, False), (False, False)]


def test_the_fill_pass_teaches_an_option_whatever_its_value():
    weights = PriorityWeights(DEFAULT_LEVELS)

    assert constructive._fills_hour(weights, {}, -500, strict=True) is False
    assert constructive._fills_hour(weights, {}, -500, strict=False, fill=True) is True
