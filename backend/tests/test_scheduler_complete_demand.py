from app.services.scheduler_complete_demand import CompleteDemandLedgerBuilder


def _snapshot() -> dict:
    return {
        "classes": [{"id": 1, "size": 24, "grade_level": 10}],
        "subjects": [{"id": 2, "required_room_type": "normal"}],
        "teachers": [{"id": 3}],
        "teacher_subject_eligibility": [{"teacher_id": 3, "subject_id": 2}],
        "class_subject_requirements": [
            {"class_id": 1, "subject_id": 2, "grade_level": 10, "teacher_id": 3}
        ],
        "rooms": [
            {"id": 4, "capacity": 30, "type": "normal"},
            {"id": 5, "capacity": 20, "type": "normal"},
            {"id": 6, "capacity": 30, "type": "laboratory"},
        ],
        "module_accounting": [
            {"id": 8, "subject_id": 2, "hours_total": 40, "sequence": 2},
            {"id": 7, "subject_id": 2, "hours_total": 50, "sequence": 1},
        ],
    }


def test_complete_demand_ledger_preserves_module_sequence_and_full_hours():
    ledger = CompleteDemandLedgerBuilder().build(_snapshot())

    assert ledger.is_complete is True
    assert ledger.blockers == ()
    assert ledger.required_minutes == 90 * 60
    assert len(ledger.items) == 1
    item = ledger.items[0]
    assert item.eligible_room_ids == (4,)
    assert [module.module_id for module in item.modules] == [7, 8]
    assert [module.sequence for module in item.modules] == [1, 2]


def test_complete_demand_cannot_pass_with_missing_required_modules():
    snapshot = _snapshot()
    snapshot["module_accounting"] = []

    ledger = CompleteDemandLedgerBuilder().build(snapshot)

    assert ledger.is_complete is False
    assert ledger.items == ()
    assert any("No required module demand" in blocker for blocker in ledger.blockers)


def test_complete_demand_reports_teacher_and_room_ineligibility():
    snapshot = _snapshot()
    snapshot["teacher_subject_eligibility"] = [
        {"teacher_id": 3, "subject_id": 99}
    ]
    snapshot["rooms"] = [{"id": 4, "capacity": 10, "type": "normal"}]

    ledger = CompleteDemandLedgerBuilder().build(snapshot)

    assert ledger.is_complete is False
    assert any("not eligible" in blocker for blocker in ledger.blockers)
    assert any("No eligible room" in blocker for blocker in ledger.blockers)
