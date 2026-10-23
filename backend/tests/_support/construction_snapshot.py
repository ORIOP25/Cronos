"""Frozen construction evidence; slow artifacts stay outside Git.

Capture is permitted only with the three production sources of the agreed base.
Comparisons never replace a reference, including when they fail.
"""

import json
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import asdict, fields, replace
from datetime import UTC, date, datetime
from functools import lru_cache
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path

import pytest

from app.scheduler.domain.calendar import grid_dates
from app.scheduler.domain.candidate import (
    CandidateSchedule,
    SchedulingStrategy,
    Unavailability,
    UnavailableResource,
)
from app.scheduler.domain.candidate_validation import ValidationViolationCode, validate_candidate
from app.scheduler.domain.capacity import residual_minutes
from app.scheduler.domain.priorities import DEFAULT_LEVELS, SCHOOL_CRITERION_KEYS, PriorityWeights
from app.scheduler.domain.recovery import measure_disruption
from app.scheduler.domain.serialization import (
    candidate_from_dict,
    candidate_to_dict,
    canonical_json,
    canonical_json_value,
    payload_digest,
    snapshot_to_dict,
)
from app.scheduler.infrastructure import search as search_module
from app.scheduler.infrastructure.search import search_complete_schedule
from app.scheduler.lab.realistic_pilot import build_realistic_pilot
from app.scheduler.lab.recovery import laboratory_policy

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / ".test-artifacts" / "construction"
BASE_COMMIT = "5a4fd7d369062eefaf08446f6adb5fa1398e5af6"
LEGACY_BASE_SOURCES = {
    "infrastructure/constructive.py": "5fff3cb324e821425cdc2d3bab275f86d89abad7dd54a4d6521185551a3fc463",
    "infrastructure/recovery_construction.py": "31cf61590336ca8b36e5bba39960f144365369c2c47fc933e3c9724491f74efe",
    "domain/priority_value.py": "a9ed02054f0f520c2e4465b141e106a343aa1d5ef82743b87e7f3c0de828cc94",
}


