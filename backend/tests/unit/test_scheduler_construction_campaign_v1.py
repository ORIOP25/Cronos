"""Manual equivalence campaign; never part of the critical fast manifest."""

import pytest

from app.scheduler.domain.serialization import canonical_json_value, snapshot_to_dict
from tests._support.construction_snapshot import (
    BASE_SOURCES,
    campaign_profiles,
    read_reference,
    repair_models,
    run_profile,
    source_hashes,
    update_scenario,
    write_match_receipt,
    write_reference,
)

pytestmark = pytest.mark.slow_solver


def capture_or_compare(name, payload):
    if source_hashes() == BASE_SOURCES:
        write_reference(name, payload)
    else:
        reference = read_reference(name)
        assert canonical_json_value(payload) == reference
        write_match_receipt(name, payload, reference)


@pytest.mark.parametrize("profile", tuple(campaign_profiles()))
def test_construction_campaign_matches_frozen_base(profile):
    capture_or_compare(profile, run_profile(profile))


def test_construction_campaign_period_models_match_frozen_base(monkeypatch):
    models = repair_models(monkeypatch)
    if source_hashes() == BASE_SOURCES:
        write_reference("period-models", models)
    capture_or_compare("period-models-S2", models)


@pytest.mark.parametrize("event", ("A", "B"))
def test_construction_campaign_update_inputs_match_frozen_base(event):
    snapshot, _periods, _active, history, teacher = update_scenario(event)
    capture_or_compare(
        f"update-input-{event}",
        {
            "snapshot": snapshot_to_dict(snapshot),
            "history": history,
            "teacher": teacher,
        },
    )


@pytest.mark.parametrize("event", ("A", "B"))
@pytest.mark.parametrize("level", range(5))
def test_construction_updates_match_frozen_base(event, level):
    from tests._support.construction_snapshot import run_update_level, update_pair_record

    capture_or_compare(f"update-pair-{event}", update_pair_record(event))
    capture_or_compare(f"update-result-{event}-{level}", run_update_level(event, level))


def test_construction_campaign_update_harness_reuses_constructions(monkeypatch):
    from dataclasses import replace

    from app.scheduler.domain.candidate import SchedulingStrategy
    from app.scheduler.domain.priorities import DEFAULT_LEVELS, PriorityWeights
    from tests._support import construction_snapshot
    from tests.unit.test_scheduler_construction_characterization_v1 import (
        BASE_TYPED_CANDIDATE,
        base_inputs,
    )

    original, periods = base_inputs()
    active = BASE_TYPED_CANDIDATE
    snapshot = replace(
        original,
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        baseline_lessons=active.lessons,
        priority_weights=PriorityWeights(DEFAULT_LEVELS),
        reserved_lesson_ids=frozenset(row.lesson_id for row in active.lessons),
    )
    teacher = snapshot.assignments[0].teacher_id
    monkeypatch.setattr(
        construction_snapshot,
        "update_scenario",
        lambda _event: (snapshot, periods, active, {}, teacher),
    )
    monkeypatch.setattr(
        construction_snapshot,
        "read_reference",
        lambda _name: {
            "snapshot": canonical_json_value(snapshot_to_dict(snapshot)),
            "history": {},
            "teacher": teacher,
        },
    )
    calls = []
    search = construction_snapshot.search_module
    local_construct = search.construct_recovery
    rebuilt_construct = search.construct_schedule

    def local(*args, **kwargs):
        calls.append("local")
        return local_construct(*args, **kwargs)

    def rebuilt(*args, **kwargs):
        calls.append("rebuilt")
        return rebuilt_construct(*args, **kwargs)

    monkeypatch.setattr(search, "construct_recovery", local)
    monkeypatch.setattr(search, "construct_schedule", rebuilt)
    construction_snapshot.update_pair.cache_clear()
    try:
        records = [construction_snapshot.run_update_level("A", level) for level in range(5)]
        assert calls == ["local", "rebuilt"]
        assert [record["level"] for record in records] == list(range(5))
        assert all(record["status"] == "COMPLETE" for record in records)
        assert all(record["priorities_followed"] is True for record in records)
        assert all(len(record["costs"]) == 2 for record in records)
    finally:
        construction_snapshot.update_pair.cache_clear()


def test_construction_campaign_source_hash_ignores_checkout_line_endings(tmp_path, monkeypatch):
    from tests._support import construction_snapshot

    monkeypatch.setattr(construction_snapshot, "ROOT", tmp_path)
    sources = tmp_path / "backend" / "app" / "scheduler"
    for name in construction_snapshot.BASE_SOURCES:
        path = sources / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"quantity = 1\n")
    normal = construction_snapshot.source_hashes()
    for name in construction_snapshot.BASE_SOURCES:
        (sources / name).write_bytes(b"quantity = 1\r\n")
    assert construction_snapshot.source_hashes() == normal
