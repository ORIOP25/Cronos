import copy
import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "schedule_check", Path(__file__).with_name("validate-e2e-schedule.py")
)
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


class IndependentScheduleTests(unittest.TestCase):
    def setUp(self):
        self.originals = {
            "rooms": {"Sala A": {"type": "Teórica", "capacity": 25}},
            "classes": [{"course": "C", "class": "A", "size": 20}],
            "teachers": {"teacher@example.com": {"subjects": ["Subject"]}},
            "subjects": {
                "Subject": {
                    "room_type": "Teórica",
                    "modules": [
                        {"code": "M1", "order": 1, "minutes": 30},
                        {"code": "M2", "order": 2, "minutes": 60},
                    ],
                }
            },
            "demand": [
                {
                    "course": "C",
                    "class": "A",
                    "subject": "Subject",
                    "teacher": "teacher@example.com",
                    "minutes": 90,
                }
            ],
        }
        self.snapshot = {
            "school": {
                "start_date": "2026-10-07",
                "hard_end_date": "2026-10-09",
                "teaching_dates": ["2026-10-07"],
                "grid": {"2026-10-07": [["09:00", "09:50"], ["09:50", "10:40"]]},
                "lunch": {"start": "12:00", "end": "13:00", "minimum_minutes": 30},
                "unavailable": [],
            },
            "executed": [
                {"assignment": ["C", "A", "Subject"], "module": "M1", "minutes": 10}
            ],
            "lessons": [
                {
                    "id": "one",
                    "assignment": ["C", "A", "Subject"],
                    "teacher": "teacher@example.com",
                    "room": "Sala A",
                    "date": "2026-10-07",
                    "start": "09:00",
                    "end": "09:50",
                    "credit_minutes": 50,
                    "slices": [
                        {"module": "M1", "offset": 10, "minutes": 20},
                        {"module": "M2", "offset": 0, "minutes": 30},
                    ],
                },
                {
                    "id": "two",
                    "assignment": ["C", "A", "Subject"],
                    "teacher": "teacher@example.com",
                    "room": "Sala A",
                    "date": "2026-10-07",
                    "start": "09:50",
                    "end": "10:40",
                    "credit_minutes": 30,
                    "slices": [{"module": "M2", "offset": 30, "minutes": 30}],
                },
            ],
        }

    def test_adjacent_lessons_exact_residual_minutes_and_final_partial_credit(self):
        report = checker.validate(self.originals, self.snapshot)
        self.assertEqual(report["planned_minutes"], 80)
        self.assertEqual(report["executed_minutes"], 10)
        self.assertEqual(report["required_minutes"], 90)

    def test_missing_excess_misordered_and_wrongly_offset_credit_is_refused(self):
        mutations = [
            lambda s: s["lessons"].pop(),
            lambda s: s["lessons"][1].update(credit_minutes=31),
            lambda s: s["lessons"][0]["slices"][0].update(module="M2"),
            lambda s: s["lessons"][1]["slices"][0].update(offset=29),
            lambda s: s["lessons"][1].update(id="one"),
            lambda s: s["lessons"][1].update(credit_minutes=True),
            lambda s: s["lessons"][0]["slices"][1].update(offset=False),
            lambda s: s["executed"][0].update(minutes=31),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                snapshot = copy.deepcopy(self.snapshot)
                mutate(snapshot)
                with self.assertRaises(ValueError):
                    checker.validate(self.originals, snapshot)

    def test_calendar_grid_room_teacher_and_resource_collisions_are_refused(self):
        mutations = [
            lambda s: s["lessons"][0].update(date="2026-10-08"),
            lambda s: s["lessons"][0].update(end="09:45"),
            lambda s: s["lessons"][0].update(room="Unknown"),
            lambda s: s["lessons"][0].update(teacher="other@example.com"),
            lambda s: s["school"].update(hard_end_date="2026-10-06"),
            lambda s: s["school"]["unavailable"].append(
                {
                    "kind": "teacher",
                    "resource": "teacher@example.com",
                    "date": "2026-10-07",
                    "start": "09:30",
                    "end": "10:00",
                }
            ),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                snapshot = copy.deepcopy(self.snapshot)
                mutate(snapshot)
                with self.assertRaises(ValueError):
                    checker.validate(self.originals, snapshot)
        originals = copy.deepcopy(self.originals)
        originals["rooms"]["Sala A"]["capacity"] = 19
        with self.assertRaisesRegex(ValueError, "Room"):
            checker.validate(originals, self.snapshot)
        originals["rooms"]["Sala A"].update(capacity=25, type="Laboratório")
        with self.assertRaisesRegex(ValueError, "Room"):
            checker.validate(originals, self.snapshot)
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["lessons"][1].update(start="09:40", end="10:30")
        snapshot["school"]["grid"]["2026-10-07"].append(["09:40", "10:30"])
        with self.assertRaisesRegex(ValueError, "Resource overlap"):
            checker.validate(self.originals, snapshot)

    def test_lunch_requires_one_continuous_gap_and_not_the_sum_of_fragments(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["school"]["grid"]["2026-10-07"] = [
            ["12:00", "12:50"],
            ["13:10", "14:00"],
        ]
        snapshot["school"]["lunch"].update(start="11:40", end="14:20")
        snapshot["lessons"][0].update(start="12:00", end="12:50")
        snapshot["lessons"][1].update(start="13:10", end="14:00")
        with self.assertRaisesRegex(ValueError, "continuous lunch"):
            checker.validate(self.originals, snapshot)
        snapshot["school"]["lunch"]["minimum_minutes"] = 20
        self.assertEqual(
            checker.validate(self.originals, snapshot)["planned_minutes"], 80
        )


if __name__ == "__main__":
    unittest.main()
