"""JSON manifests with separated seeds and deterministic case reproduction."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

from app.scheduler.domain.candidate import SchedulingStrategy
from app.scheduler.domain.serialization import (
    canonical_json as _canonical,
)
from app.scheduler.domain.serialization import (
    lesson_to_dict,
    period_to_dict,
)
from app.scheduler.domain.serialization import (
    time_token as _time_token,
)
from app.scheduler.lab.annual import build_annual_fixture
from app.scheduler.lab.fixtures import (
    AssignmentSpec,
    CaseExpectation,
    Fixture,
    FixtureSpec,
    build_fixture,
    mutate,
)
from app.scheduler.lab.scale import build_scale_fixture

SCHEMA_VERSION = "scheduler-lab-v3"


@dataclass(frozen=True)
class ScaleCaseSpec:
    class_count: int
    module_minutes: int = 240
    seed: int = 1


@dataclass(frozen=True)
class AnnualCaseSpec:
    class_count: int
    profile: str = "loose"
    seed: int = 1
    events: int = 0
    step_days: int = 14


@dataclass(frozen=True)
class CaseSeeds:
    fixture_seed: int
    event_seed: int
    solver_seed: int

    def __post_init__(self) -> None:
        if any(
            type(seed) is not int or seed < 0
            for seed in (self.fixture_seed, self.event_seed, self.solver_seed)
        ):
            raise ValueError("Case seeds must be nonnegative integers.")


@dataclass(frozen=True)
class LabCase:
    case_id: str
    family: str
    version: int
    expectation: CaseExpectation
    spec: FixtureSpec | None
    seeds: CaseSeeds
    mutation: str | None = None
    expected_violations: tuple[str, ...] = ()
    scale: ScaleCaseSpec | None = None
    annual: AnnualCaseSpec | None = None
    events: tuple[int, ...] = ()
    witness_mode: str = "oracle"


def spec_to_dict(spec: FixtureSpec) -> dict[str, Any]:
    return {
        "strategy": spec.strategy.value,
        "origin": spec.origin.isoformat(),
        "preferred_end_date": spec.preferred_end_date.isoformat(),
        "hard_end_date": spec.hard_end_date.isoformat(),
        "timezone_name": spec.timezone_name,
        "grid_slots": [
            [day_of_week, _time_token(start), _time_token(end)]
            for day_of_week, start, end in spec.grid_slots
        ],
        "periods": [
            [day.isoformat(), _time_token(start), _time_token(end)]
            for day, start, end in spec.periods
        ],
        "assignments": [
            {
                "class_id": row.class_id,
                "teacher_id": row.teacher_id,
                "module_minutes": list(row.module_minutes),
                "eligible_rooms": list(row.eligible_rooms),
            }
            for row in spec.assignments
        ],
        "blocked_dates": sorted(day.isoformat() for day in spec.blocked_dates),
        "executed_minutes": sorted(
            [assignment_id, sorted([module_id, minutes] for module_id, minutes in rows)]
            for assignment_id, rows in spec.executed_minutes
        ),
        "unavailable": sorted(
            [
                [
                    resource_type,
                    resource_id,
                    [day.isoformat(), _time_token(start), _time_token(end)],
                ]
                for resource_type, resource_id, (day, start, end) in spec.unavailable
            ]
        ),
        "soft_unavailable": sorted(
            [
                [
                    resource_type,
                    resource_id,
                    [day.isoformat(), _time_token(start), _time_token(end)],
                ]
                for resource_type, resource_id, (day, start, end) in spec.soft_unavailable
            ]
        ),
        "protected_dates": sorted(day.isoformat() for day in spec.protected_dates),
        "now_utc": None if spec.now_utc is None else spec.now_utc.isoformat(),
        "reservations": sorted([list(row) for row in spec.reservations]),
        "open_debt_minutes": sorted(
            [claim_id, minutes] for claim_id, minutes in spec.open_debt_minutes
        ),
        "claim_assignments": sorted(
            [claim_id, assignment_id] for claim_id, assignment_id in spec.claim_assignments
        ),
        "active_version_id": spec.active_version_id,
    }


def spec_from_dict(data: dict[str, Any]) -> FixtureSpec:
    return FixtureSpec(
        strategy=SchedulingStrategy(data["strategy"]),
        origin=date.fromisoformat(data["origin"]),
        preferred_end_date=date.fromisoformat(data["preferred_end_date"]),
        hard_end_date=date.fromisoformat(data["hard_end_date"]),
        timezone_name=data["timezone_name"],
        grid_slots=tuple(
            (day_of_week, time.fromisoformat(start), time.fromisoformat(end))
            for day_of_week, start, end in data["grid_slots"]
        ),
        periods=tuple(
            (date.fromisoformat(day), time.fromisoformat(start), time.fromisoformat(end))
            for day, start, end in data["periods"]
        ),
        assignments=tuple(
            AssignmentSpec(
                class_id=row["class_id"],
                teacher_id=row["teacher_id"],
                module_minutes=tuple(row["module_minutes"]),
                eligible_rooms=tuple(row["eligible_rooms"]),
            )
            for row in data["assignments"]
        ),
        blocked_dates=frozenset(date.fromisoformat(day) for day in data["blocked_dates"]),
        executed_minutes=tuple(
            (assignment_id, tuple((module_id, minutes) for module_id, minutes in rows))
            for assignment_id, rows in data["executed_minutes"]
        ),
        unavailable=tuple(
            (
                resource_type,
                resource_id,
                (date.fromisoformat(day), time.fromisoformat(start), time.fromisoformat(end)),
            )
            for resource_type, resource_id, (day, start, end) in data["unavailable"]
        ),
        soft_unavailable=tuple(
            (
                resource_type,
                resource_id,
                (date.fromisoformat(day), time.fromisoformat(start), time.fromisoformat(end)),
            )
            for resource_type, resource_id, (day, start, end) in data.get("soft_unavailable", ())
        ),
        protected_dates=frozenset(date.fromisoformat(day) for day in data["protected_dates"]),
        now_utc=None if data["now_utc"] is None else datetime.fromisoformat(data["now_utc"]),
        reservations=tuple(tuple(row) for row in data["reservations"]),
        open_debt_minutes=tuple(
            (claim_id, minutes) for claim_id, minutes in data["open_debt_minutes"]
        ),
        claim_assignments=tuple(
            (claim_id, assignment_id) for claim_id, assignment_id in data["claim_assignments"]
        ),
        active_version_id=data["active_version_id"],
    )


def case_to_dict(case: LabCase) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "family": case.family,
        "version": case.version,
        "expectation": case.expectation.value,
        "mutation": case.mutation,
        "expected_violations": list(case.expected_violations),
        "seeds": {
            "fixture_seed": case.seeds.fixture_seed,
            "event_seed": case.seeds.event_seed,
            "solver_seed": case.seeds.solver_seed,
        },
        "spec": None if case.spec is None else spec_to_dict(case.spec),
        "scale": (
            None
            if case.scale is None
            else {
                "class_count": case.scale.class_count,
                "module_minutes": case.scale.module_minutes,
                "seed": case.scale.seed,
            }
        ),
        "annual": (
            None
            if case.annual is None
            else {
                "class_count": case.annual.class_count,
                "profile": case.annual.profile,
                "seed": case.annual.seed,
                "events": case.annual.events,
                "step_days": case.annual.step_days,
            }
        ),
        "events": list(case.events),
        "witness_mode": case.witness_mode,
    }


def case_from_dict(data: dict[str, Any]) -> LabCase:
    spec_data = data.get("spec")
    scale_data = data.get("scale")
    annual_data = data.get("annual")
    provided = sum(row is not None for row in (spec_data, scale_data, annual_data))
    if provided != 1:
        raise ValueError("A case needs exactly one of spec, scale or annual.")
    return LabCase(
        case_id=data["case_id"],
        family=data["family"],
        version=data["version"],
        expectation=CaseExpectation(data["expectation"]),
        spec=None if spec_data is None else spec_from_dict(spec_data),
        seeds=CaseSeeds(
            data["seeds"]["fixture_seed"],
            data["seeds"]["event_seed"],
            data["seeds"]["solver_seed"],
        ),
        mutation=data.get("mutation"),
        expected_violations=tuple(data.get("expected_violations", ())),
        scale=(
            None
            if scale_data is None
            else ScaleCaseSpec(
                scale_data["class_count"],
                scale_data.get("module_minutes", 240),
                scale_data.get("seed", 1),
            )
        ),
        annual=(
            None
            if annual_data is None
            else AnnualCaseSpec(
                annual_data["class_count"],
                annual_data.get("profile", "loose"),
                annual_data.get("seed", 1),
                annual_data.get("events", 0),
                annual_data.get("step_days", 14),
            )
        ),
        events=tuple(int(seed) for seed in data.get("events", ())),
        witness_mode=data.get("witness_mode", "oracle"),
    )


def to_manifest(campaign_id: str, cases: tuple[LabCase, ...]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": campaign_id,
        "cases": [case_to_dict(case) for case in cases],
    }


def from_manifest(manifest: dict[str, Any]) -> tuple[str, tuple[LabCase, ...]]:
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported scheduler lab manifest schema.")
    cases = tuple(case_from_dict(row) for row in manifest["cases"])
    identifiers = [case.case_id for case in cases]
    duplicates = sorted({case_id for case_id in identifiers if identifiers.count(case_id) > 1})
    if duplicates:
        raise ValueError(f"Duplicate case IDs in manifest: {duplicates}")
    return manifest["campaign_id"], cases


def build_case(case: LabCase) -> Fixture:
    if case.scale is not None:
        built = build_scale_fixture(
            case.scale.class_count,
            seed=case.scale.seed,
            module_minutes=case.scale.module_minutes,
        )
        fixture = Fixture(
            case_id=case.case_id,
            family=case.family,
            version=case.version,
            expectation=case.expectation,
            snapshot=built.snapshot,
            periods=built.periods,
            witness=built.witness,
            fixture_seed=case.seeds.fixture_seed,
            event_seed=case.seeds.event_seed,
            solver_seed=case.seeds.solver_seed,
        )
    elif case.annual is not None:
        built = build_annual_fixture(
            case.annual.class_count,
            profile=case.annual.profile,
            seed=case.annual.seed,
        )
        fixture = Fixture(
            case_id=case.case_id,
            family=case.family,
            version=case.version,
            expectation=case.expectation,
            snapshot=built.snapshot,
            periods=built.periods,
            witness=built.witness,
            fixture_seed=case.seeds.fixture_seed,
            event_seed=case.seeds.event_seed,
            solver_seed=case.seeds.solver_seed,
        )
    else:
        assert case.spec is not None
        fixture = build_fixture(
            case.case_id,
            case.spec,
            family=case.family,
            version=case.version,
            expectation=case.expectation,
            fixture_seed=case.seeds.fixture_seed,
            event_seed=case.seeds.event_seed,
            solver_seed=case.seeds.solver_seed,
        )
    if case.mutation is not None:
        fixture = mutate(fixture, case.mutation)
    return fixture


def input_digest(fixture: Fixture) -> str:
    """Digest of the mathematical inputs and witness, independent of solver seed."""
    snapshot = fixture.snapshot
    payload = {
        "strategy": snapshot.strategy.value,
        "origin": snapshot.origin.isoformat(),
        "preferred_end_date": snapshot.preferred_end_date.isoformat(),
        "hard_end_date": snapshot.hard_end_date.isoformat(),
        "timezone_name": snapshot.timezone_name,
        "grid_slots": sorted(
            [slot.day_of_week, _time_token(slot.start_local), _time_token(slot.end_local)]
            for slot in snapshot.grid_slots
        ),
        "blocked_dates": sorted(day.isoformat() for day in snapshot.blocked_dates),
        "unavailable": sorted(
            [row.resource_type.value, row.resource_id, period_to_dict(row.period)]
            for row in snapshot.unavailable
        ),
        "soft_unavailable": sorted(
            [row.resource_type.value, row.resource_id, period_to_dict(row.period)]
            for row in snapshot.soft_unavailable
        ),
        "protected_dates": sorted(day.isoformat() for day in snapshot.protected_dates),
        "now_utc": None if snapshot.now_utc is None else snapshot.now_utc.isoformat(),
        "assignments": sorted(
            [
                row.assignment_id,
                row.class_id,
                row.subject_id,
                row.teacher_id,
                sorted(row.eligible_room_ids),
                sorted(
                    [module.module_id, module.sequence, module.required_minutes]
                    for module in row.modules
                ),
            ]
            for row in snapshot.assignments
        ),
        "executed": sorted(
            [assignment_id, sorted([module_id, minutes] for module_id, minutes in rows.items())]
            for assignment_id, rows in snapshot.executed_minutes.items()
        ),
        "reservations": sorted(
            [row.version_id, row.lesson_id, row.claim_id, row.minutes]
            for row in snapshot.reservations
        ),
        "open_debt": sorted(
            [claim_id, minutes] for claim_id, minutes in snapshot.open_debt_minutes.items()
        ),
        "claim_assignments": sorted(
            [claim_id, assignment_id]
            for claim_id, assignment_id in snapshot.claim_assignments.items()
        ),
        "active_version_id": snapshot.active_version_id,
        "protected": sorted(lesson_to_dict(lesson) for lesson in snapshot.protected_lessons),
        "baseline": sorted(lesson_to_dict(lesson) for lesson in snapshot.baseline_lessons),
        "periods": sorted(period_to_dict(period) for period in fixture.periods),
        "witness": (
            None
            if fixture.witness is None
            else sorted(lesson_to_dict(lesson) for lesson in fixture.witness.lessons)
        ),
    }
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def manifest_digest(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(manifest).encode("utf-8")).hexdigest()
