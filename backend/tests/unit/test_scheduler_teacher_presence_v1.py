"""Teacher presence rules in the validator and the exact solver.

S3 covers the validator (R04-R08); S5 covers the exact placement model (minimum
hours per presence, grid-block gap, designated free lunch option, protected
exemption) and the enumerative-oracle objective.
"""

from dataclasses import replace
from datetime import date, time

import pytest

from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    GridSlot,
    LunchRule,
    PlanningSnapshot,
    ScheduledLesson,
    SchedulingStrategy,
    TeacherPresenceRule,
)
from app.scheduler.domain.candidate_validation import (
    ValidationViolationCode,
    validate_candidate,
)
from app.scheduler.domain.projection import ModuleRequirement, ModuleSlice
from app.scheduler.domain.teacher_presence import (
    PresenceLesson,
    impossible_presence_teacher_ids,
    longest_presence_minutes,
    lunch_options,
    presence_minutes_fit,
    teacher_day_complies,
)

TZ = "Europe/Lisbon"
ORIGIN = date(2026, 9, 21)
PREFERRED = date(2026, 10, 30)
HARD_END = date(2026, 11, 30)


@pytest.mark.parametrize("adaptive", [False, True])
def test_impossible_teacher_presence_stops_before_constructing_any_solver_model(adaptive):
    from app.scheduler.application.generation import generate_complete
    from app.scheduler.application.recovery import repair_schedule
    from tests.unit.test_scheduler_recovery_solver_v1 import POLICY

    slots = (_slot(9), _slot(10))
    periods = (_period(9), _period(10))
    target = _snapshot(
        slots=slots,
        required_minutes=60,
        teacher_presence=(TeacherPresenceRule(100, False, 720, 60),),
    )

    def unexpected_search(*_args, **_kwargs):
        pytest.fail("Impossible presence must be detected before search allocates a model.")

    if adaptive:
        target = replace(target, strategy=SchedulingStrategy.ADAPTIVE_RECOVERY)
        result = repair_schedule(
            target, periods, CandidateSchedule(()), search=unexpected_search, policy=POLICY
        )
    else:
        result = generate_complete(target, periods, search=unexpected_search)

    assert result.outcome == "INFEASIBLE"
    assert result.candidate is None
    assert result.search_seconds == 0
    proven = [row for row in result.diagnoses if row.code == "TEACHER_PRESENCE_IMPOSSIBLE"]
    assert len(proven) == 1
    assert proven[0].affected_teacher_ids == (100,)
    assert proven[0].evidence_kind == "PROVEN_SCOPE"


MONDAY = date(2026, 9, 21)

LUNCH = LunchRule(window_start=time(12, 0), window_end=time(14, 0), minimum_minutes=60)


