from datetime import date, timedelta

import pytest

from app.scheduler.domain.quality import AdaptiveQualityPolicy, adaptive_quality_vector

START = date(2026, 9, 1)
PREFERRED = START + timedelta(days=10)
HARD_END = START + timedelta(days=12)
POLICY = AdaptiveQualityPolicy("laboratory-example", tuple(range(1, 11)), 1)


def quality(first_day, second_day, *, disruption=0):
    return adaptive_quality_vector(
        {1: START + timedelta(days=first_day), 2: START + timedelta(days=second_day)},
        class_ids=(1, 2),
        origin=START,
        preferred_end_date=PREFERRED,
        hard_end_date=HARD_END,
        disruption_cost=disruption,
        teacher_gap_minutes=0,
        class_gap_minutes=0,
        preference_cost=0,
        room_change_cost=0,
        policy=POLICY,
    )


def test_t15_advancing_the_latest_class_wins_with_equal_disruption():
    assert quality(8, 7) < quality(10, 2)


def test_t16_no_reward_for_delaying_one_class_to_match_another():
    assert quality(8, 5) < quality(8, 6)


def test_t17_margin_cost_rises_near_preference_with_explicit_coefficients():
    assert quality(3, 3, disruption=1) < quality(4, 4, disruption=0)
    assert quality(4, 4, disruption=0) < quality(3, 3, disruption=10)
    assert quality(9, 9, disruption=8) < quality(10, 10, disruption=0)


def test_t18_excess_over_preference_dominates_any_editable_disruption():
    assert quality(10, 8, disruption=1000) < quality(11, 8, disruption=0)


def test_hard_end_and_incomplete_class_are_rejected():
    with pytest.raises(ValueError):
        quality(13, 8)
    with pytest.raises(ValueError):
        adaptive_quality_vector(
            {1: START},
            class_ids=(1, 2),
            origin=START,
            preferred_end_date=PREFERRED,
            hard_end_date=HARD_END,
            disruption_cost=0,
            teacher_gap_minutes=0,
            class_gap_minutes=0,
            preference_cost=0,
            room_change_cost=0,
            policy=POLICY,
        )


def test_policy_coefficients_must_be_immutable():
    with pytest.raises(ValueError):
        AdaptiveQualityPolicy("laboratory-example", [1, 2], 1)


def test_recovery_dates_must_follow_start_preference_and_hard_end():
    with pytest.raises(ValueError, match="scheduling dates"):
        adaptive_quality_vector(
            {1: START},
            class_ids=(1,),
            origin=START,
            preferred_end_date=START - timedelta(days=1),
            hard_end_date=HARD_END,
            disruption_cost=0,
            teacher_gap_minutes=0,
            class_gap_minutes=0,
            preference_cost=0,
            room_change_cost=0,
            policy=POLICY,
        )
