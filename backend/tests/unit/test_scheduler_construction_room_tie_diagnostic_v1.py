"""Diagnose why the weighted base construction chooses room 501.

This is a temporary investigation test. It records the period-repair inputs, the
CP-SAT objective, hints and optimal values without changing production code.
"""

from importlib.metadata import version

from app.scheduler.domain.priorities import DEFAULT_LEVELS, PriorityWeights
from app.scheduler.infrastructure import constructive
from app.scheduler.infrastructure.constructive import construct_schedule
from tests.unit.test_scheduler_construction_characterization_v1 import base_inputs


def _rooms(candidate) -> list[tuple[int, int]]:
    assert candidate is not None
    return [(lesson.lesson_id, lesson.room_id) for lesson in candidate.lessons]


def _objective_terms(proto) -> list[tuple[str, int]]:
    names = [variable.name for variable in proto.variables]
    return [
        (names[index], coefficient)
        for index, coefficient in zip(proto.objective.vars, proto.objective.coeffs, strict=True)
    ]


def _hints(proto) -> dict[str, int]:
    names = [variable.name for variable in proto.variables]
    return {
        names[index]: value
        for index, value in zip(proto.solution_hint.vars, proto.solution_hint.values, strict=True)
    }


def test_diagnose_s1_room_tie(monkeypatch):
    records = []
    current = [None]
    original_select = constructive._select_period
    original_solver = constructive.cp_model.CpSolver

    def recording_select_period(options, *, deadline, scores=None, fill_admitted=False):
        record = {
            "options": [(row.assignment_id, tuple(available)) for row, available in options],
            "scores": None if scores is None else dict(scores),
            "fill_admitted": fill_admitted,
            "proto": None,
            "status": None,
            "status_name": None,
            "objective": None,
            "bound": None,
            "selected": None,
        }
        records.append(record)
        previous = current[0]
        current[0] = record
        try:
            selected = original_select(
                options,
                deadline=deadline,
                scores=scores,
                fill_admitted=fill_admitted,
            )
        finally:
            current[0] = previous
        record["selected"] = [(row.assignment_id, room) for row, room in selected]
        return selected

    class RecordingSolver(original_solver):
        def Solve(self, model):
            record = current[0]
            assert record is not None
            record["proto"] = model.Proto()
            status = super().Solve(model)
            record["status"] = status
            record["status_name"] = self.StatusName(status)
            record["objective"] = self.ObjectiveValue()
            record["bound"] = self.BestObjectiveBound()
            return status

    monkeypatch.setattr(constructive, "_select_period", recording_select_period)
    monkeypatch.setattr(constructive.cp_model, "CpSolver", RecordingSolver)

    snapshot, periods = base_inputs()
    unweighted = construct_schedule(snapshot, periods, weights=None, deadline=None)
    unweighted_records = list(records)

    records.clear()
    current[0] = None
    snapshot, periods = base_inputs()
    weighted = construct_schedule(
        snapshot,
        periods,
        weights=PriorityWeights(DEFAULT_LEVELS),
        deadline=None,
    )
    weighted_records = list(records)
    scored = [record for record in weighted_records if record["scores"] is not None]

    print(f"ortools_version={version('ortools')}")
    for index, record in enumerate(unweighted_records):
        print(
            f"unweighted[{index}] options={record['options']} "
            f"scores={record['scores']} fill_admitted={record['fill_admitted']} "
            f"solver_called={record['proto'] is not None} selected={record['selected']}"
        )
    print(f"unweighted_candidate_rooms={_rooms(unweighted)}")
    for index, record in enumerate(weighted_records):
        print(
            f"weighted[{index}] options={record['options']} scores={record['scores']} "
            f"fill_admitted={record['fill_admitted']} solver_called={record['proto'] is not None} "
            f"selected={record['selected']}"
        )
        if record["proto"] is not None:
            print(f"weighted[{index}] objective_terms={_objective_terms(record['proto'])}")
            print(f"weighted[{index}] hints={_hints(record['proto'])}")
            print(
                f"weighted[{index}] status={record['status_name']} "
                f"objective={record['objective']} bound={record['bound']}"
            )
    print(f"weighted_candidate_rooms={_rooms(weighted)}")
    print(f"weighted_scored_calls={len(scored)}")

    assert version("ortools") == "9.15.6755"
    assert _rooms(unweighted) == [(1_000_001, 500), (1_000_002, 500)]
    assert _rooms(weighted) == [(1_000_001, 501), (1_000_002, 501)]
    assert all(record["proto"] is None for record in unweighted_records)
    assert len(scored) == 2

    for record in scored:
        assert record["proto"] is not None
        assert record["scores"][(1, 500)] == record["scores"][(1, 501)]
        coefficients = dict(_objective_terms(record["proto"]))
        assert coefficients["choice_1_500"] == coefficients["choice_1_501"]
        hints = _hints(record["proto"])
        assert hints["choice_1_500"] == 1
        assert hints["choice_1_501"] == 0
        assert record["status"] == constructive.cp_model.OPTIMAL
        assert record["objective"] == record["bound"]
        assert record["selected"] == [(1, 501)]