def _slot(hour: int, minutes: int = 60) -> GridSlot:
    end = hour * 60 + minutes
    return GridSlot(0, time(hour, 0), time(end // 60, end % 60))


def _period(hour: int, minutes: int = 60):
    end = hour * 60 + minutes
    return normalize_period(MONDAY, time(hour, 0), time(end // 60, end % 60), TZ)


def _snapshot(
    *,
    slots,
    required_minutes: int,
    teacher_presence=(),
    lunch_rule=None,
    protected=(),
    class_ids=(1,),
) -> PlanningSnapshot:
    return PlanningSnapshot(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=ORIGIN,
        preferred_end_date=PREFERRED,
        hard_end_date=HARD_END,
        timezone_name=TZ,
        grid_slots=tuple(slots),
        assignments=(
            Assignment(
                assignment_id=1,
                class_ids=tuple(class_ids),
                subject_id=10,
                teacher_id=100,
                eligible_room_ids=frozenset({500}),
                modules=(ModuleRequirement(1, 1, required_minutes),),
            ),
        ),
        executed_minutes={},
        blocked_dates=frozenset(),
        unavailable=(),
        protected_lessons=tuple(protected),
        teacher_presence=tuple(teacher_presence),
        lunch_rule=lunch_rule,
    )


def _lessons(*hours: int, credit: int = 60) -> tuple[ScheduledLesson, ...]:
    lessons = []
    offset = 0
    for index, hour in enumerate(hours, start=1):
        lessons.append(
            ScheduledLesson(
                lesson_id=index,
                assignment_id=1,
                period=_period(hour),
                room_id=500,
                credit_minutes=credit,
                slices=(ModuleSlice(index, 1, offset, credit),),
            )
        )
        offset += credit
    return tuple(lessons)


def _codes(report) -> set[ValidationViolationCode]:
    return {violation.code for violation in report.violations}


def test_presence_capacity_does_not_combine_different_weekday_grids():
    target = _snapshot(
        slots=(_slot(9), GridSlot(1, time(10), time(11))),
        required_minutes=60,
        teacher_presence=(TeacherPresenceRule(100, False, 120, 0),),
    )
    # The raw calendar includes all slot signatures on each date. Only the
    # matching weekday is a teaching opportunity, as in placement eligibility.
    periods = tuple(
        normalize_period(day, time(hour), time(hour + 1), TZ)
        for day in (MONDAY, date(2026, 9, 22))
        for hour in (9, 10)
    )
    assert impossible_presence_teacher_ids(target, periods) == (100,)


def test_presence_capacity_exempts_a_teacher_with_only_protected_demand():
    target = _snapshot(
        slots=(_slot(9),),
        required_minutes=60,
        protected=_lessons(9),
        teacher_presence=(TeacherPresenceRule(100, False, 720, 0),),
    )
    assert impossible_presence_teacher_ids(target, (_period(9),)) == ()


# --- R04: the presence split by a free lunch choice --------------------------


def test_r04_accepts_two_presences_split_by_the_lunch_choice():
    snapshot = _snapshot(
        slots=[_slot(10), _slot(11), _slot(12), _slot(14), _slot(15), _slot(16)],
        required_minutes=360,
        teacher_presence=(
            TeacherPresenceRule(teacher_id=100, minimum_minutes=180, max_gap_minutes=60),
        ),
        lunch_rule=LUNCH,
    )
    candidate = CandidateSchedule(_lessons(10, 11, 12, 14, 15, 16))

    assert validate_candidate(snapshot, candidate).valid


# --- R05: the minimum hours per presence -------------------------------------


def test_r05_rejects_a_presence_below_the_minimum_and_accepts_without_a_rule():
    candidate = CandidateSchedule(_lessons(10, 11, 17))
    slots = [_slot(10), _slot(11), _slot(12), _slot(13), _slot(17)]
    with_rule = _snapshot(
        slots=slots,
        required_minutes=180,
        teacher_presence=(
            TeacherPresenceRule(teacher_id=100, minimum_minutes=180, max_gap_minutes=60),
        ),
        lunch_rule=LUNCH,
    )

    report = validate_candidate(with_rule, candidate)
    assert ValidationViolationCode.TEACHER_PRESENCE_VIOLATION in _codes(report)

    without_rule = _snapshot(slots=slots, required_minutes=180, lunch_rule=LUNCH)
    assert validate_candidate(without_rule, candidate).valid


# --- R06: the gap is the sum of empty grid blocks ----------------------------


def test_r06_gap_counts_empty_grid_blocks_not_wall_clock():
    slots = [_slot(9), _slot(10), _slot(11), _slot(12), _slot(13)]
    gap_one = (
        TeacherPresenceRule(
            teacher_id=100, lunch_required=False, minimum_minutes=180, max_gap_minutes=60
        ),
    )

    accepted = _snapshot(slots=slots, required_minutes=180, teacher_presence=gap_one)
    assert validate_candidate(accepted, CandidateSchedule(_lessons(9, 10, 12))).valid

    refused = _snapshot(slots=slots, required_minutes=180, teacher_presence=gap_one)
    report = validate_candidate(refused, CandidateSchedule(_lessons(9, 10, 13)))
    assert ValidationViolationCode.TEACHER_PRESENCE_VIOLATION in _codes(report)

    wider = _snapshot(
        slots=slots,
        required_minutes=180,
        teacher_presence=(
            TeacherPresenceRule(
                teacher_id=100, lunch_required=False, minimum_minutes=180, max_gap_minutes=120
            ),
        ),
    )
    assert validate_candidate(wider, CandidateSchedule(_lessons(9, 10, 13))).valid


# --- R07: a joint lesson counts once for its teacher -------------------------


def test_r07_a_joint_lesson_counts_once_for_the_teacher():
    snapshot = _snapshot(
        slots=[_slot(10)],
        required_minutes=60,
        class_ids=(1, 2),
        teacher_presence=(
            TeacherPresenceRule(
                teacher_id=100, lunch_required=False, minimum_minutes=120, max_gap_minutes=120
            ),
        ),
    )
    candidate = CandidateSchedule(_lessons(10))

    assert ValidationViolationCode.TEACHER_PRESENCE_VIOLATION in _codes(
        validate_candidate(snapshot, candidate)
    )


# --- R08: protected presence exemption ---------------------------------------


def test_r08_a_protected_only_presence_is_exempt():
    protected = _lessons(10)
    snapshot = _snapshot(
        slots=[_slot(10)],
        required_minutes=60,
        protected=protected,
        teacher_presence=(
            TeacherPresenceRule(
                teacher_id=100, lunch_required=False, minimum_minutes=180, max_gap_minutes=60
            ),
        ),
    )

    assert validate_candidate(snapshot, CandidateSchedule(protected)).valid


def test_r08_a_mixed_presence_counts_protected_and_editable_lessons():
    protected = (
        ScheduledLesson(
            lesson_id=1,
            assignment_id=1,
            period=_period(10),
            room_id=500,
            credit_minutes=60,
            slices=(ModuleSlice(1, 1, 0, 60),),
        ),
    )
    editable = (
        ScheduledLesson(
            lesson_id=2,
            assignment_id=1,
            period=_period(11),
            room_id=500,
            credit_minutes=60,
            slices=(ModuleSlice(2, 1, 60, 60),),
        ),
    )
    snapshot = _snapshot(
        slots=[_slot(10), _slot(11)],
        required_minutes=120,
        protected=protected,
        teacher_presence=(
            TeacherPresenceRule(
                teacher_id=100, lunch_required=False, minimum_minutes=180, max_gap_minutes=120
            ),
        ),
    )

    report = validate_candidate(snapshot, CandidateSchedule(protected + editable))
    assert ValidationViolationCode.TEACHER_PRESENCE_VIOLATION in _codes(report)


# --- Pure helpers ------------------------------------------------------------


def test_lunch_options_anchor_minimal_free_windows():
    assert lunch_options([720, 780, 840], 840, 60) == [(720, 780), (780, 840)]


def test_teacher_day_complies_accepts_a_free_lunch_split():
    lessons = (
        PresenceLesson(600, 660, protected=False),
        PresenceLesson(660, 720, protected=False),
        PresenceLesson(720, 780, protected=False),
        PresenceLesson(840, 900, protected=False),
        PresenceLesson(900, 960, protected=False),
        PresenceLesson(960, 1020, protected=False),
    )
    slots = [(600, 660), (660, 720), (720, 780), (840, 900), (900, 960), (960, 1020)]
    rule = TeacherPresenceRule(teacher_id=100, minimum_minutes=180, max_gap_minutes=60)

    assert teacher_day_complies(lessons, rule, lunch_rule=LUNCH, grid_slots=slots)


# --- S5: exact placement model ----------------------------------------------


def _rule(minimum_minutes: int, max_gap_minutes: int = 10_000, *, lunch_required: bool = False):
    return TeacherPresenceRule(
        teacher_id=1,
        lunch_required=lunch_required,
        minimum_minutes=minimum_minutes,
        max_gap_minutes=max_gap_minutes,
    )


def _solver(periods, assignments, *, presence=(), lunch=None, protected=(), grid=None):
    from tests.unit.test_scheduler_resource_exclusivity_v1 import plan

    target = plan(
        periods,
        assignments,
        protected_lessons=protected,
        lunch_rule=lunch,
        teacher_presence=tuple(presence),
    )
    if grid is not None:
        target = replace(target, grid_slots=tuple(grid))
    return target


def test_solver_rejects_a_teacher_day_below_the_minimum():
    from tests.unit.test_scheduler_resource_exclusivity_v1 import assignment
    from tests.unit.test_scheduler_w04_w05_regressions_v1 import period

    periods = (period(0, start=9, end=10), period(0, start=10, end=11))
    snapshot = _solver(periods, [assignment(1, 1, 1, {1}, 120)], presence=(_rule(180),))

    from app.scheduler.infrastructure.placement_model import solve_placement

    assert solve_placement(snapshot, periods, time_limit_seconds=5).candidate is None


def test_solver_accepts_a_teacher_day_at_the_minimum():
    from app.scheduler.infrastructure.placement_model import solve_placement
    from tests.unit.test_scheduler_resource_exclusivity_v1 import assignment
    from tests.unit.test_scheduler_w04_w05_regressions_v1 import period

    periods = tuple(period(0, start=hour, end=hour + 1) for hour in (9, 10, 11))
    snapshot = _solver(periods, [assignment(1, 1, 1, {1}, 180)], presence=(_rule(180),))

    outcome = solve_placement(snapshot, periods, time_limit_seconds=5)

    assert outcome.candidate is not None
    assert validate_candidate(snapshot, outcome.candidate).valid


def test_solver_measures_the_gap_in_empty_grid_blocks():
    from app.scheduler.infrastructure.placement_model import solve_placement
    from tests.unit.test_scheduler_resource_exclusivity_v1 import assignment
    from tests.unit.test_scheduler_w04_w05_regressions_v1 import period

    periods = (
        period(0, start=9, end=10),
        period(0, start=10, end=11),
        period(0, start=12, end=13),
    )
    grid = [_slot(9), _slot(10), _slot(11), _slot(12)]

    strict = _solver(periods, [assignment(1, 1, 1, {1}, 180)], presence=(_rule(180, 0),), grid=grid)
    assert solve_placement(strict, periods, time_limit_seconds=5).candidate is None

    tolerated = _solver(
        periods, [assignment(1, 1, 1, {1}, 180)], presence=(_rule(180, 60),), grid=grid
    )
    accepted = solve_placement(tolerated, periods, time_limit_seconds=5)
    assert accepted.candidate is not None
    assert validate_candidate(tolerated, accepted.candidate).valid


def test_solver_uses_one_designated_free_lunch_option_for_the_split():
    """A free option that leaves the afternoon short must not forbid a good split."""
    from app.scheduler.infrastructure.placement_model import solve_placement
    from tests.unit.test_scheduler_resource_exclusivity_v1 import assignment
    from tests.unit.test_scheduler_w04_w05_regressions_v1 import period

    periods = tuple(period(0, start=hour, end=hour + 1) for hour in (12, 13, 14))
    snapshot = _solver(
        periods,
        [assignment(1, 1, 1, {1}, 120)],
        presence=(_rule(120, 10_000, lunch_required=True),),
        lunch=LunchRule(time(12), time(14), 60),
    )

    outcome = solve_placement(snapshot, periods, time_limit_seconds=5)

    assert outcome.candidate is not None
    assert validate_candidate(snapshot, outcome.candidate).valid


def test_solver_exempts_a_protected_only_presence_from_the_minimum():
    from app.scheduler.infrastructure.placement_model import solve_placement
    from tests.unit.test_scheduler_resource_exclusivity_v1 import assignment, lesson
    from tests.unit.test_scheduler_w04_w05_regressions_v1 import period

    periods = (period(0, start=9, end=10),)
    protected = (lesson(10, 1, periods[0], 1),)
    snapshot = _solver(
        periods,
        [assignment(1, 1, 1, {1}, 60)],
        presence=(_rule(180),),
        protected=protected,
    )

    outcome = solve_placement(snapshot, periods, time_limit_seconds=5)

    assert outcome.candidate is not None
    assert validate_candidate(snapshot, outcome.candidate).valid


def test_solver_counts_protected_minutes_in_a_mixed_presence():
    from app.scheduler.infrastructure.placement_model import solve_placement
    from tests.unit.test_scheduler_resource_exclusivity_v1 import assignment, lesson
    from tests.unit.test_scheduler_w04_w05_regressions_v1 import period

    periods = (period(0, start=9, end=10), period(0, start=10, end=11))
    protected = (lesson(10, 1, periods[0], 1),)
    snapshot = _solver(
        periods,
        [assignment(1, 1, 1, {1}, 120)],
        presence=(_rule(180),),
        protected=protected,
    )

    assert solve_placement(snapshot, periods, time_limit_seconds=5).candidate is None


def test_r22_exact_optimum_matches_the_enumerative_oracle_on_a_rule_instance():
    from app.scheduler.domain.oracle import optimal_candidate, oracle_objective
    from app.scheduler.infrastructure.placement_model import solve_placement
    from tests.unit.test_scheduler_resource_exclusivity_v1 import assignment
    from tests.unit.test_scheduler_w04_w05_regressions_v1 import period

    periods = (
        period(0, start=9, end=10),
        period(0, start=10, end=11),
        period(0, start=11, end=12),
        period(1, start=9, end=10),
    )
    snapshot = _solver(periods, [assignment(1, 1, 1, {1}, 180)], presence=(_rule(180),))

    expected = optimal_candidate(snapshot, periods)
    assert expected is not None
    outcome = solve_placement(snapshot, periods, time_limit_seconds=10)

    assert outcome.candidate is not None
    assert oracle_objective(snapshot, outcome.candidate) == oracle_objective(snapshot, expected)


def test_presence_rules_change_the_lunch_cache_salt():
    from app.scheduler.infrastructure.placement_model import _lunch_cache_salt

    base = _snapshot(slots=[_slot(9)], required_minutes=60, lunch_rule=LUNCH)
    without = _lunch_cache_salt(base, "s")
    with_rule = replace(
        base,
        teacher_presence=(
            TeacherPresenceRule(
                teacher_id=100, lunch_required=False, minimum_minutes=60, max_gap_minutes=60
            ),
        ),
    )

    assert _lunch_cache_salt(with_rule, "s") != without


BREAK_DAY = tuple(
    (hour * 60 + minute, hour * 60 + minute + 60)
    for hour, minute in (
        (9, 0),
        (10, 10),
        (11, 20),
        (12, 30),
        (13, 30),
        (14, 40),
        (15, 50),
        (17, 0),
    )
)


def test_the_longest_presence_is_one_side_of_the_lunch_break():
    lunch = LunchRule(time(12, 30), time(14, 30), 60)
    rule = TeacherPresenceRule(9, minimum_minutes=180, max_gap_minutes=60)

    # Lunch at 13:30 leaves 9:00-13:30 (four lessons) on one side.
    assert longest_presence_minutes(rule, BREAK_DAY, lunch_rule=lunch) == 240
    # Without a required lunch the whole day is one presence.
    assert (
        longest_presence_minutes(replace(rule, lunch_required=False), BREAK_DAY, lunch_rule=lunch)
        == 480
    )


@pytest.mark.parametrize(
    ("left", "fits"),
    [(0, True), (120, False), (180, True), (240, True), (300, False), (360, True), (420, True)],
)
def test_remaining_minutes_fit_only_when_they_split_into_valid_presences(left, fits):
    # A 3-hour minimum with at most 4 hours per presence: 5 hours can never be taught.
    assert presence_minutes_fit(left, minimum=180, longest=240) is fits
