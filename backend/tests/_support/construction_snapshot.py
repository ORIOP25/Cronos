"""Frozen construction evidence; slow artifacts stay outside Git.

Capture is permitted only with the three production sources of the agreed base.
Comparisons never replace a reference, including when they fail.
"""

import json
from collections import defaultdict
from dataclasses import asdict, fields, replace
from datetime import UTC, date, datetime
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path

from app.scheduler.domain.calendar import grid_dates
from app.scheduler.domain.candidate import (
    CandidateSchedule,
    SchedulingStrategy,
    Unavailability,
    UnavailableResource,
)
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.domain.capacity import residual_minutes
from app.scheduler.domain.priorities import DEFAULT_LEVELS, SCHOOL_CRITERION_KEYS, PriorityWeights
from app.scheduler.domain.serialization import (
    candidate_from_dict,
    candidate_to_dict,
    canonical_json,
    canonical_json_value,
    payload_digest,
    snapshot_to_dict,
)
from app.scheduler.infrastructure.search import search_complete_schedule
from app.scheduler.lab.realistic_pilot import build_realistic_pilot

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / ".test-artifacts" / "construction"
BASE_COMMIT = "5a4fd7d369062eefaf08446f6adb5fa1398e5af6"
BASE_SOURCES = {
    "infrastructure/constructive.py": "5fff3cb324e821425cdc2d3bab275f86d89abad7dd54a4d6521185551a3fc463",
    "infrastructure/recovery_construction.py": "31cf61590336ca8b36e5bba39960f144365369c2c47fc933e3c9724491f74efe",
    "domain/priority_value.py": "a9ed02054f0f520c2e4465b141e106a343aa1d5ef82743b87e7f3c0de828cc94",
}


def campaign_profiles():
    profiles = {"C01": PriorityWeights(DEFAULT_LEVELS)}
    for key in SCHOOL_CRITERION_KEYS[:-1]:
        for level in (0, 4):
            profiles[f"C{len(profiles) + 1:02d}"] = PriorityWeights({**DEFAULT_LEVELS, key: level})
    profiles["C20"] = PriorityWeights({**DEFAULT_LEVELS, **dict.fromkeys(SCHOOL_CRITERION_KEYS, 2)})
    profiles["C21"] = PriorityWeights({**DEFAULT_LEVELS, "class_gaps": 0, "class_same_room": 4})
    profiles["C22"] = PriorityWeights({**DEFAULT_LEVELS, "teacher_gaps": 0, "class_gaps": 4})
    profiles["C23"] = PriorityWeights(DEFAULT_LEVELS)
    return profiles


def source_hashes():
    scheduler = ROOT / "backend" / "app" / "scheduler"
    return {name: sha256((scheduler / name).read_bytes()).hexdigest() for name in BASE_SOURCES}


def assert_base_sources():
    assert source_hashes() == BASE_SOURCES, "Baseline capture requires unchanged base production."
    assert version("ortools") == "9.15.6755"


def provenance():
    return {
        "base_commit": BASE_COMMIT,
        "harness_commit": (EVIDENCE / "harness-commit.txt").read_text(encoding="utf-8").strip(),
        "production_sources": source_hashes(),
        "harness_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "ortools": version("ortools"),
        "random_seed": 1,
        "num_workers": 1,
        "time_limit_seconds": 3600,
    }


def write_reference(name, payload):
    assert_base_sources()
    record = {"provenance": provenance(), "digest": payload_digest(payload), "payload": payload}
    path = EVIDENCE / "base" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        assert read_reference(name) == canonical_json_value(payload), "References are immutable."
    else:
        with path.open("x", encoding="utf-8") as target:
            target.write(canonical_json(record))


def read_reference(name):
    path = EVIDENCE / "base" / f"{name}.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["provenance"]["base_commit"] == BASE_COMMIT
    assert record["provenance"]["production_sources"] == BASE_SOURCES
    assert record["provenance"]["ortools"] == version("ortools")
    assert record["digest"] == payload_digest(record["payload"])
    return record["payload"]


def candidate_record(candidate):
    assert candidate is not None
    return {
        "candidate": candidate_to_dict(candidate),
        "typed_candidate": canonical_json_value(asdict(candidate)),
    }


