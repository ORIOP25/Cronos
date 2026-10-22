"""Repeatable priority measurements over scheduler lab scenarios."""

from __future__ import annotations

import argparse
import csv
import json
import resource
from dataclasses import dataclass, replace
from datetime import date, time
from pathlib import Path
from time import perf_counter
from typing import Any

from app.scheduler.domain.calendar import Period, normalize_period
from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    PlanningSnapshot,
)
from app.scheduler.domain.priorities import CRITERION_KEYS, DEFAULT_LEVELS, PriorityWeights
from app.scheduler.domain.priority_metrics import measure_priority_metrics
from app.scheduler.domain.projection import ModuleRequirement
from app.scheduler.domain.recovery import measure_disruption
from app.scheduler.domain.serialization import snapshot_from_dict, snapshot_to_dict
from app.scheduler.infrastructure.search import search_adaptive_schedule, search_complete_schedule
from app.scheduler.lab.realistic_pilot import build_realistic_pilot
from app.scheduler.lab.recovery import CANCEL_LESSON, apply_event, laboratory_policy
from app.scheduler.lab.scale import build_scale_fixture
from app.scheduler.lab.typology import (
    build_availability_typology_fixture,
    build_joint_typology_fixture,
    build_typology_fixture,
)

ROOT = Path(__file__).resolve().parents[4]
PILOT_DIR = ROOT / "documentation" / "07_data_and_seed" / "sample_import_48_classes"


@dataclass(frozen=True)
class _Scenario:
    name: str
    snapshot: PlanningSnapshot
    periods: tuple[Period, ...]
    baseline: CandidateSchedule | None = None
    labels: dict[str, dict[str, str]] | None = None


def _profiles() -> dict[str, PriorityWeights]:
    important = dict.fromkeys(CRITERION_KEYS, 2)
    class_gaps = dict(DEFAULT_LEVELS)
    class_gaps.update(class_gaps=4, finish_early=1)
    teacher_avoid = dict(DEFAULT_LEVELS)
    teacher_avoid["teacher_preferences"] = 4
    weekly = dict(DEFAULT_LEVELS)
    weekly["weekly_stability"] = 4
    same_room = dict(DEFAULT_LEVELS)
    same_room["class_same_room"] = 4
    return {
        "recommended": PriorityWeights(DEFAULT_LEVELS),
        "all-important": PriorityWeights(important),
        "class-gaps-maximum": PriorityWeights(class_gaps),
        "teacher-avoid-maximum": PriorityWeights(teacher_avoid),
        "weekly-stability-maximum": PriorityWeights(weekly),
        "same-room-maximum": PriorityWeights(same_room),
    }


def _pilot_rows(path: Path, filename: str) -> list[dict[str, str]]:
    with (path / filename).open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source, delimiter=";"))


