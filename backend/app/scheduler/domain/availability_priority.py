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
from fractions import Fraction
from math import ceil

from app.scheduler.domain.calendar import Period
from app.scheduler.domain.candidate import Assignment, PlanningSnapshot, UnavailableResource

ResourceKey = tuple[str, int]
TEACHER = "teacher"
CLASS = "class"
RESOURCE_KINDS = frozenset((TEACHER, CLASS))
PeriodKey = tuple[datetime, datetime]

# Realistic school: a failing strict pass shows 24 h of deficit, a succeeding one at most 2 h.
PACE_MIN_BEHIND = 5
PACE_BEHIND_SHARE = Fraction(1, 10)
PACE_MIN_DEFICIT_MINUTES = 10 * 60
PACE_FALLING_WEEKS = 2


def on_pace(demand: int, initial_demand: int, capacity_left: int, initial_capacity: int) -> bool:
    """T05: the remaining demand is not behind its share of the remaining capacity."""
    return demand * initial_capacity >= initial_demand * capacity_left


def resource_keys(assignment: Assignment) -> tuple[ResourceKey, ...]:
    return (
        (TEACHER, assignment.teacher_id),
        *((CLASS, class_id) for class_id in assignment.class_ids),
    )


def is_avoided(
    snapshot: PlanningSnapshot,
    assignment: Assignment,
    period: Period,
    *,
    evitar_kinds: frozenset[str] = RESOURCE_KINDS,
) -> bool:
    """True when the period is Evitar for the assignment's teacher or one of its classes.

    ``evitar_kinds`` names the resource kinds whose Evitar counts.
    """
    return any(
        key[0] in evitar_kinds and _soft_overlaps(snapshot, key, period)
        for key in resource_keys(assignment)
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

    def behind_pace(self, capacity: int) -> bool:
        """The negation of ``on_pace``: the demand is ahead of its share of the capacity left."""
        return self.demand * self.total > self.initial_demand * capacity


def _pressure(track: _Track, start: datetime) -> Fraction:
    """T07: demand over the capacity left from ``start``, capped at one; zero without demand."""
    if track.demand <= 0:
        return Fraction(0)
    capacity = track.capacity_from(start)
    if capacity <= track.demand:
        return Fraction(1)
    return Fraction(track.demand, capacity)


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

    def tightness(self, assignment: Assignment, period: Period) -> Fraction:
        """T07: the largest demand over the capacity left from this period, capped at one.

        A resource without minutes left, or no tracked resource at all, is not tight.
        """
        return max(
            (_pressure(track, period.start_utc) for track in self._tracks_of(assignment)),
            default=Fraction(0),
        )

    def urgency(self, assignment: Assignment, period: Period) -> int:
        """Schedule priorities T09: the smallest remaining capacity among resources
        that cannot skip this period; lower wins, the others share the ceiling."""
        urgent = [
            capacity
            for track in self._tracks_of(assignment)
            if track.demand > 0
            and (capacity := track.capacity_from(period.start_utc)) - track.demand
            <= period.duration_minutes
        ]
        return min(urgent, default=self._ceiling)

    def is_necessary(
        self,
        assignment: Assignment,
        period: Period,
        *,
        evitar_kinds: frozenset[str] = RESOURCE_KINDS,
    ) -> bool:
        """Whether a resource needs this period to keep its remaining demand feasible.

        ``evitar_kinds`` names the resource kinds whose Evitar blocks count. In an
        Evitar that its resource can still keep free, only lost capacity makes the
        period necessary: pace measured over hours to avoid would push lessons into
        that Evitar (T08).
        """
        if self.needed_evitar(assignment, period, evitar_kinds=evitar_kinds):
            return True
        # An Evitar the resource can still keep free: pace alone (of any resource of
        # the option) must not pull the lesson into it; only lost capacity can.
        avoidable = any(
            key[0] in evitar_kinds and _soft_overlaps(self._snapshot, key, period)
            for key in resource_keys(assignment)
        )
        for key in resource_keys(assignment):
            track = self._tracks.get(key)
            if track is None or track.demand <= 0:
                continue
            capacity = track.capacity_from(period.start_utc)
            if track.demand > capacity - period.duration_minutes:
                return True
            if not avoidable and track.behind_pace(capacity):
                return True
        return False

    def needed_evitar(
        self,
        assignment: Assignment,
        period: Period,
        *,
        evitar_kinds: frozenset[str] = RESOURCE_KINDS,
    ) -> frozenset[ResourceKey]:
        """The resources whose own Evitar at this period their demand cannot avoid.

        Their Evitar does not penalise the option (T08): the rest of their time,
        neutral or all of it, can no longer hold what they still have to teach.
        """
        needed = set()
        for key in resource_keys(assignment):
            track = self._tracks.get(key)
            if (
                track is None
                or track.demand <= 0
                or key[0] not in evitar_kinds
                or not _soft_overlaps(self._snapshot, key, period)
            ):
                continue
            capacity = track.capacity_from(period.start_utc)
            if (
                track.demand > capacity - period.duration_minutes
                or track.demand > track.neutral_capacity_from(period.start_utc)
            ):
                needed.add(key)
        return frozenset(needed)

    def unfavorable(
        self,
        assignment: Assignment,
        period: Period,
        *,
        evitar_kinds: frozenset[str] = RESOURCE_KINDS,
    ) -> bool:
        return any(
            key[0] in evitar_kinds and _soft_overlaps(self._snapshot, key, period)
            for key in resource_keys(assignment)
        )

    def allows(
        self,
        assignment: Assignment,
        period: Period,
        planned: Iterable[tuple[Assignment, int]] = (),
        *,
        evitar_kinds: frozenset[str] = RESOURCE_KINDS,
    ) -> bool:
        """T08: inside a resource's own Evitar, demand must exceed its neutral capacity.

        ``planned`` holds lessons of the same pass not yet placed, as (assignment,
        credited minutes); their minutes leave the demand before the comparison.
        """
        planned_minutes: defaultdict[ResourceKey, int] = defaultdict(int)
        for other, minutes in planned:
            for key in resource_keys(other):
                planned_minutes[key] += minutes
        blocked = any(
            key[0] in evitar_kinds
            and _soft_overlaps(self._snapshot, key, period)
            and self.demand(key) - planned_minutes[key] <= self.neutral_capacity(key, period)
            for key in resource_keys(assignment)
        )
        if blocked:
            self.refused += 1
        return not blocked

    def cannot_finish(self, period: Period) -> bool:
        """True when a resource has more minutes left than eligible minutes from this period.

        Capacity counts each eligible period once, so it never undercounts: the pass
        that reaches this state ends with missing hours.
        """
        return any(
            track.demand > track.capacity_from(period.start_utc) for track in self._tracks.values()
        )

    def pace_signal(self, start: datetime) -> PaceSignal:
        """The tracked resources behind their linear pace from ``start``, and their deficit."""
        tracked = [track for track in self._tracks.values() if track.demand > 0]
        behind = 0
        deficit = Fraction(0)
        for track in tracked:
            capacity = track.capacity_from(start)
            if track.behind_pace(capacity):
                behind += 1
                deficit += track.demand - Fraction(track.initial_demand * capacity, track.total)
        return PaceSignal(behind, deficit, len(tracked))

    def place(self, assignment: Assignment, minutes: int) -> None:
        for key in resource_keys(assignment):
            self._tracks[key].demand -= minutes

    def _tracks_of(self, assignment: Assignment) -> list[_Track]:
        return [self._tracks[key] for key in resource_keys(assignment) if key in self._tracks]


@dataclass(frozen=True)
class PaceSignal:
    """Weekly pace state of a pass: resources behind pace, their deficit, tracked count."""

    behind: int
    deficit_minutes: Fraction
    tracked: int

    @property
    def falling_behind(self) -> bool:
        return (
            self.behind >= max(PACE_MIN_BEHIND, ceil(PACE_BEHIND_SHARE * self.tracked))
            and self.deficit_minutes >= PACE_MIN_DEFICIT_MINUTES
        )


class PaceWatch:
    """Weekly pace checks of a weighted strict pass (SCHEDULE_PRIORITIES T07).

    The check runs at the first period of each ISO week; the pass gives up once
    ``PACE_FALLING_WEEKS`` checks in a row fall behind.
    """

    def __init__(self) -> None:
        self._week: tuple[int, int] | None = None
        self._falling_weeks = 0

    def gives_up(self, ledger: AvailabilityLedger, period: Period) -> bool:
        week = period.school_date.isocalendar()[:2]
        if week == self._week:
            return False
        self._week = week
        if ledger.pace_signal(period.start_utc).falling_behind:
            self._falling_weeks += 1
        else:
            self._falling_weeks = 0
        return self._falling_weeks >= PACE_FALLING_WEEKS