def campaign_inputs(profile):
    school = build_realistic_pilot()
    snapshot = replace(school.snapshot, priority_weights=campaign_profiles()[profile])
    if profile == "C23":
        snapshot = replace(
            snapshot,
            assignments=tuple(
                replace(
                    assignment,
                    modules=tuple(
                        replace(
                            module, required_minutes=max(1, module.required_minutes * 70 // 100)
                        )
                        for module in assignment.modules
                    ),
                )
                for assignment in snapshot.assignments
            ),
        )
    return snapshot, school.periods


def run_profile(profile):
    snapshot, periods = campaign_inputs(profile)
    outcome = search_complete_schedule(
        snapshot,
        periods,
        time_limit_seconds=3600,
        random_seed=1,
        num_workers=1,
        stop_at_first_complete=True,
    )
    assert outcome.status == "COMPLETE", (profile, outcome.status, outcome.message)
    assert outcome.candidate is not None
    assert validate_candidate(snapshot, outcome.candidate).valid
    return {
        "snapshot": snapshot_to_dict(snapshot),
        "periods": [asdict(period) for period in periods],
        **candidate_record(outcome.candidate),
        "status": outcome.status,
        "quality": canonical_json_value(
            {field.name: getattr(outcome.quality, field.name) for field in fields(outcome.quality)}
        ),
        "evidence": asdict(outcome.evidence),
    }


def repair_models(monkeypatch):
    from app.scheduler.infrastructure import constructive
    from tests.unit.test_scheduler_weighted_construction_v1 import (
        test_period_repair_models_keep_their_variables_hints_and_objective,
    )

    models = []
    original = constructive.cp_model.CpSolver

    class RecordingSolver(original):
        def Solve(self, model):
            models.append(str(model.Proto()))
            return super().Solve(model)

    monkeypatch.setattr(constructive.cp_model, "CpSolver", RecordingSolver)
    test_period_repair_models_keep_their_variables_hints_and_objective(monkeypatch)
    assert len(models) == 4
    return models


def update_inputs():
    """Materialize executed credit once per teaching unit, never per member class."""
    baseline = read_reference("C01")
    full = candidate_from_dict(baseline["candidate"])
    snapshot, periods = campaign_inputs("C01")
    now = datetime(2027, 2, 22, tzinfo=UTC)
    executed = defaultdict(lambda: defaultdict(int))
    for lesson in full.lessons:
        assert not lesson.period.start_utc <= now < lesson.period.end_utc
        if lesson.period.end_utc <= now:
            for part in lesson.slices:
                executed[lesson.assignment_id][part.module_id] += part.credit_minutes
    active = CandidateSchedule(
        tuple(lesson for lesson in full.lessons if lesson.period.start_utc > now)
    )
    protected_dates = frozenset(
        grid_dates(
            now.date(), date(2027, 2, 26), {slot.day_of_week for slot in snapshot.grid_slots}
        )
    )
    protected = tuple(
        lesson for lesson in active.lessons if lesson.period.school_date in protected_dates
    )
    planning = replace(
        snapshot,
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        now_utc=now,
        executed_minutes={identity: dict(modules) for identity, modules in executed.items()},
        baseline_lessons=active.lessons,
        protected_lessons=protected,
        protected_dates=protected_dates,
        reserved_lesson_ids=frozenset(row.lesson_id for row in full.lessons),
    )
    assert validate_candidate(planning, active).valid
    for assignment in planning.assignments:
        identity = assignment.assignment_id
        required = sum(module.required_minutes for module in assignment.modules)
        completed = sum(executed[identity].values())
        frozen = sum(row.credit_minutes for row in protected if row.assignment_id == identity)
        assert required == completed + frozen + residual_minutes(planning, identity)
    return planning, periods, active, dict(executed)


def update_scenario(event):
    snapshot, periods, active, history = update_inputs()
    affected = {
        period
        for period in periods
        if (
            date(2027, 3, 1) <= period.school_date <= date(2027, 3, 12)
            if event == "A"
            else date(2027, 3, 3) <= period.school_date and period.school_date.weekday() == 2
        )
    }
    minimum = {
        row.teacher_id for row in snapshot.teacher_presence if row.minimum_minutes is not None
    }
    teachers = sorted({row.teacher_id for row in snapshot.assignments} - minimum)
    for teacher in teachers:
        lessons = [
            row
            for row in active.lessons
            if snapshot.assignment_for(row.assignment_id).teacher_id == teacher
        ]
        if not any(row.period in affected for row in lessons):
            continue
        if any(
            row.period in affected
            for row in snapshot.protected_lessons
            if snapshot.assignment_for(row.assignment_id).teacher_id == teacher
        ):
            continue
        changed = replace(
            snapshot,
            unavailable=(
                *snapshot.unavailable,
                *(
                    Unavailability(UnavailableResource.TEACHER, teacher, period)
                    for period in sorted(affected, key=lambda row: row.start_utc)
                ),
            ),
        )
        assert not validate_candidate(changed, active).valid
        return changed, periods, active, history, teacher
    raise AssertionError(f"Scenario {event} has no affected teacher without a protected conflict.")
