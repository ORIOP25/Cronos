"""Check materialized browser campaign lessons against independent CSV demand.

Input uses original CSV names, local HH:MM intervals and effective module credit.
No application, solver or application validator imports are permitted here.
"""

import importlib.util
import json
import re
import sys
from collections import defaultdict
from datetime import date
from itertools import pairwise
from pathlib import Path


def _integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError("Minutes and capacities must be exact non-negative integers")
    return value


def _day(value):
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("School dates must use YYYY-MM-DD")
    return parsed


def _minute(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:[01]\d|2[0-3]):[0-5]\d|24:00", value
    ):
        raise ValueError("Grid times must use HH:MM")
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def _interval(start, end):
    result = _minute(start), _minute(end)
    if result[0] >= result[1]:
        raise ValueError("Physical intervals must be positive")
    return result


def _assignment(value):
    if (
        not isinstance(value, list)
        or len(value) != 3
        or any(not isinstance(item, str) or not item for item in value)
    ):
        raise ValueError("Assignment must identify original course, class and subject")
    return tuple(value)


def _overlaps(left, right):
    return left[0] < right[1] and right[0] < left[1]


def _continuous_gap(intervals, window):
    start, end = window
    cursor, longest = start, 0
    for left, right in sorted(intervals):
        if right <= start or left >= end:
            continue
        longest = max(longest, min(left, end) - cursor)
        cursor = max(cursor, min(right, end))
    return max(longest, end - cursor)


