from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class SchedulerGoldenFixture:
    name: str
    snapshot: dict
    debt_basis: dict


def small_scheduler_fixture() -> SchedulerGoldenFixture:
    return _build_fixture(
        name="small",
        class_count=3,
        subject_count=4,
        subjects_per_class=3,
        teacher_count=6,
        normal_rooms=3,
        lab_rooms=1,
    )


def medium_scheduler_fixture() -> SchedulerGoldenFixture:
    return _build_fixture(
        name="medium",
        class_count=12,
        subject_count=6,
        subjects_per_class=4,
        teacher_count=20,
        normal_rooms=6,
        lab_rooms=2,
    )


def large_scheduler_fixture() -> SchedulerGoldenFixture:
    return _build_fixture(
        name="large",
        class_count=30,
        subject_count=6,
        subjects_per_class=4,
        teacher_count=45,
        normal_rooms=8,
        lab_rooms=4,
    )


def _build_fixture(
    *,
    name: str,
    class_count: int,
    subject_count: int,
    subjects_per_class: int,
    teacher_count: int,
    normal_rooms: int,
    lab_rooms: int,
) -> SchedulerGoldenFixture:
    start = date(2025, 9, 1)
    hard_end = date(2026, 7, 15)
    classes = [
        {"id": class_id, "size": 24 + class_id % 5, "grade_level": 10}
        for class_id in range(1, class_count + 1)
    ]
    subjects = [
        {
            "id": subject_id,
            "required_room_type": "lab" if subject_id % 3 == 0 else "normal",
        }
        for subject_id in range(1, subject_count + 1)
    ]
    teachers = [{"id": teacher_id} for teacher_id in range(1, teacher_count + 1)]
    requirements = []
    eligibility = []
    for class_id in range(1, class_count + 1):
        for offset in range(subjects_per_class):
            subject_id = (class_id + offset - 1) % subject_count + 1
            teacher_id = ((class_id - 1) * subjects_per_class + offset) % teacher_count + 1
            requirements.append(
                {
                    "class_id": class_id,
                    "subject_id": subject_id,
                    "grade_level": 10,
                    "teacher_id": teacher_id,
                }
            )
            eligibility.append({"teacher_id": teacher_id, "subject_id": subject_id})
    modules = [
        {
            "id": subject_id * 10 + sequence,
            "subject_id": subject_id,
            "hours_total": 2,
            "sequence": sequence,
        }
        for subject_id in range(1, subject_count + 1)
        for sequence in (1, 2)
    ]
    slots = []
    slot_id = 1
    for weekday in range(5):
        for hour in (8, 9, 10, 11, 13, 14, 15, 16):
            slots.append(
                {
                    "id": slot_id,
                    "day_of_week": weekday,
                    "start_time": f"{hour:02d}:00:00",
                    "end_time": f"{hour + 1:02d}:00:00",
                }
            )
            slot_id += 1
    rooms = [
        {"id": room_id, "capacity": 35, "type": "normal"}
        for room_id in range(1, normal_rooms + 1)
    ] + [
        {"id": normal_rooms + room_id, "capacity": 35, "type": "lab"}
        for room_id in range(1, lab_rooms + 1)
    ]
    blocked_day = start + timedelta(days=30)
    snapshot = {
        "organization_id": 1,
        "school_year_id": 1,
        "strategy": "COMPLETE_GENERATION",
        "timezone": "Europe/Lisbon",
        "start_date": start.isoformat(),
        "hard_end_date": hard_end.isoformat(),
        "scheduler_state_version": 8,
        "approved_scheduler_state_version": 7,
        "timetable_grid": slots,
        "calendar_events": [
            {
                "id": 1,
                "start_date": blocked_day.isoformat(),
                "end_date": blocked_day.isoformat(),
                "event_type": "blocked",
                "source": "golden_fixture",
            }
        ],
        "constraints": [],
        "lunch_rules": {
            "window_start": "12:00:00",
            "window_end": "13:30:00",
            "minimum_minutes": 30,
        },
        "classes": classes,
        "subjects": subjects,
        "teachers": teachers,
        "teacher_subject_eligibility": list(
            {tuple(sorted(row.items())): row for row in eligibility}.values()
        ),
        "class_subject_requirements": requirements,
        "teacher_availability": [
            {"teacher_id": 1, "timeslot_id": 1, "score": -1},
            {"teacher_id": 2, "timeslot_id": 2, "score": 0},
        ],
        "rooms": rooms,
        "module_accounting": modules,
        "active_schedule": [
            {
                "id": 1,
                "schedule_version_id": "golden-v1",
                "stable_block_key": "golden-active-1",
                "class_id": 1,
                "subject_id": requirements[0]["subject_id"],
                "teacher_id": requirements[0]["teacher_id"],
                "room_id": 1,
                "date": (start + timedelta(days=7)).isoformat(),
                "timeslot_id": 1,
                "duration_minutes": 60,
                "is_recovery_block": False,
                "recovery_source_occurrence_id": None,
                "recovery_source_occurrence_revision": None,
                "lesson_log_status": None,
            }
        ],
    }
    debt_basis = {
        "organization_id": 1,
        "school_year_id": 1,
        "items": [
            {
                "occurrence_id": 1,
                "occurrence_revision": 1,
                "class_id": 1,
                "subject_id": requirements[0]["subject_id"],
                "teacher_id": requirements[0]["teacher_id"],
                "unresolved_debt_minutes": 120,
            }
        ],
    }
    return SchedulerGoldenFixture(name=name, snapshot=snapshot, debt_basis=debt_basis)
