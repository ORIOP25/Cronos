from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import ceil
from typing import Any

from app.services.scheduler_complete_demand import CompleteDemandLedger


@dataclass(frozen=True)
class HorizonSelection:
    start_date: date
    end_date: date
    horizon_days: int
    complexity_score: float
    estimated_candidate_count: int
    factors: dict[str, float | int]


class AdaptiveHorizonSelector:
    MIN_HORIZON_DAYS = 14
    MAX_HORIZON_DAYS = 84
    CANDIDATES_PER_SOLVE_SECOND = 100

    def select(
        self,
        snapshot: dict[str, Any],
        ledger: CompleteDemandLedger,
        *,
        start_date: date,
        remaining_solve_seconds: float,
    ) -> HorizonSelection:
        hard_end = date.fromisoformat(snapshot["hard_end_date"])
        remaining_days = max(0, (hard_end - start_date).days + 1)
        class_count = len({item.class_id for item in ledger.items})
        teacher_count = len({item.teacher_id for item in ledger.items})
        room_count = len(snapshot.get("rooms", []))
        slot_count = len(snapshot.get("timetable_grid", []))
        demand_sessions = ceil(
            ledger.required_minutes / max(1, self._minimum_slot_minutes(snapshot))
        )
        impossible_count = sum(
            row.get("score") == -1
            for row in snapshot.get("teacher_availability", [])
        )
        availability_rows = len(snapshot.get("teacher_availability", []))
        impossible_density = impossible_count / max(1, availability_rows)
        teacher_contention = len(ledger.items) / max(1, teacher_count)
        room_contention = class_count / max(1, room_count)
        demand_pressure = demand_sessions / max(1, remaining_days * max(1, slot_count))

        score = min(
            100.0,
            class_count * 1.5
            + teacher_count * 0.8
            + min(8.0, room_count * 0.4)
            + slot_count * 0.25
            + min(25.0, demand_sessions / 40)
            + min(12.0, teacher_contention * 2)
            + min(12.0, room_contention * 2)
            + impossible_density * 15
            + min(10.0, demand_pressure * 10)
            + (10.0 if 0 < remaining_days < 90 else 0.0),
        )
        complexity_days = round(
            self.MAX_HORIZON_DAYS
            - (self.MAX_HORIZON_DAYS - self.MIN_HORIZON_DAYS) * score / 100
        )
        rooms_per_item = sum(
            len(item.eligible_room_ids) for item in ledger.items
        ) / max(1, len(ledger.items))
        weekday_slot_density = slot_count / 7
        estimated_candidates_per_day = max(
            1,
            ceil(len(ledger.items) * weekday_slot_density * rooms_per_item),
        )
        time_budget_candidates = max(
            estimated_candidates_per_day * self.MIN_HORIZON_DAYS,
            int(max(1.0, remaining_solve_seconds) * self.CANDIDATES_PER_SOLVE_SECOND),
        )
        budget_days = max(
            self.MIN_HORIZON_DAYS,
            time_budget_candidates // estimated_candidates_per_day,
        )
        horizon_days = min(complexity_days, budget_days, remaining_days)
        if remaining_days >= self.MIN_HORIZON_DAYS:
            horizon_days = max(self.MIN_HORIZON_DAYS, horizon_days)
        end_date = start_date + timedelta(days=max(0, horizon_days - 1))
        end_date = min(end_date, hard_end)
        estimated_count = estimated_candidates_per_day * horizon_days
        return HorizonSelection(
            start_date=start_date,
            end_date=end_date,
            horizon_days=horizon_days,
            complexity_score=round(score, 2),
            estimated_candidate_count=estimated_count,
            factors={
                "classes": class_count,
                "teachers": teacher_count,
                "rooms": room_count,
                "timeslots": slot_count,
                "demand_sessions": demand_sessions,
                "remaining_days": remaining_days,
                "impossible_availability_density": round(impossible_density, 4),
                "teacher_contention": round(teacher_contention, 4),
                "room_contention": round(room_contention, 4),
                "demand_pressure": round(demand_pressure, 4),
            },
        )

    @staticmethod
    def _minimum_slot_minutes(snapshot: dict[str, Any]) -> int:
        durations = []
        for row in snapshot.get("timetable_grid", []):
            start = AdaptiveHorizonSelector._minute(row["start_time"])
            end = AdaptiveHorizonSelector._minute(row["end_time"])
            if end > start:
                durations.append(end - start)
        return min(durations, default=60)

    @staticmethod
    def _minute(value: str) -> int:
        hours, minutes, *_rest = map(int, value.split(":"))
        return hours * 60 + minutes