def validate(originals, snapshot):
    school = snapshot["school"]
    start, end = _day(school["start_date"]), _day(school["hard_end_date"])
    if start > end:
        raise ValueError("School date bounds are invalid")
    teaching_dates = {_day(value) for value in school["teaching_dates"]}
    grid = {
        day: {
            _interval(*interval) for interval in school["grid"].get(day.isoformat(), [])
        }
        for day in teaching_dates
    }
    lunch = school.get("lunch")
    if lunch is not None:
        lunch_window = _interval(lunch["start"], lunch["end"])
        lunch_minutes = _integer(lunch["minimum_minutes"], 1)
        if lunch_minutes > lunch_window[1] - lunch_window[0]:
            raise ValueError("Lunch configuration is incomplete or impossible")
    assignments = {
        (item["course"], item["class"], item["subject"]): item
        for item in originals["demand"]
    }
    if len(assignments) != len(originals["demand"]):
        raise ValueError("Duplicate independent demand")
    classes = {
        (item["course"], item["class"]): _integer(item["size"], 1)
        for item in originals["classes"]
    }
    modules = {
        key: sorted(
            originals["subjects"][key[2]]["modules"], key=lambda item: item["order"]
        )
        for key in assignments
    }
    completed = defaultdict(int)
    for entry in snapshot["executed"]:
        key = _assignment(entry["assignment"])
        identity = key, entry["module"]
        if (
            key not in modules
            or identity in completed
            or entry["module"] not in {item["code"] for item in modules[key]}
        ):
            raise ValueError("Unknown or duplicate effective module credit")
        completed[identity] = _integer(entry["minutes"])
    required, executed = 0, sum(completed.values())
    for key, requirements in modules.items():
        for module in requirements:
            required += _integer(module["minutes"], 1)
            if completed[key, module["code"]] > module["minutes"]:
                raise ValueError("Executed module credit exceeds original demand")
    unavailable = defaultdict(list)
    for blocked in school["unavailable"]:
        kind = blocked["kind"]
        resource = (
            tuple(blocked["resource"]) if kind == "class" else blocked["resource"]
        )
        if kind not in {"class", "teacher", "room"}:
            raise ValueError("Unknown unavailability resource kind")
        unavailable[kind, resource, _day(blocked["date"])].append(
            _interval(blocked["start"], blocked["end"])
        )
    grouped, occupied, identities = defaultdict(list), defaultdict(list), set()
    for lesson in snapshot["lessons"]:
        identity = lesson["id"]
        if (
            type(identity) not in {int, str}
            or not identity
            or (type(identity) is int and identity < 0)
            or identity in identities
        ):
            raise ValueError("Missing or duplicate lesson identity")
        identities.add(identity)
        key = _assignment(lesson["assignment"])
        if key not in assignments:
            raise ValueError("Unknown lesson assignment")
        assignment = assignments[key]
        teacher = lesson["teacher"]
        if teacher != assignment["teacher"] or key[2] not in originals["teachers"].get(
            teacher, {}
        ).get("subjects", []):
            raise ValueError("Teacher assignment or competency does not match")
        room = originals["rooms"].get(lesson["room"])
        if (
            not room
            or room["type"] != originals["subjects"][key[2]]["room_type"]
            or _integer(room["capacity"], 1) < classes[key[:2]]
        ):
            raise ValueError("Room type or capacity is incompatible")
        day = _day(lesson["date"])
        interval = _interval(lesson["start"], lesson["end"])
        if (
            not start <= day <= end
            or day not in teaching_dates
            or interval not in grid[day]
        ):
            raise ValueError("Lesson is outside the teaching calendar or physical grid")
        credit = _integer(lesson["credit_minutes"], 1)
        for part in lesson["slices"]:
            _integer(part["offset"])
            _integer(part["minutes"], 1)
        if credit > interval[1] - interval[0]:
            raise ValueError("Credit exceeds physical lesson duration")
        for kind, resource in [
            ("class", key[:2]),
            ("teacher", teacher),
            ("room", lesson["room"]),
        ]:
            resource_day = kind, resource, day
            if any(
                _overlaps(interval, blocked) for blocked in unavailable[resource_day]
            ):
                raise ValueError("Lesson uses an unavailable resource")
            occupied[resource_day].append(interval)
        grouped[key].append((day, interval, str(identity), lesson))
    for (kind, _, _), intervals in occupied.items():
        ordered = sorted(intervals)
        if any(_overlaps(left, right) for left, right in pairwise(ordered)):
            raise ValueError("Resource overlap")
        if (
            lunch is not None
            and kind in {"class", "teacher"}
            and _continuous_gap(intervals, lunch_window) < lunch_minutes
        ):
            raise ValueError("Resource has no continuous lunch break")
    planned = 0
    for key, requirements in modules.items():
        offsets = {
            module["code"]: completed[key, module["code"]] for module in requirements
        }
        remaining = {
            module["code"]: module["minutes"] - offsets[module["code"]]
            for module in requirements
        }
        lessons = sorted(grouped[key])
        for index, (_, interval, _, lesson) in enumerate(lessons):
            credit = lesson["credit_minutes"]
            if index < len(lessons) - 1 and credit != interval[1] - interval[0]:
                raise ValueError(
                    "Only the final editable lesson may have partial credit"
                )
            planned += credit
            expected_slices = []
            for module in requirements:
                code = module["code"]
                part = min(credit, remaining[code])
                if part:
                    expected_slices.append(
                        {"module": code, "offset": offsets[code], "minutes": part}
                    )
                    remaining[code] -= part
                    offsets[code] += part
                    credit -= part
                if not credit:
                    break
            if credit or lesson["slices"] != expected_slices:
                raise ValueError(
                    "Module slices, chronological credit or offsets do not match"
                )
        if any(remaining.values()):
            raise ValueError("Planned credit does not cover exact residual demand")
    return {
        "schema_version": 1,
        "valid": True,
        "required_minutes": required,
        "executed_minutes": executed,
        "planned_minutes": planned,
        "lessons": len(identities),
    }


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python scripts/validate-e2e-schedule.py <materialized-snapshot.json>"
        )
    script = Path(__file__).with_name("inspect-e2e-data.py")
    spec = importlib.util.spec_from_file_location("original_csv_inspector", script)
    inspector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inspector)
    originals = inspector.inspect(script.parent.parent / "frontend/e2e/data/originals")
    result = validate(
        originals, json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    )
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