BASE_SOURCES = {
    "infrastructure/constructive.py": "b709d66f2d3d5b3e89c7c7bc37eb1745d0c4124894155d2c8460c1ac8065ff96",
    "infrastructure/recovery_construction.py": "7f7d95367ba7929adff491e3480860f3f0fdafb689109e2c34b2b5d567b9128b",
    "domain/priority_value.py": "1dc4f28fb6a9be0e59886e0d51ed9bd32dbc454a2dc82f7ee7aaeb857db679c5",
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


def file_digest(path):
    """Hash Python source with the same LF newlines the parser sees on every OS."""
    return sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def source_hashes():
    scheduler = ROOT / "backend" / "app" / "scheduler"
    return {name: file_digest(scheduler / name) for name in BASE_SOURCES}


def assert_base_sources():
    assert source_hashes() == BASE_SOURCES, "Baseline capture requires unchanged base production."
    assert version("ortools") == "9.15.6755"


def provenance():
    return {
        "base_commit": BASE_COMMIT,
        "harness_commit": (EVIDENCE / "harness-commit.txt").read_text(encoding="utf-8-sig").strip(),
        "production_sources": source_hashes(),
        "source_format": "utf8-lf",
        "harness_sha256": file_digest(Path(__file__)),
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
    # Earlier captures pin the exact CRLF files. Both maps name the same base code.
    assert record["provenance"]["production_sources"] in (BASE_SOURCES, LEGACY_BASE_SOURCES)
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
    if profile == "C23":
        assert outcome.status == "INCONCLUSIVE", (profile, outcome.status, outcome.message)
        assert outcome.candidate is None
        assert outcome.quality is None
        assert outcome.evidence is not None
        assert outcome.evidence.objective_scope == "ANNUAL_QUOTA_SEARCH"
        assert outcome.evidence.stop_reason == "SEARCH_STOPPED"
        return {
            "snapshot": snapshot_to_dict(snapshot),
            "periods": [asdict(period) for period in periods],
            "candidate": None,
            "typed_candidate": None,
            "status": outcome.status,
            "message": outcome.message,
            "quality": None,
            "evidence": asdict(outcome.evidence),
        }
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
        report = validate_candidate(changed, active)
        assert report.valid is False
        assert {row.code for row in report.violations} == {
            ValidationViolationCode.RESOURCE_UNAVAILABLE
        }
        expected = {row.lesson_id for row in lessons if row.period in affected}
        assert {row.lesson_id for row in report.violations} == expected
        assert not expected & {row.lesson_id for row in snapshot.protected_lessons}
        assert all(
            row.resource_type == UnavailableResource.TEACHER.value and row.resource_id == teacher
            for row in report.violations
        )
        return changed, periods, active, history, teacher
    raise AssertionError(f"Scenario {event} has no affected teacher without a protected conflict.")


# Update equivalence reuses the two expensive constructions per event.
# Each level still executes the real search selection, room pass and cost.


@contextmanager
def without_update_stability_reads():
    original = PriorityWeights.__getattribute__

    def read(weights, name):
        assert name != "update_stability", "Construction must not read update_stability."
        return original(weights, name)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(PriorityWeights, "__getattribute__", read)
        yield


def quality_record(quality):
    return canonical_json_value(
        {field.name: getattr(quality, field.name) for field in fields(quality)}
    )


@lru_cache(maxsize=2)
def update_pair(event):
    snapshot, periods, active, history, teacher = update_scenario(event)
    frozen_input = read_reference(f"update-input-{event}")
    assert canonical_json_value(snapshot_to_dict(snapshot)) == frozen_input["snapshot"]
    assert canonical_json_value(history) == frozen_input["history"]
    assert teacher == frozen_input["teacher"]
    local_construct = search_module.construct_recovery
    rebuilt_construct = search_module.construct_schedule
    pair = {}
    calls = []

    def local(*args, **kwargs):
        calls.append("local")
        with without_update_stability_reads():
            candidate = local_construct(*args, **kwargs)
        assert candidate is not None, f"{event}: retained construction failed."
        pair["local"] = candidate
        return candidate

    def rebuilt(*args, **kwargs):
        calls.append("rebuilt")
        with without_update_stability_reads():
            candidate = rebuilt_construct(*args, **kwargs)
        assert candidate is not None, f"{event}: rebuilt construction failed."
        pair["rebuilt"] = candidate
        return candidate

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(search_module, "construct_recovery", local)
        patch.setattr(search_module, "construct_schedule", rebuilt)
        outcome = search_module.search_adaptive_schedule(
            snapshot,
            periods,
            active,
            laboratory_policy(snapshot),
            time_limit_seconds=3600,
            random_seed=1,
            num_workers=1,
            stop_at_first_complete=True,
        )
    assert calls == ["local", "rebuilt"]
    assert outcome.status == "COMPLETE"
    assert outcome.candidate is not None
    return snapshot, periods, active, history, teacher, pair


def update_pair_record(event):
    snapshot, _periods, active, history, teacher, pair = update_pair(event)
    return {
        "snapshot": snapshot_to_dict(snapshot),
        "history": history,
        "teacher": teacher,
        "active": candidate_record(active),
        "local": candidate_record(pair["local"]),
        "rebuilt": candidate_record(pair["rebuilt"]),
    }


def run_update_level(event, level):
    snapshot, periods, active, history, teacher, pair = update_pair(event)
    weights = PriorityWeights({**DEFAULT_LEVELS, "update_stability": level})
    planning = replace(snapshot, priority_weights=weights)
    policy = laboratory_policy(planning)
    costs = []
    priorities = []
    original_cost = search_module.priority_cost
    original_outcome = search_module._constructive_outcome
    calls = []

    def cached(name, *args, **kwargs):
        calls.append(name)
        assert args[1] == periods
        restored = replace(args[0], priority_weights=snapshot.priority_weights)
        assert snapshot_to_dict(restored) == snapshot_to_dict(snapshot)
        assert kwargs["weights"] == weights
        assert kwargs["should_cancel"] is None
        if name == "rebuilt":
            assert kwargs["weekly_reference"] == active
        return pair[name]

    def cost(*args, **kwargs):
        value = original_cost(*args, **kwargs)
        costs.append({"metrics": canonical_json_value(args[0]), "value": value})
        return value

    def outcome(*args, **kwargs):
        priorities.append(kwargs["priorities_followed"])
        return original_outcome(*args, **kwargs)

    from functools import partial

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(search_module, "construct_recovery", partial(cached, "local"))
        patch.setattr(search_module, "construct_schedule", partial(cached, "rebuilt"))
        patch.setattr(search_module, "priority_cost", cost)
        patch.setattr(search_module, "_constructive_outcome", outcome)
        result = search_module.search_adaptive_schedule(
            planning,
            periods,
            active,
            policy,
            time_limit_seconds=3600,
            random_seed=1,
            num_workers=1,
            stop_at_first_complete=True,
        )
    assert calls == ["local", "rebuilt"]
    assert result.status == "COMPLETE"
    assert result.candidate is not None
    assert validate_candidate(planning, result.candidate).valid
    assert len(costs) == 2
    assert priorities == [True]
    disruption = measure_disruption(planning, active, result.candidate, policy)
    return {
        "event": event,
        "level": level,
        "history": history,
        "teacher": teacher,
        **candidate_record(result.candidate),
        "status": result.status,
        "evidence": asdict(result.evidence),
        "quality": quality_record(result.quality),
        "costs": costs,
        "disruption": asdict(disruption),
        "priorities_followed": priorities[0],
    }


def write_match_receipt(name, payload, reference):
    """Retain a small proof receipt; never overwrite a frozen base payload."""
    sources = source_hashes()
    sources["infrastructure/construction_support.py"] = file_digest(
        ROOT / "backend" / "app" / "scheduler" / "infrastructure" / "construction_support.py"
    )
    receipt = {
        "base_commit": BASE_COMMIT,
        "reference_sha256": payload_digest(reference),
        "matched_sha256": payload_digest(payload),
        "production_sources": sources,
        "source_format": "utf8-lf",
        "harness_sha256": file_digest(Path(__file__)),
        "ortools": version("ortools"),
        "matched": True,
    }
    assert receipt["matched_sha256"] == receipt["reference_sha256"]
    directory = EVIDENCE / "head"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.json").write_text(canonical_json(receipt), encoding="utf-8")
