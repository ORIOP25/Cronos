"""Pure reasons for a school administrator to request generation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class EligibilityReason(StrEnum):
    FIRST_GENERATION = "FIRST_GENERATION"
    PLANNING_CHANGE = "PLANNING_CHANGE"
    RETRY_INCOMPLETE = "RETRY_INCOMPLETE"
    PERIODIC_RENEWAL = "PERIODIC_RENEWAL"
    ACTIVE_JOB = "ACTIVE_JOB"


@dataclass(frozen=True)
class EligibilityFacts:
    school_today: date
    planning_revision: int
    last_completed_planning_revision: int | None
    last_successful_generation_date: date | None
    last_attempt_incomplete: bool
    active_job: bool


@dataclass(frozen=True)
class EligibilityDecision:
    reasons: tuple[EligibilityReason, ...]
    blocker: EligibilityReason | None = None

    @property
    def can_generate(self) -> bool:
        return bool(self.reasons) and self.blocker is None


def generation_eligibility(facts: EligibilityFacts) -> EligibilityDecision:
    if type(facts.school_today) is not date:
        raise ValueError("School today must be a local date.")
    if type(facts.planning_revision) is not int or facts.planning_revision < 0:
        raise ValueError("Planning revision must be nonnegative.")
    completed_revision = facts.last_completed_planning_revision
    last_success = facts.last_successful_generation_date
    if (completed_revision is None) != (last_success is None):
        raise ValueError("A complete proposal needs both its revision and completion date.")
    if completed_revision is not None and (
        type(completed_revision) is not int
        or completed_revision < 0
        or completed_revision > facts.planning_revision
    ):
        raise ValueError("Completed planning revision is invalid.")
    if last_success is not None and (
        type(last_success) is not date or last_success > facts.school_today
    ):
        raise ValueError("Last successful generation date is invalid.")

    reasons = []
    if completed_revision is None:
        reasons.append(EligibilityReason.FIRST_GENERATION)
    elif facts.planning_revision > completed_revision:
        reasons.append(EligibilityReason.PLANNING_CHANGE)
    if facts.last_attempt_incomplete:
        reasons.append(EligibilityReason.RETRY_INCOMPLETE)
    if last_success is not None and (facts.school_today - last_success).days >= 28:
        reasons.append(EligibilityReason.PERIODIC_RENEWAL)
    blocker = EligibilityReason.ACTIVE_JOB if facts.active_job else None
    return EligibilityDecision(tuple(reasons), blocker)
