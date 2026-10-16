from dataclasses import replace
from datetime import date, time, timedelta

from app.scheduler.application.generation import generate_complete
from app.scheduler.composition import generate_schedule
from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import (
    CandidateSchedule,
    ScheduledLesson,
    SchedulingStrategy,
    TeacherPresenceRule,
)
from app.scheduler.domain.capacity import aggregate_capacity_check
from app.scheduler.domain.diagnostics import DiagnosisCode, EvidenceKind
from app.scheduler.domain.projection import ModuleSlice
from app.scheduler.domain.results import (
    OUTCOME_COMPLETE,
    OUTCOME_FAILED,
    OUTCOME_INCONCLUSIVE,
    OUTCOME_INFEASIBLE,
    SearchOutcome,
)
from app.scheduler.infrastructure.placement_model import solve_placement
from app.scheduler.lab.fixtures import (
    AssignmentSpec,
    CaseExpectation,
    FixtureSpec,
    build_fixture,
)
from app.scheduler.lab.scale import build_scale_fixture
from tests.unit.test_scheduler_w04_w05_regressions_v1 import period, snapshot

TZ = "Europe/Lisbon"
ORIGIN = date(2026, 9, 21)
GRID = ((0, time(9), time(10)), (2, time(9), time(10)))
PERIODS = ((date(2026, 9, 21), time(9), time(10)), (date(2026, 9, 23), time(9), time(10)))


def _spec(module_minutes: tuple[int, ...], periods=PERIODS, grid=GRID) -> FixtureSpec:
    return FixtureSpec(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=ORIGIN,
        preferred_end_date=date(2026, 10, 30),
        hard_end_date=date(2026, 11, 30),
        timezone_name=TZ,
        grid_slots=grid,
        periods=periods,
        assignments=(AssignmentSpec(1, 100, module_minutes, (500,)),),
    )


def test_generation_produces_a_validated_complete_schedule():
    fixture = build_fixture("gen-1", _spec((100,)))

    result = generate_schedule(fixture.snapshot, fixture.periods, time_limit_seconds=5)

    assert result.outcome == "COMPLETE"
    assert result.report is not None and result.report.valid
    assert result.report.total_credit_minutes == 100


def test_generation_handles_modules_that_cross_lessons():
    days = (date(2026, 9, 21), date(2026, 9, 22), date(2026, 9, 23), date(2026, 9, 24))
    periods = tuple((day, time(9), time(9, 50)) for day in days)
    grid = tuple((day.weekday(), time(9), time(9, 50)) for day in days)
    fixture = build_fixture("gen-crossing", _spec((75, 75), periods=periods, grid=grid))

    result = generate_schedule(fixture.snapshot, fixture.periods, time_limit_seconds=5)

    assert result.outcome == "COMPLETE"
    assert result.report is not None and result.report.valid
    assert result.report.total_credit_minutes == 150
    modules = {slice_.module_id for lesson in result.candidate.lessons for slice_ in lesson.slices}
    assert modules == {1, 2}


def test_generation_reports_a_proven_deficit_as_infeasible():
    fixture = build_fixture(
        "gen-infeasible", _spec((200,)), expectation=CaseExpectation.INFEASIBLE_PROVEN
    )

    result = generate_schedule(fixture.snapshot, fixture.periods, time_limit_seconds=5)

    assert result.outcome == "INFEASIBLE"
    assert "Proven minimum deficit" in result.message
    assert result.candidate is None


def test_generation_keeps_the_last_lesson_partial():
    fixture = build_fixture("gen-partial", _spec((100,)))

    result = generate_schedule(fixture.snapshot, fixture.periods, time_limit_seconds=5)

    credits = [lesson.credit_minutes for lesson in result.candidate.lessons]
    assert result.outcome == "COMPLETE"
    assert sum(credits) == 100
    assert credits[-1] < 60


def test_a_bounded_search_never_claims_infeasibility():
    fixture = build_scale_fixture(60)

    result = generate_schedule(fixture.snapshot, fixture.periods, time_limit_seconds=0.05)

    assert result.outcome in {"COMPLETE", "INCONCLUSIVE"}
    if result.outcome == "INCONCLUSIVE":
        assert result.candidate is None