def _pilot_scenario(directory: Path) -> _Scenario:
    rooms = _pilot_rows(directory, "Cronos_Salas_Template.csv")
    classes = _pilot_rows(directory, "Cronos_CursosETurmas_Template.csv")
    subject_modules = _pilot_rows(directory, "Cronos_DisciplinasEModulos_Template.csv")
    teachers = _pilot_rows(directory, "Cronos_ProfessoresECompetencias_Template.csv")
    assignments = _pilot_rows(directory, "Cronos_Atribuicoes_Template.csv")

    room_ids = {row["Nome da sala"]: index for index, row in enumerate(rooms, start=1)}
    room_types = {row["Nome da sala"]: row["Tipo de sala"] for row in rooms}
    room_capacity = {row["Nome da sala"]: int(row["Capacidade"]) for row in rooms}
    classes_by_name = {row["Nome da turma"]: row for row in classes}
    class_ids = {name: index for index, name in enumerate(classes_by_name, start=1)}
    teacher_names = {row["Email do professor"]: row["Nome do professor"] for row in teachers}
    teacher_ids = {email: index for index, email in enumerate(teacher_names, start=1)}
    modules_by_subject: dict[str, list[dict[str, str]]] = {}
    room_type_by_subject = {}
    for row in subject_modules:
        modules_by_subject.setdefault(row["Nome da disciplina"], []).append(row)
        room_type_by_subject[row["Nome da disciplina"]] = row["Tipo de sala"]
    subject_ids = {name: index for index, name in enumerate(sorted(modules_by_subject), start=1)}

    period_fixture = build_typology_fixture(48, build_witness=False)
    units = []
    for index, row in enumerate(assignments, start=1):
        class_name = row["Nome da turma"]
        subject_name = row["Nome da disciplina"]
        required_type = room_type_by_subject[subject_name]
        enrollment = int(classes_by_name[class_name]["Número de alunos"])
        eligible = frozenset(
            room_ids[name]
            for name, current_type in room_types.items()
            if current_type == required_type and room_capacity[name] >= enrollment
        )
        if not eligible:
            raise ValueError(
                f"No rebalanced {required_type} room can fit {class_name} ({enrollment} students)."
            )
        modules = tuple(
            ModuleRequirement(
                module_id=module_index,
                sequence=int(module["Ordem do módulo"]),
                required_minutes=int(float(module["Horas do módulo"]) * 60),
            )
            for module_index, module in enumerate(
                sorted(
                    modules_by_subject[subject_name],
                    key=lambda value: int(value["Ordem do módulo"]),
                ),
                start=1,
            )
        )
        units.append(
            Assignment(
                assignment_id=index,
                class_ids=(class_ids[class_name],),
                subject_id=subject_ids[subject_name],
                teacher_id=teacher_ids[row["Email do professor"]],
                eligible_room_ids=eligible,
                modules=modules,
                needs_special_room=required_type != "Normal",
            )
        )
    labels = {
        "classes": {str(value): name for name, value in class_ids.items()},
        "subjects": {str(value): name for name, value in subject_ids.items()},
        "teachers": {str(teacher_ids[email]): name for email, name in teacher_names.items()},
        "rooms": {str(value): name for name, value in room_ids.items()},
        "room_types": {str(room_ids[name]): room_type for name, room_type in room_types.items()},
        "room_capacities": {
            str(room_ids[name]): str(capacity) for name, capacity in room_capacity.items()
        },
    }
    return _Scenario(
        "pilot-48",
        replace(period_fixture.snapshot, assignments=tuple(units)),
        period_fixture.periods,
        labels=labels,
    )


def _scenario(name: str, pilot_directory: Path | None = None) -> _Scenario:
    if name.startswith("scale-"):
        fixture = build_scale_fixture(int(name.removeprefix("scale-")), seed=1)
        return _Scenario(name, fixture.snapshot, fixture.periods)
    if name.startswith("typology-"):
        fixture = build_typology_fixture(int(name.removeprefix("typology-")), build_witness=False)
        return _Scenario(name, fixture.snapshot, fixture.periods)
    if name.startswith("availability-"):
        fixture = build_availability_typology_fixture(int(name.removeprefix("availability-")))
        return _Scenario(name, fixture.snapshot, fixture.periods)
    if name.startswith("joint-"):
        fixture = build_joint_typology_fixture(int(name.removeprefix("joint-")))
        return _Scenario(name, fixture.snapshot, fixture.periods)
    if name == "recovery-3":
        fixture = build_typology_fixture(3)
        baseline = fixture.witness
        snapshot = apply_event(fixture.snapshot, baseline, CANCEL_LESSON, 0)
        return _Scenario(name, snapshot, fixture.periods, baseline)
    if name == "pilot-48":
        return _pilot_scenario(pilot_directory or PILOT_DIR)
    if name == "pilot-real":
        school = build_realistic_pilot()
        return _Scenario(name, school.snapshot, school.periods, labels=school.labels)
    raise ValueError(f"Unknown priority benchmark scenario: {name}")


def _from_input(path: Path) -> _Scenario:
    bundle = json.loads(path.read_text(encoding="utf-8"))
    snapshot = snapshot_from_dict(bundle["snapshot"])
    periods = tuple(
        normalize_period(
            date.fromisoformat(row["school_date"]),
            time.fromisoformat(row["start_local"]),
            time.fromisoformat(row["end_local"]),
            snapshot.timezone_name,
        )
        for row in bundle["periods"]
    )
    return _Scenario(bundle.get("scenario", path.stem), snapshot, periods)


def export_input(snapshot: PlanningSnapshot, periods: tuple[Period, ...], path: Path) -> None:
    """Write a portable JSON input bundle for a later local benchmark run."""
    bundle = {
        "snapshot": snapshot_to_dict(snapshot),
        "periods": [
            {
                "school_date": row.school_date.isoformat(),
                "start_local": row.start_local.isoformat(),
                "end_local": row.end_local.isoformat(),
            }
            for row in periods
        ],
    }
    path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")


