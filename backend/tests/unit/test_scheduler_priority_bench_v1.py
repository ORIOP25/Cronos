"""Priority benchmark runner emits one complete, measured row per repetition."""

import csv
import hashlib
import json
from pathlib import Path

from app.scheduler.domain.priorities import CRITERION_KEYS
from app.scheduler.lab.priority_bench import _profiles, _scenario, export_input, run_benchmark


def test_priority_bench_three_class_one_profile_writes_three_complete_metric_rows(tmp_path):
    output = tmp_path / "priority-bench.json"

    rows = run_benchmark(
        scenarios=("scale-3",),
        profiles=("recommended",),
        repetitions=3,
        output_path=output,
    )

    assert len(rows) == 3
    assert all(row["outcome"] == "COMPLETE" for row in rows)
    assert all(set(row["metrics"]) == set(CRITERION_KEYS) for row in rows)
    assert all(row["runtime_seconds"] >= 0 for row in rows)
    assert all(row["peak_memory_bytes"] > 0 for row in rows)
    assert json.loads(output.read_text(encoding="utf-8")) == rows

    fixture = _scenario("scale-3")
    input_path = tmp_path / "snapshot.json"
    export_input(fixture.snapshot, fixture.periods, input_path)
    imported = run_benchmark(input_path=input_path, repetitions=1)
    assert imported[0]["outcome"] == "COMPLETE"


def test_all_important_profile_sets_every_priority_level_to_two():
    assert _profiles()["all-important"].to_dict() == dict.fromkeys(CRITERION_KEYS, 2)


def test_pilot_csv_is_balanced_without_changing_room_identity_or_capacity():
    pilot_dir = (
        Path(__file__).resolve().parents[3]
        / "documentation"
        / "07_data_and_seed"
        / "sample_import_48_classes"
    )
    with (pilot_dir / "Cronos_Salas_Template.csv").open(encoding="utf-8-sig", newline="") as source:
        source_rooms = list(csv.DictReader(source, delimiter=";"))
    source_types = [row["Tipo de sala"] for row in source_rooms]
    room_identity = "\n".join(f"{row['Nome da sala']}|{row['Capacidade']}" for row in source_rooms)

    assert len(source_rooms) == 48
    assert hashlib.sha256(room_identity.encode()).hexdigest() == (
        "47e0d47324992fbf8ab7ae28c7de34742515e2f95bde291cc7d22d821887fcc5"
    )
    assert {room_type: source_types.count(room_type) for room_type in set(source_types)} == {
        "Normal": 37,
        "Laboratório": 7,
        "Artes": 3,
        "Ginásio": 1,
    }

    case = _scenario("pilot-48")
    labels = case.labels

    assert len(labels["rooms"]) == 48
    assert len(case.snapshot.assignments) == 336
    assert {
        labels["rooms"][room_id]: room_type for room_id, room_type in labels["room_types"].items()
    } == {row["Nome da sala"]: row["Tipo de sala"] for row in source_rooms}
    gym_id = next(room_id for room_id, name in labels["rooms"].items() if name == "G-02")
    assert labels["room_types"][gym_id] == "Ginásio"
    assert all(assignment.eligible_room_ids for assignment in case.snapshot.assignments)
    assert sum(room_type == "Normal" for room_type in labels["room_types"].values()) == 37
    assert sum(room_type == "Laboratório" for room_type in labels["room_types"].values()) == 7
    assert sum(room_type == "Artes" for room_type in labels["room_types"].values()) == 3
    assert sum(room_type == "Ginásio" for room_type in labels["room_types"].values()) == 1
    assert len(labels["room_capacities"]) == 48