def test_generation_preserves_a_protected_lesson():
    fixture = build_fixture("gen-protected", _spec((100,)))
    protected = ScheduledLesson(
        lesson_id=1,
        assignment_id=1,
        period=normalize_period(date(2026, 9, 21), time(9), time(10), TZ),
        room_id=500,
        credit_minutes=60,
        slices=(ModuleSlice(1, 1, 0, 60),),
    )
    snapshot = fixture.snapshot.__class__(
        strategy=fixture.snapshot.strategy,
        origin=fixture.snapshot.origin,
        preferred_end_date=fixture.snapshot.preferred_end_date,
        hard_end_date=fixture.snapshot.hard_end_date,
        timezone_name=fixture.snapshot.timezone_name,
        grid_slots=fixture.snapshot.grid_slots,
        assignments=fixture.snapshot.assignments,
        executed_minutes={},
        blocked_dates=fixture.snapshot.blocked_dates,
        unavailable=(),
        protected_lessons=(protected,),
    )

    result = generate_schedule(snapshot, fixture.periods, time_limit_seconds=5)

    assert result.outcome == "COMPLETE"
    assert result.report is not None and result.report.valid
    assert any(lesson.lesson_id == 1 for lesson in result.candidate.lessons)
    assert result.report.total_credit_minutes == 100


def test_aggregate_capacity_reports_only_proven_deficits():
    feasible = _spec((100,))
    infeasible = _spec((200,))

    feasible_fixture = build_fixture("cap-a", feasible)
    infeasible_fixture = build_fixture(
        "cap-b", infeasible, expectation=CaseExpectation.INFEASIBLE_PROVEN
    )

    assert not aggregate_capacity_check(
        feasible_fixture.snapshot, feasible_fixture.periods
    ).proven_infeasible
    assert aggregate_capacity_check(
        infeasible_fixture.snapshot, infeasible_fixture.periods
    ).proven_infeasible


def test_a_class_level_deficit_proves_infeasibility_without_a_search():
    spec = FixtureSpec(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=ORIGIN,
        preferred_end_date=date(2026, 10, 30),
        hard_end_date=date(2026, 11, 30),
        timezone_name=TZ,
        grid_slots=((0, time(9), time(10)), (1, time(9), time(10))),
        periods=(
            (ORIGIN, time(9), time(10)),
            (ORIGIN + timedelta(days=1), time(9), time(10)),
        ),
        assignments=(
            AssignmentSpec(7, 1, (60,), (500,)),
            AssignmentSpec(7, 2, (120,), (501,)),
        ),
    )
    fixture = build_fixture("class-deficit", spec, expectation=CaseExpectation.INFEASIBLE_PROVEN)

    def forbidden_search(*args, **kwargs):
        raise AssertionError("The search must not run when capacity proves infeasibility.")

    result = generate_complete(fixture.snapshot, fixture.periods, search=forbidden_search)

    assert result.outcome == "INFEASIBLE"
    assert result.candidate is None
    assert any(row.code is DiagnosisCode.INSUFFICIENT_CLASS_TIME for row in result.diagnoses)


def test_placement_status_is_typed():
    fixture = build_scale_fixture(10)

    outcome = solve_placement(fixture.snapshot, fixture.periods, time_limit_seconds=10)

    assert outcome.status in {"COMPLETE", "INFEASIBLE", "INCONCLUSIVE"}
    assert outcome.proven_scope == "UNRESTRICTED_EXACT_MODEL"


def test_t13_a_dense_day_from_the_grid_is_allowed():
    day = date(2026, 9, 21)
    periods = tuple((day, time(9 + hour), time(10 + hour)) for hour in range(5))
    grid = tuple((0, time(9 + hour), time(10 + hour)) for hour in range(5))
    fixture = build_fixture("t13-dense-day", _spec((240,), periods=periods, grid=grid))

    result = generate_schedule(fixture.snapshot, fixture.periods, time_limit_seconds=10)

    assert result.outcome == "COMPLETE"
    assert result.report is not None and result.report.valid
    assert len(result.candidate.lessons) == 4


SINGLE_PERIOD = ((0, time(9), time(10)),)


def test_t14_a_dispreferred_period_stays_eligible():
    soft = _spec((60,), periods=((ORIGIN, time(9), time(10)),), grid=SINGLE_PERIOD)
    soft = replace(
        soft,
        soft_unavailable=(("teacher", 100, (ORIGIN, time(9), time(10))),),
    )
    fixture = build_fixture("t14-soft-preference", soft)

    result = generate_schedule(fixture.snapshot, fixture.periods, time_limit_seconds=10)

    assert result.outcome == "COMPLETE"
    assert result.report is not None and result.report.valid
    assert result.quality is not None and result.quality.preference_cost_minutes == 60


