"""W10 combined campaign manifests: factor matrix, interactions, boundaries, replays.

The manifests are generated from explicit level interpretations so the declared
pairwise matrix is complete by construction. Generating a case is not executing
it: coverage is measured later from the campaign report.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from app.scheduler.domain.candidate import SchedulingStrategy
from app.scheduler.lab.annual import (
    PROFILE_LOOSE,
    PROFILE_SCARCE_ROOMS,
    PROFILE_SHARED_TEACHER,
)
from app.scheduler.lab.boundaries import block_resource, remove_grid_slot
from app.scheduler.lab.fixtures import AssignmentSpec, CaseExpectation, FixtureSpec
from app.scheduler.lab.manifest import (
    AnnualCaseSpec,
    CaseSeeds,
    LabCase,
    to_manifest,
)
from app.scheduler.lab.matrix import covering_array

ORIGIN = date(2026, 9, 21)
TIMEZONE = "Europe/Lisbon"

PAIR_AXES = {
    "demand": ("1h", "10h", "50h"),
    "credit": ("full", "partial"),
    "modules": ("single", "crossing"),
    "space": ("tight", "ample"),
    "teachers": ("independent", "shared"),
    "rooms": ("alternatives", "specific"),
    "history": ("clean", "executed"),
    "stability": ("editable", "protected"),
    "horizon": ("short", "long"),
    "events": ("cancel", "absence", "room-closed", "combined"),
}

EVENT_LEVELS = {
    "cancel": (0, ()),
    "absence": (1, ()),
    "room-closed": (2, ()),
    "combined": (0, (1, 2)),
}

DEMAND_MINUTES = {"1h": 60, "10h": 600, "50h": 3000}
EVENT_SLACK_PERIODS = {"cancel": 2, "room-closed": 2, "absence": 6, "combined": 8}

BOUNDARY_AXES = {
    "resource": ("room", "teacher", "grid"),
    "pressure": ("removed", "restored"),
}


def _weekdays(count: int) -> tuple[date, ...]:
    days: list[date] = []
    day = ORIGIN
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return tuple(days)


def _split_modules(base: int) -> tuple[int, ...]:
    first = max(1, base // 3)
    return (first, base - first)


def _interaction_spec(
    *,
    demand: str,
    credit: str,
    modules: str,
    space: str,
    teachers: str,
    rooms: str,
    history: str,
    stability: str,
    horizon: str,
    events: str = "",
    preferred_days: int | None = None,
) -> FixtureSpec:
    """Interpret one matrix row as a constructible repair scenario.

    ``events`` belongs to the matrix declaration and is applied by the case
    builder; the spec only carries the physical topology. Capacity is scaled so
    every declared combination has a constructive witness.
    """
    base = DEMAND_MINUTES[demand] + (30 if credit == "partial" else 0)
    per_teacher = base * (2 if teachers == "shared" else 1)
    period_count = (
        -(-per_teacher // 60) + (2 if space == "tight" else 8) + EVENT_SLACK_PERIODS.get(events, 0)
    )
    days = _weekdays(period_count)
    grid_slots = tuple(dict.fromkeys((day.weekday(), time(9), time(10)) for day in days))
    periods = tuple((day, time(9), time(10)) for day in days)
    module_minutes = (base,) if modules == "single" else _split_modules(base)
    second_teacher = 7 if teachers == "shared" else 8
    first_rooms = (500, 501) if rooms == "alternatives" else (500,)
    second_rooms = (502, 503) if rooms == "alternatives" else (501,)
    executed: tuple[tuple[int, tuple[tuple[int, int], ...]], ...] = ()
    if history == "executed":
        consumed = max(1, min(60, module_minutes[0] // 2))
        executed = ((1, ((1, consumed),)), (2, ((1, consumed),)))
    if preferred_days is not None:
        preferred = ORIGIN + timedelta(days=preferred_days)
    elif horizon == "short":
        preferred = ORIGIN + timedelta(days=6)
    else:
        preferred = days[-1] + timedelta(days=14)
    hard = max(preferred + timedelta(days=21), days[-1] + timedelta(days=14))
    return FixtureSpec(
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        origin=ORIGIN,
        preferred_end_date=preferred,
        hard_end_date=hard,
        timezone_name=TIMEZONE,
        grid_slots=grid_slots,
        periods=periods,
        assignments=(
            AssignmentSpec(1, 7, module_minutes, first_rooms),
            AssignmentSpec(2, second_teacher, module_minutes, second_rooms),
        ),
        executed_minutes=executed,
        now_utc=datetime(2026, 9, 24, 8, 0, tzinfo=UTC) if stability == "protected" else None,
    )


def _interaction_case(
    case_id: str,
    family: str,
    levels: dict[str, str],
    *,
    index: int,
    events: tuple[int, tuple[int, ...]] | None = None,
    preferred_days: int | None = None,
) -> LabCase:
    primary, extras = events or EVENT_LEVELS[levels["events"]]
    return LabCase(
        case_id=case_id,
        family=family,
        version=1,
        expectation=CaseExpectation.EXPLORATORY_UNKNOWN,
        spec=_interaction_spec(**levels, preferred_days=preferred_days),
        seeds=CaseSeeds(1 + index, primary, 1 + index),
        events=extras,
        witness_mode="constructed",
    )


def _explicit_cases() -> tuple[tuple[LabCase, dict[str, str]], ...]:
    return (
        (
            _interaction_case(
                "w10-c08-teacher-room-calendar",
                "C08",
                {
                    "demand": "1h",
                    "credit": "partial",
                    "modules": "crossing",
                    "space": "tight",
                    "teachers": "shared",
                    "rooms": "specific",
                    "history": "clean",
                    "stability": "editable",
                    "horizon": "long",
                    "events": "combined",
                },
                index=1,
            ),
            {
                "demand": "1h",
                "credit": "partial",
                "modules": "crossing",
                "space": "tight",
                "teachers": "shared",
                "rooms": "specific",
                "history": "clean",
                "stability": "editable",
                "horizon": "long",
                "events": "combined",
            },
        ),
        (
            _interaction_case(
                "w10-c10-recovery-after-preferred",
                "C10",
                {
                    "demand": "1h",
                    "credit": "full",
                    "modules": "single",
                    "space": "tight",
                    "teachers": "shared",
                    "rooms": "specific",
                    "history": "clean",
                    "stability": "editable",
                    "horizon": "short",
                    "events": "cancel",
                },
                index=2,
                preferred_days=2,
            ),
            {
                "demand": "1h",
                "credit": "full",
                "modules": "single",
                "space": "tight",
                "teachers": "shared",
                "rooms": "specific",
                "history": "clean",
                "stability": "editable",
                "horizon": "short",
                "events": "cancel",
            },
        ),
        (
            _interaction_case(
                "w10-c11-stability-margin",
                "C11",
                {
                    "demand": "10h",
                    "credit": "partial",
                    "modules": "crossing",
                    "space": "ample",
                    "teachers": "independent",
                    "rooms": "specific",
                    "history": "clean",
                    "stability": "protected",
                    "horizon": "long",
                    "events": "absence",
                },
                index=3,
            ),
            {
                "demand": "10h",
                "credit": "partial",
                "modules": "crossing",
                "space": "ample",
                "teachers": "independent",
                "rooms": "specific",
                "history": "clean",
                "stability": "protected",
                "horizon": "long",
                "events": "absence",
            },
        ),
        (
            _interaction_case(
                "w10-c12-accumulated-events",
                "C12",
                {
                    "demand": "10h",
                    "credit": "full",
                    "modules": "crossing",
                    "space": "ample",
                    "teachers": "shared",
                    "rooms": "alternatives",
                    "history": "executed",
                    "stability": "editable",
                    "horizon": "long",
                    "events": "combined",
                },
                index=4,
                events=(0, (1, 2, 0)),
            ),
            {
                "demand": "10h",
                "credit": "full",
                "modules": "crossing",
                "space": "ample",
                "teachers": "shared",
                "rooms": "alternatives",
                "history": "executed",
                "stability": "editable",
                "horizon": "long",
                "events": "combined",
            },
        ),
        (
            _interaction_case(
                "w10-c03-shared-teacher-pressure",
                "C03",
                {
                    "demand": "50h",
                    "credit": "full",
                    "modules": "single",
                    "space": "tight",
                    "teachers": "shared",
                    "rooms": "specific",
                    "history": "clean",
                    "stability": "editable",
                    "horizon": "long",
                    "events": "absence",
                },
                index=5,
            ),
            {
                "demand": "50h",
                "credit": "full",
                "modules": "single",
                "space": "tight",
                "teachers": "shared",
                "rooms": "specific",
                "history": "clean",
                "stability": "editable",
                "horizon": "long",
                "events": "absence",
            },
        ),
    )


def combined_manifest() -> dict[str, Any]:
    rows = covering_array(PAIR_AXES)
    cases: list[LabCase] = []
    matrix_cases: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        case = _interaction_case(f"w10-pair-{index:02d}", "W10-PAIR", row, index=index)
        cases.append(case)
        matrix_cases.append({"case_id": case.case_id, "levels": dict(row)})
    for case, levels in _explicit_cases():
        cases.append(case)
        matrix_cases.append({"case_id": case.case_id, "levels": dict(levels)})
    manifest = to_manifest("w10-combined", tuple(cases))
    manifest["matrix"] = {
        "axes": {axis: list(levels) for axis, levels in PAIR_AXES.items()},
        "cases": matrix_cases,
        "exclusions": [],
    }
    manifest["coverage"] = {
        "mandatory_levels": {axis: list(levels) for axis, levels in PAIR_AXES.items()},
        "critical_interactions": [
            "many-hours x tight-space x shared-teacher x absence",
            "partial-credit x crossing-modules x substitution-history x combined-events",
            "specific-room x stability-window x after-preferred",
            "easy-solution x final-weeks-blocked",
        ],
    }
    return manifest


def _boundary_base() -> FixtureSpec:
    return FixtureSpec(
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        origin=ORIGIN,
        preferred_end_date=ORIGIN + timedelta(days=4),
        hard_end_date=ORIGIN + timedelta(days=10),
        timezone_name=TIMEZONE,
        grid_slots=((0, time(9), time(10)), (2, time(9), time(10))),
        periods=((ORIGIN, time(9), time(10)), (ORIGIN + timedelta(days=2), time(9), time(10))),
        assignments=(AssignmentSpec(1, 100, (100,), (500,)),),
    )


def _boundary_specs(resource: str) -> tuple[FixtureSpec, FixtureSpec]:
    base = _boundary_base()
    if resource == "room":
        transition = block_resource(base, "room", 500)
    elif resource == "teacher":
        transition = block_resource(base, "teacher", 100)
    elif resource == "grid":
        transition = remove_grid_slot(base)
    else:
        raise ValueError(f"Unknown boundary resource: {resource}")
    return transition.pressure, transition.reversal


def boundary_manifest() -> dict[str, Any]:
    cases: list[LabCase] = []
    for resource in BOUNDARY_AXES["resource"]:
        pressure, reversal = _boundary_specs(resource)
        cases.append(
            LabCase(
                f"w10-b-{resource}-removed",
                "W10-BOUNDARY",
                1,
                CaseExpectation.INFEASIBLE_PROVEN,
                pressure,
                CaseSeeds(1, 0, 1),
            )
        )
        cases.append(
            LabCase(
                f"w10-b-{resource}-restored",
                "W10-BOUNDARY",
                1,
                CaseExpectation.FEASIBLE_WITH_WITNESS,
                reversal,
                CaseSeeds(1, 0, 2),
            )
        )
    manifest = to_manifest("w10-boundaries", tuple(cases))
    manifest["matrix"] = {
        "axes": {axis: list(levels) for axis, levels in BOUNDARY_AXES.items()},
        "cases": [
            {
                "case_id": case.case_id,
                "levels": {
                    "resource": case.case_id.split("-")[2],
                    "pressure": "removed" if case.case_id.endswith("-removed") else "restored",
                },
            }
            for case in cases
        ],
        "exclusions": [],
    }
    return manifest


def reserved_repair_manifest() -> dict[str, Any]:
    """W12.4 reserved evaluation: topologies and seeds unused in calibration."""
    base = FixtureSpec(
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        origin=date(2026, 11, 2),
        preferred_end_date=date(2026, 12, 4),
        hard_end_date=date(2027, 1, 15),
        timezone_name=TIMEZONE,
        grid_slots=((0, time(10), time(11)), (1, time(10), time(11)), (2, time(10), time(11))),
        periods=(
            (date(2026, 11, 2), time(10), time(11)),
            (date(2026, 11, 3), time(10), time(11)),
            (date(2026, 11, 4), time(10), time(11)),
            (date(2026, 11, 9), time(10), time(11)),
        ),
        assignments=(
            AssignmentSpec(1, 21, (120,), (700, 701)),
            AssignmentSpec(2, 22, (60,), (702,)),
            AssignmentSpec(3, 23, (60,), (703,)),
            AssignmentSpec(4, 21, (60,), (704,)),
        ),
    )
    cases = (
        LabCase(
            "w12-reserved-01",
            "RESERVED",
            1,
            CaseExpectation.EXPLORATORY_UNKNOWN,
            base,
            CaseSeeds(7, 1, 11),
            events=(2,),
        ),
        LabCase(
            "w12-reserved-02",
            "RESERVED",
            1,
            CaseExpectation.EXPLORATORY_UNKNOWN,
            replace(
                base,
                preferred_end_date=date(2026, 11, 13),
                periods=base.periods[:3],
                grid_slots=base.grid_slots[:3],
            ),
            CaseSeeds(8, 2, 12),
        ),
        LabCase(
            "w12-reserved-03",
            "RESERVED",
            1,
            CaseExpectation.EXPLORATORY_UNKNOWN,
            replace(
                base,
                assignments=(
                    AssignmentSpec(1, 21, (180,), (700,)),
                    AssignmentSpec(2, 24, (120,), (700, 701)),
                ),
            ),
            CaseSeeds(9, 0, 13),
            events=(1, 2),
        ),
    )
    return to_manifest("w12-reserved-repair", cases)


def reserved_annual_manifest() -> dict[str, Any]:
    cases = (
        LabCase(
            "w12-reserved-annual-20",
            "RESERVED",
            1,
            CaseExpectation.EXPLORATORY_UNKNOWN,
            None,
            CaseSeeds(11, 9, 17),
            annual=AnnualCaseSpec(20, PROFILE_LOOSE, 3, events=3, step_days=21),
        ),
        LabCase(
            "w12-reserved-annual-15-connected",
            "RESERVED",
            1,
            CaseExpectation.EXPLORATORY_UNKNOWN,
            None,
            CaseSeeds(12, 10, 18),
            annual=AnnualCaseSpec(15, "connected", 2, events=2, step_days=21),
        ),
    )
    return to_manifest("w12-reserved-annual", cases)


def annual_replay_manifest() -> dict[str, Any]:
    cases = (
        LabCase(
            "w10-replay-10-loose",
            "C14",
            1,
            CaseExpectation.EXPLORATORY_UNKNOWN,
            None,
            CaseSeeds(1, 1, 1),
            annual=AnnualCaseSpec(10, PROFILE_LOOSE, 1, events=3, step_days=14),
        ),
        LabCase(
            "w10-replay-30-shared",
            "C14",
            1,
            CaseExpectation.EXPLORATORY_UNKNOWN,
            None,
            CaseSeeds(1, 2, 2),
            annual=AnnualCaseSpec(30, PROFILE_SHARED_TEACHER, 1, events=2, step_days=14),
        ),
        LabCase(
            "w10-replay-45-scarce-rooms",
            "C14",
            1,
            CaseExpectation.EXPLORATORY_UNKNOWN,
            None,
            CaseSeeds(1, 3, 3),
            annual=AnnualCaseSpec(45, PROFILE_SCARCE_ROOMS, 1, events=2, step_days=14),
        ),
        LabCase(
            "w10-replay-60-shared",
            "C14",
            1,
            CaseExpectation.EXPLORATORY_UNKNOWN,
            None,
            CaseSeeds(1, 4, 4),
            annual=AnnualCaseSpec(60, PROFILE_SHARED_TEACHER, 1, events=2, step_days=14),
        ),
    )
    manifest = to_manifest("w10-annual-replay", cases)
    manifest["replay"] = {
        "scales": [10, 30, 45, 60],
        "profiles": [PROFILE_LOOSE, PROFILE_SHARED_TEACHER, PROFILE_SCARCE_ROOMS],
        "step_days": 14,
    }
    return manifest


def holdout_repair_manifest() -> dict[str, Any]:
    """R12.3 untouched holdout: new topologies and seeds after all corrections."""
    cases = (
        _interaction_case(
            "w12r-holdout-01",
            "HOLDOUT",
            {
                "demand": "10h",
                "credit": "partial",
                "modules": "crossing",
                "space": "tight",
                "teachers": "shared",
                "rooms": "specific",
                "history": "executed",
                "stability": "editable",
                "horizon": "long",
                "events": "absence",
            },
            index=21,
        ),
        _interaction_case(
            "w12r-holdout-02",
            "HOLDOUT",
            {
                "demand": "1h",
                "credit": "full",
                "modules": "crossing",
                "space": "ample",
                "teachers": "independent",
                "rooms": "alternatives",
                "history": "clean",
                "stability": "protected",
                "horizon": "short",
                "events": "combined",
            },
            index=22,
        ),
    )
    return to_manifest("w12r-holdout-repair", cases)


def holdout_annual_manifest() -> dict[str, Any]:
    """The first design (3 events x 21 days) was voided: the anticipation policy
    consumed the plan before the third event. This valid holdout keeps two
    events on a 14-day cadence, matching the earlier replay protocol."""
    case = LabCase(
        "w12r-holdout-annual-15",
        "HOLDOUT",
        2,
        CaseExpectation.EXPLORATORY_UNKNOWN,
        None,
        CaseSeeds(31, 7, 23),
        annual=AnnualCaseSpec(15, PROFILE_SCARCE_ROOMS, 5, events=2, step_days=14),
    )
    return to_manifest("w12r-holdout-annual", (case,))


def online_policy_manifest() -> dict[str, Any]:
    """R11.2 online evaluation: a family not used in the offline calibration."""
    case = LabCase(
        "annual-30-loose-cancel-online",
        "ONLINE",
        1,
        CaseExpectation.EXPLORATORY_UNKNOWN,
        None,
        CaseSeeds(5, 0, 5),
        annual=AnnualCaseSpec(30, PROFILE_LOOSE, 1),
    )
    return to_manifest("w11-online-policy", (case,))


MANIFEST_BUILDERS = {
    "combined": combined_manifest,
    "boundaries": boundary_manifest,
    "annual-replay": annual_replay_manifest,
    "reserved": reserved_repair_manifest,
    "reserved-annual": reserved_annual_manifest,
    "online-policy": online_policy_manifest,
    "holdout": holdout_repair_manifest,
    "holdout-annual": holdout_annual_manifest,
}


def write_manifest(kind: str, path: Path) -> dict[str, Any]:
    manifest = MANIFEST_BUILDERS[kind]()
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a W10 combined lab manifest.")
    parser.add_argument("--kind", required=True, choices=sorted(MANIFEST_BUILDERS))
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    manifest = write_manifest(args.kind, Path(args.out))
    print(f"[w10] {args.kind}: {len(manifest['cases'])} case(s) written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
