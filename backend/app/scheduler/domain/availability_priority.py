"""Availability priority rules for the constructive passes (tech spec T01-T06, T08, T14).

The ledger tracks, per teacher and per class, the eligible minutes left
(capacity) against the lesson minutes still missing (demand). Pure domain
rules: stdlib and scheduler domain types only, integers only, no clock.
"""

from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from app.scheduler.domain.calendar import Period
from app.scheduler.domain.candidate import Assignment, PlanningSnapshot, UnavailableResource

ResourceKey = tuple[str, int]
TEACHER = "teacher"
CLASS = "class"
PeriodKey = tuple[datetime, datetime]


def on_pace(demand: int, initial_demand: int, capacity_left: int, initial_capacity: int) -> bool:
    """T05: the remaining demand is not behind its share of the remaining capacity."""
    return demand * initial_capacity >= initial_demand * capacity_left


def resource_keys(assignment: Assignment) -> tuple[ResourceKey, ...]:
    return (
        (TEACHER, assignment.teacher_id),
        *((CLASS, class_id) for class_id in assignment.class_ids),
    )


def _period_key(period: Period) -> PeriodKey:
    return (period.start_utc, period.end_utc)


def _soft_overlaps(snapshot: PlanningSnapshot, key: ResourceKey, period: Period) -> bool:
    kind, identity = key
    resource = UnavailableResource.TEACHER if kind == TEACHER else UnavailableResource.CLASS
    return any(
        row.overlaps(period)
        for row in snapshot.soft_unavailable_on(resource, identity, period.school_date)
    )


def _suffix_sums(values: Sequence[int]) -> list[int]:
    """Entry i is the sum of values[i:]; the last entry is 0."""
    sums = [0] * (len(values) + 1)
    for index in range(len(values) - 1, -1, -1):
        sums[index] = sums[index + 1] + values[index]
    return sums


@dataclass
class _Track:
    """One resource: its demand and its capacity suffix sums by period start."""

    initial_demand: int
    demand: int
    starts: list[datetime]
    total_from: list[int]
    neutral_from: list[int]

    @property
    def total(self) -> int:
        return self.total_from[0]

    def capacity_from(self, start: datetime) -> int:
        return self.total_from[bisect_left(self.starts, start)]

    def neutral_capacity_from(self, start: datetime) -> int:
        return self.neutral_from[bisect_left(self.starts, start)]


def _track(
    snapshot: PlanningSnapshot, key: ResourceKey, demand: int, periods: Iterable[Period]
) -> _Track:
    ordered = sorted(periods, key=_period_key)
    minutes = [period.duration_minutes for period in ordered]
    neutral = [
        0 if _soft_overlaps(snapshot, key, period) else period.duration_minutes
        for period in ordered
    ]
    return _Track(
        initial_demand=demand,
        demand=demand,
        starts=[period.start_utc for period in ordered],
        total_from=_suffix_sums(minutes),
        neutral_from=_suffix_sums(neutral),
    )


class AvailabilityLedger:
    """Per-pass book of scarcity. Each construction pass builds its own ledger."""

    refused: int

    def __init__(self, snapshot: PlanningSnapshot, tracks: Mapping[ResourceKey, _Track]) -> None:
        self._snapshot = snapshot
        self._tracks = dict(tracks)
        self._ceiling = max((track.total for track in self._tracks.values()), default=0)
        self.refused = 0

    @classmethod
    def build(
        cls,
        snapshot: PlanningSnapshot,
        eligible: Mapping[int, Sequence[Period]],
        remaining: Mapping[int, int],
        occupied: Iterable[tuple[Assignment, Period]] = (),
    ) -> AvailabilityLedger:
        """Capacity is the union of eligible periods; demand is the missing minutes."""
        occupied_keys: defaultdict[ResourceKey, set[PeriodKey]] = defaultdict(set)
        for assignment, period in occupied:
            for key in resource_keys(assignment):
                occupied_keys[key].add(_period_key(period))
        demand: defaultdict[ResourceKey, int] = defaultdict(int)
        periods: defaultdict[ResourceKey, dict[PeriodKey, Period]] = defaultdict(dict)
        for row in snapshot.assignments:
            minutes = remaining.get(row.assignment_id, 0)
            if minutes <= 0:
                continue
            for key in resource_keys(row):
                demand[key] += minutes
                for period in eligible.get(row.assignment_id, ()):
                    if _period_key(period) not in occupied_keys[key]:
                        periods[key].setdefault(_period_key(period), period)
        tracks = {
            key: _track(snapshot, key, minutes, periods[key].values())
            for key, minutes in demand.items()
        }
        return cls(snapshot, tracks)

    def demand(self, key: ResourceKey) -> int:
        track = self._tracks.get(key)
        return track.demand if track else 0

    def capacity(self, key: ResourceKey) -> int:
        track = self._tracks.get(key)
        return track.total if track else 0

    def neutral_capacity(self, key: ResourceKey, period: Period) -> int:
        track = self._tracks.get(key)
        return track.neutral_capacity_from(period.start_utc) if track else 0

    def priority(self, assignment: Assignment, period: Period) -> int:
        """T06: the smallest capacity among resources on pace; lower wins."""
        paced = [
            track.total
            for track in self._tracks_of(assignment)
            if track.demand > 0
            and on_pace(
                track.demand,
                track.initial_demand,
                track.capacity_from(period.start_utc),
                track.total,
            )
        ]
        return min(paced, default=self._ceiling)

    def unfavorable(self, assignment: Assignment, period: Period) -> bool:
        return any(_soft_overlaps(self._snapshot, key, period) for key in resource_keys(assignment))

    def allows(self, assignment: Assignment, period: Period) -> bool:
        """T08: inside a resource's own Evitar, demand must exceed its neutral capacity."""
        blocked = any(
            _soft_overlaps(self._snapshot, key, period)
            and self.demand(key) <= self.neutral_capacity(key, period)
            for key in resource_keys(assignment)
        )
        if blocked:
            self.refused += 1
        return not blocked

    def place(self, assignment: Assignment, minutes: int) -> None:
        for key in resource_keys(assignment):
            self._tracks[key].demand -= minutes

    def _tracks_of(self, assignment: Assignment) -> list[_Track]:
        return [self._tracks[key] for key in resource_keys(assignment) if key in self._tracks]