def test_t14_a_hard_unavailability_prohibits_the_period():
    blocked = _spec((60,), periods=((ORIGIN, time(9), time(10)),), grid=SINGLE_PERIOD)
    blocked = replace(
        blocked,
        unavailable=(("teacher", 100, (ORIGIN, time(9), time(10))),),
    )
    fixture = build_fixture(
        "t14-hard-unavailability", blocked, expectation=CaseExpectation.INFEASIBLE_PROVEN
    )

    result = generate_schedule(fixture.snapshot, fixture.periods, time_limit_seconds=10)

    assert result.outcome == "INFEASIBLE"


def test_the_assigned_teacher_is_a_fixed_requirement():
    spec = FixtureSpec(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=ORIGIN,
        preferred_end_date=date(2026, 10, 30),
        hard_end_date=date(2026, 11, 30),
        timezone_name=TZ,
        grid_slots=((0, time(9), time(10)),),
        periods=((ORIGIN, time(9), time(10)),),
        assignments=(
            AssignmentSpec(1, 7, (60,), (500,)),
            AssignmentSpec(2, 7, (60,), (501,)),
        ),
    )
    fixture = build_fixture("fixed-teacher", spec, expectation=CaseExpectation.INFEASIBLE_PROVEN)

    result = generate_schedule(fixture.snapshot, fixture.periods, time_limit_seconds=10)

    assert result.outcome == "INFEASIBLE"


def test_room_unavailability_removes_the_impossible_room():
    day = ORIGIN
    spec = FixtureSpec(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=day,
        preferred_end_date=date(2026, 10, 30),
        hard_end_date=date(2026, 11, 30),
        timezone_name=TZ,
        grid_slots=((0, time(9), time(10)), (0, time(10), time(11))),
        periods=((day, time(9), time(10)), (day, time(10), time(11))),
        assignments=(AssignmentSpec(1, 7, (60,), (500, 501)),),
        unavailable=(
            ("room", 500, (day, time(9), time(10))),
            ("room", 501, (day, time(10), time(11))),
        ),
    )
    fixture = build_fixture("room-unavailability", spec)

    result = generate_schedule(fixture.snapshot, fixture.periods, time_limit_seconds=10)

    assert result.outcome == "COMPLETE"
    assert result.report is not None and result.report.valid
    lesson = result.candidate.lessons[0]
    assert (lesson.period.start_local, lesson.room_id) in {
        (time(9), 501),
        (time(10), 500),
    }


def test_room_unavailability_can_prove_infeasibility():
    day = ORIGIN
    spec = FixtureSpec(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=day,
        preferred_end_date=date(2026, 10, 30),
        hard_end_date=date(2026, 11, 30),
        timezone_name=TZ,
        grid_slots=((0, time(9), time(10)),),
        periods=((day, time(9), time(10)),),
        assignments=(AssignmentSpec(1, 7, (60,), (500,)),),
        unavailable=(("room", 500, (day, time(9), time(10))),),
    )
    fixture = build_fixture("room-blocked", spec, expectation=CaseExpectation.INFEASIBLE_PROVEN)

    result = generate_schedule(fixture.snapshot, fixture.periods, time_limit_seconds=10)

    assert result.outcome == "INFEASIBLE"


def test_t12_a_specific_room_pushes_the_other_lesson_to_another_period():
    day = ORIGIN
    spec = FixtureSpec(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=day,
        preferred_end_date=date(2026, 10, 30),
        hard_end_date=date(2026, 11, 30),
        timezone_name=TZ,
        grid_slots=((0, time(9), time(10)), (0, time(10), time(11))),
        periods=((day, time(9), time(10)), (day, time(10), time(11))),
        assignments=(
            AssignmentSpec(1, 7, (60,), (500,)),
            AssignmentSpec(2, 8, (60,), (500,)),
        ),
        unavailable=(("class", 1, (day, time(10), time(11))),),
    )
    fixture = build_fixture("t12-specific-room", spec)

    result = generate_schedule(fixture.snapshot, fixture.periods, time_limit_seconds=10)

    assert result.outcome == "COMPLETE"
    assert result.report is not None and result.report.valid
    placement = {
        lesson.assignment_id: (lesson.period.start_local, lesson.room_id)
        for lesson in result.candidate.lessons
    }
    assert placement == {1: (time(9), 500), 2: (time(10), 500)}


