from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.scheduler.domain.constraints import (
    SchedulerConstraintPolicy,
    placement_facts,
)


@dataclass(frozen=True)
class SchedulerConstraintRules:
    """Compatibility facade for application services migrating to the domain policy."""

    policy: SchedulerConstraintPolicy
    blockers: tuple[str, ...] = ()

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any]) -> SchedulerConstraintRules:
        result = SchedulerConstraintPolicy.from_snapshot(snapshot)
        return cls(
            policy=result.policy or SchedulerConstraintPolicy(),
            blockers=tuple(row.message for row in result.configuration_violations),
        )

    @property
    def specific_rooms(self):
        return self.policy.specific_rooms

    @property
    def locked_timeslots(self):
        return self.policy.locked_timeslots

    @property
    def teacher_unavailable_timeslots(self):
        return self.policy.teacher_unavailable_timeslots

    @property
    def teacher_unavailable_days(self):
        return self.policy.teacher_unavailable_days

    @property
    def teacher_unavailable_dates(self):
        return self.policy.teacher_unavailable_dates

    @property
    def teacher_unavailable_date_slots(self):
        return self.policy.teacher_unavailable_date_slots

    @property
    def teacher_preferred_timeslots(self):
        return self.policy.teacher_preferred_timeslots

    def is_candidate_allowed(self, candidate: Any) -> bool:
        return not self.policy.evaluate(placement_facts(candidate)).hard_violations

    def preference_bonus(self, teacher_id: int, timeslot_id: int) -> int:
        return int((teacher_id, timeslot_id) in self.policy.teacher_preferred_timeslots)

    def violation_for_block(self, block: Any) -> str | None:
        violations = self.policy.evaluate(placement_facts(block)).hard_violations
        return violations[0].message if violations else None
