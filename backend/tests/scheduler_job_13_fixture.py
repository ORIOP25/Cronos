"""Sanitized immutable workload captured from failed adaptive job 13."""

_ACTIVE_ROWS = (
    (167, "2026-09-14", 11, 16, 937, 0),
    (168, "2026-09-14", 11, 16, 938, 50),
    (169, "2026-09-14", 11, 16, 939, 100),
    (170, "2026-09-14", 11, 16, 940, 150),
    (171, "2026-09-14", 10, 15, 941, 0),
    (172, "2026-09-14", 10, 15, 943, 50),
    (173, "2026-09-14", 10, 15, 944, 100),
    (174, "2026-09-14", 10, 15, 945, 150),
    (175, "2026-09-15", 11, 16, 946, 200),
    (176, "2026-09-15", 11, 16, 947, 250),
    (177, "2026-09-15", 11, 16, 948, 300),
    (178, "2026-09-15", 11, 16, 949, 350),
    (179, "2026-09-15", 10, 15, 950, 200),
    (180, "2026-09-15", 10, 15, 952, 250),
    (181, "2026-09-15", 10, 15, 953, 300),
    (182, "2026-09-15", 10, 15, 954, 350),
    (183, "2026-09-16", 10, 15, 955, 400),
    (184, "2026-09-16", 10, 15, 956, 450),
    (185, "2026-09-16", 10, 15, 957, 500),
    (186, "2026-09-16", 10, 15, 958, 550),
    (187, "2026-09-16", 11, 16, 959, 400),
    (188, "2026-09-16", 11, 16, 961, 450),
    (189, "2026-09-16", 11, 16, 962, 500),
    (190, "2026-09-16", 11, 16, 963, 550),
    (191, "2026-09-17", 11, 16, 964, 600),
    (192, "2026-09-17", 11, 16, 965, 650),
    (193, "2026-09-17", 11, 16, 966, 700),
    (194, "2026-09-17", 11, 16, 967, 750),
    (195, "2026-09-17", 10, 15, 968, 600),
    (196, "2026-09-17", 10, 15, 970, 650),
    (197, "2026-09-17", 10, 15, 971, 700),
    (198, "2026-09-17", 10, 15, 972, 750),
    (199, "2026-09-18", 11, 16, 973, 800),
    (200, "2026-09-18", 11, 16, 974, 850),
    (201, "2026-09-18", 11, 16, 975, 900),
    (202, "2026-09-18", 11, 16, 976, 950),
    (203, "2026-09-18", 10, 15, 977, 800),
    (204, "2026-09-18", 10, 15, 979, 850),
    (205, "2026-09-18", 10, 15, 980, 900),
    (206, "2026-09-18", 10, 15, 981, 950),
    (207, "2026-09-21", 11, 16, 937, 1000),
    (208, "2026-09-21", 11, 16, 938, 1050),
    (209, "2026-09-21", 11, 16, 939, 1100),
    (210, "2026-09-21", 11, 16, 940, 1150),
    (211, "2026-09-21", 10, 15, 941, 1000),
    (212, "2026-09-21", 10, 15, 943, 1050),
    (213, "2026-09-21", 10, 15, 944, 1100),
    (214, "2026-09-21", 10, 15, 945, 1150),
    (215, "2026-09-22", 11, 16, 946, 1200),
    (216, "2026-09-22", 11, 16, 947, 1250),
    (217, "2026-09-22", 11, 16, 948, 1300),
    (218, "2026-09-22", 11, 16, 949, 1350),
    (219, "2026-09-22", 10, 15, 950, 1200),
    (220, "2026-09-22", 10, 15, 952, 1250),
    (221, "2026-09-22", 10, 15, 953, 1300),
    (222, "2026-09-22", 10, 15, 954, 1350),
    (223, "2026-09-23", 11, 16, 955, 1400),
    (224, "2026-09-23", 11, 16, 956, 1450),
    (225, "2026-09-23", 10, 15, 957, 1400),
    (226, "2026-09-23", 10, 15, 958, 1450),
)