def test_t30_only_the_residual_demand_becomes_future_lessons():
    spec = _spec(
        (60,),
        periods=((ORIGIN, time(9), time(10)),),
        grid=SINGLE_PERIOD,
    )
    spec = replace(
        spec,
        assignments=(
            AssignmentSpec(1, 100, (60,), (500,)),
            AssignmentSpec(2, 101, (60,), (501,)),
        ),
        executed_minutes=((1, ((1, 60),)),),
    )
    fixture = build_fixture("t30-residual-only", spec)

    result = generate_schedule(fixture.snapshot, fixture.periods, time_limit_seconds=10)

    assert result.outcome == "COMPLETE"
    assert [lesson.assignment_id for lesson in result.candidate.lessons] == [2]
    assert result.report.total_credit_minutes == 60


def test_a_protected_lesson_reserves_its_room():
    day = ORIGIN
    spec = FixtureSpec(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=day,
        preferred_end_date=date(2026, 10, 30),
        hard_end_date=date(2026, 11, 30),
        timezone_name=TZ,
        grid_slots=((0, time(9), time(10)), (0, time(10), time(11)), (0, time(11), time(12))),
        periods=((day, time(9), time(10)), (day, time(10), time(11)), (day, time(11), time(12))),
        assignments=(
            AssignmentSpec(1, 7, (120,), (500,)),
            AssignmentSpec(2, 8, (60,), (500,)),
        ),
        unavailable=(
            ("teacher", 8, (day, time(10), time(11))),
            ("teacher", 8, (day, time(11), time(12))),
        ),
    )
    fixture = build_fixture("protected-room", spec)
    protected = ScheduledLesson(
        lesson_id=1,
        assignment_id=1,
        period=normalize_period(day, time(9), time(10), TZ),
        room_id=500,
        credit_minutes=60,
        slices=(ModuleSlice(1, 1, 0, 60),),
    )
    snapshot = replace(fixture.snapshot, protected_lessons=(protected,))

    result = generate_schedule(snapshot, fixture.periods, time_limit_seconds=10)

    assert result.outcome == "INFEASIBLE"


def _presence_hint(result):
    return [row for row in result.diagnoses if row.code is DiagnosisCode.TEACHER_PRESENCE_RULES]


def _fake_outcome(status, candidate=None, message="stopped"):
    return SearchOutcome(status, candidate, None, None, message, 0.0, {})


def test_generation_infeasible_with_minimum_teachers_reports_the_presence_hint():
    periods = (period(0),)
    target = replace(
        snapshot(periods, minutes=120),
        teacher_presence=(TeacherPresenceRule(1, True, 180, 60),),
    )

    result = generate_complete(
        target, periods, search=lambda *args, **kwargs: None, time_limit_seconds=10
    )

    assert result.outcome == OUTCOME_INFEASIBLE
    hint = _presence_hint(result)
    assert len(hint) == 1
    assert hint[0].evidence_kind is EvidenceKind.ESTIMATE
    assert hint[0].minimum_missing_minutes is None
    assert hint[0].affected_teacher_ids == (1,)


def test_generation_inconclusive_with_minimum_teachers_reports_the_presence_hint():
    periods = (period(0), period(1))
    target = replace(
        snapshot(periods, minutes=60),
        teacher_presence=(TeacherPresenceRule(1, True, 60, 60),),
    )

    def search(*args, **kwargs):
        return _fake_outcome(OUTCOME_INCONCLUSIVE)

    result = generate_complete(target, periods, search=search, time_limit_seconds=10)

    assert result.outcome == OUTCOME_INCONCLUSIVE
    hint = _presence_hint(result)
    assert len(hint) == 1
    assert hint[0].affected_teacher_ids == (1,)


def test_generation_failed_with_minimum_teachers_reports_the_presence_hint():
    periods = (period(0), period(1))
    target = replace(
        snapshot(periods, minutes=60),
        teacher_presence=(TeacherPresenceRule(1, True, 60, 60),),
    )

    def search(*args, **kwargs):
        return _fake_outcome(OUTCOME_COMPLETE, CandidateSchedule(()))

    result = generate_complete(target, periods, search=search, time_limit_seconds=10)

    assert result.outcome == OUTCOME_FAILED
    assert len(_presence_hint(result)) == 1


def test_generation_without_a_minimum_teacher_has_no_presence_hint():
    periods = (period(0),)
    target = replace(
        snapshot(periods, minutes=120),
        teacher_presence=(TeacherPresenceRule(1, False),),
    )

    result = generate_complete(
        target, periods, search=lambda *args, **kwargs: None, time_limit_seconds=10
    )

    assert result.outcome == OUTCOME_INFEASIBLE
    assert _presence_hint(result) == []