def run_benchmark(
    *,
    scenarios: tuple[str, ...] = ("scale-3",),
    profiles: tuple[str, ...] = ("recommended",),
    repetitions: int = 3,
    time_limit_seconds: float = 900,
    output_path: Path | None = None,
    input_path: Path | None = None,
    pilot_directory: Path | None = None,
) -> list[dict[str, Any]]:
    """Run deterministic scenario/profile pairs and record time, memory and metrics."""
    if type(repetitions) is not int or repetitions < 1:
        raise ValueError("Repetitions must be a positive integer.")
    profiles_by_name = _profiles()
    unknown_profiles = set(profiles) - set(profiles_by_name)
    if unknown_profiles:
        raise ValueError(f"Unknown priority benchmark profiles: {sorted(unknown_profiles)}")
    cases = (
        [_from_input(input_path)]
        if input_path is not None
        else [_scenario(name, pilot_directory) for name in scenarios]
    )
    rows = []
    for case in cases:
        for profile_name in profiles:
            weights = profiles_by_name[profile_name]
            snapshot = replace(case.snapshot, priority_weights=weights)
            for repetition in range(1, repetitions + 1):
                started = perf_counter()
                if case.baseline is None:
                    outcome = search_complete_schedule(
                        snapshot,
                        case.periods,
                        time_limit_seconds=time_limit_seconds,
                        random_seed=repetition,
                        stop_at_first_complete=True,
                    )
                else:
                    outcome = search_adaptive_schedule(
                        snapshot,
                        case.periods,
                        case.baseline,
                        laboratory_policy(snapshot),
                        time_limit_seconds=time_limit_seconds,
                        random_seed=repetition,
                        stop_at_first_complete=True,
                    )
                runtime = perf_counter() - started
                # Process peak RSS (Linux reports KiB). tracemalloc made pilot-sized
                # runs several times slower, so it distorted the timings it sat next to.
                peak_memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
                metrics = None
                lessons = []
                if outcome.candidate is not None:
                    changed_lessons = 0
                    if case.baseline is not None:
                        changed_lessons = len(
                            measure_disruption(
                                snapshot,
                                case.baseline,
                                outcome.candidate,
                                laboratory_policy(snapshot),
                            ).changes
                        )
                    metrics = measure_priority_metrics(
                        snapshot, outcome.candidate, changed_lessons=changed_lessons
                    )
                    metrics["finish_early"] = metrics["finish_early"].isoformat()
                    assignments_by_id = {row.assignment_id: row for row in snapshot.assignments}
                    lessons = [
                        {
                            "assignment_id": lesson.assignment_id,
                            "class_ids": list(assignments_by_id[lesson.assignment_id].class_ids),
                            "subject_id": assignments_by_id[lesson.assignment_id].subject_id,
                            "teacher_id": lesson.teacher_id
                            or assignments_by_id[lesson.assignment_id].teacher_id,
                            "room_id": lesson.room_id,
                            "school_date": lesson.period.school_date.isoformat(),
                            "start_local": lesson.period.start_local.isoformat(),
                            "end_local": lesson.period.end_local.isoformat(),
                            "credit_minutes": lesson.credit_minutes,
                        }
                        for lesson in outcome.candidate.lessons
                    ]
                rows.append(
                    {
                        "scenario": case.name,
                        "profile": profile_name,
                        "repetition": repetition,
                        "outcome": outcome.status,
                        "runtime_seconds": round(runtime, 6),
                        "peak_memory_bytes": peak_memory,
                        "metrics": metrics,
                        "lessons": lessons,
                        "labels": case.labels,
                    }
                )
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return rows


def _inside_repository(path: Path) -> Path:
    """Resolve a CLI path and refuse anything outside the repository (``/workspace``)."""
    root = ROOT.resolve()
    resolved = (path if path.is_absolute() else root / path).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"Lab paths must stay inside the repository ({root}): {path}")
    return resolved


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", action="append", default=[])
    parser.add_argument("--profile", action="append", default=[])
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--time-limit-seconds", type=float, default=900)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--pilot-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_benchmark(
        scenarios=tuple(args.scenario or ("scale-3",)),
        profiles=tuple(args.profile or ("recommended",)),
        repetitions=args.repetitions,
        time_limit_seconds=args.time_limit_seconds,
        output_path=_inside_repository(args.output) if args.output else None,
        input_path=_inside_repository(args.input) if args.input else None,
        pilot_directory=_inside_repository(args.pilot_dir) if args.pilot_dir else None,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