def scheduler_job_13_snapshot() -> dict:
    starts = (510, 570, 630, 690, 750, 810, 870, 930, 990)
    grid = []
    for weekday in range(5):
        for offset, start in enumerate(starts):
            slot_id = 937 + weekday * 9 + offset
            grid.append(
                {
                    "id": slot_id,
                    "day_of_week": weekday,
                    "start_time": f"{start // 60:02d}:{start % 60:02d}:00",
                    "end_time": f"{(start + 50) // 60:02d}:{(start + 50) % 60:02d}:00",
                }
            )
    active = [
        {
            "id": block_id,
            "date": output_date,
            "room_id": 10,
            "class_id": 11,
            "subject_id": subject_id,
            "teacher_id": teacher_id,
            "timeslot_id": slot_id,
            "duration_minutes": 50,
            "module_sequence_index": 0,
            "stable_block_key": (f"C11-S{subject_id}-D{output_date}-T{slot_id}-R10-A{sequence}"),
            "is_recovery_block": False,
            "lesson_log_status": None,
            "schedule_version_id": "sanitized-source",
            "recovery_source_occurrence_id": None,
            "recovery_source_occurrence_revision": None,
        }
        for block_id, output_date, subject_id, teacher_id, slot_id, sequence in _ACTIVE_ROWS
    ]
    holidays = (
        "2026-10-05",
        "2026-11-01",
        "2026-12-01",
        "2026-12-08",
        "2026-12-25",
        "2027-01-01",
        "2027-03-26",
        "2027-03-28",
        "2027-04-25",
        "2027-05-01",
        "2027-05-27",
        "2027-06-10",
    )
    generation_input = {
        "organization_id": 1,
        "school_year_id": 1,
        "strategy": "ADAPTIVE_REPAIR",
        "timezone": "Europe/Lisbon",
        "start_date": "2026-09-14",
        "hard_end_date": "2027-07-30",
        "scheduler_state_version": 12,
        "approved_scheduler_state_version": 10,
        "quality_policy_version": "baseline-v1",
        "rooms": [
            {"id": 10, "type": "normal", "capacity": 30},
            {"id": 11, "type": "normal", "capacity": 30},
        ],
        "classes": [
            {
                "id": 11,
                "size": 25,
                "grade_level": 10,
                "course_id": 9,
                "start_year": 2026,
                "end_year": 2029,
            },
            {
                "id": 12,
                "size": 25,
                "grade_level": 11,
                "course_id": 9,
                "start_year": 2025,
                "end_year": 2028,
            },
        ],
        "subjects": [
            {"id": subject_id, "required_room_type": "normal"} for subject_id in (10, 11, 12)
        ],
        "teachers": [{"id": teacher_id} for teacher_id in (15, 16, 17)],
        "constraints": [],
        "lunch_rules": {
            "window_start": "12:30:00",
            "window_end": "14:30:00",
            "minimum_minutes": 60,
        },
        "class_progress": [],
        "timetable_grid": grid,
        "active_schedule": active,
        "calendar_events": [
            {
                "source": "auto",
                "event_type": "national_holiday",
                "start_date": holiday,
                "end_date": holiday,
            }
            for holiday in holidays
        ],
        "module_accounting": [
            {"id": 12, "sequence": 0, "subject_id": 10, "required_minutes": 1500},
            {"id": 13, "sequence": 0, "subject_id": 11, "required_minutes": 1500},
            {"id": 14, "sequence": 0, "subject_id": 12, "required_minutes": 1500},
        ],
        "teacher_availability": [
            {"score": 1, "teacher_id": teacher_id, "timeslot_id": slot["id"]}
            for teacher_id in (15, 16, 17)
            for slot in grid
        ],
        "class_subject_requirements": [
            {"class_id": 11, "subject_id": 10, "teacher_id": 15, "grade_level": 10},
            {"class_id": 11, "subject_id": 11, "teacher_id": 16, "grade_level": 10},
            {"class_id": 11, "subject_id": 12, "teacher_id": 17, "grade_level": 10},
        ],
        "teacher_subject_eligibility": [
            {"subject_id": 10, "teacher_id": 15},
            {"subject_id": 11, "teacher_id": 16},
            {"subject_id": 12, "teacher_id": 17},
        ],
    }
    return {
        "generation_input": generation_input,
        "debt_basis": None,
        "repair_policy": {
            "school_today": "2026-09-11",
            "school_timezone": "Europe/Lisbon",
            "editable_start_date": "2026-09-18",
            "repair_stability_window_days": 7,
        },
    }
