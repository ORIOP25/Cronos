from datetime import date

from app.services.scheduler_disruption import DisruptionScorer


def _block(key, block_date="2026-03-02", room=1, slot=1, class_id=10, teacher=20):
    return {
        "stable_block_key": key,
        "class_id": class_id,
        "teacher_id": teacher,
        "room_id": room,
        "timeslot_id": slot,
        "date": block_date,
        "is_recovery_block": False,
    }


def test_disruption_prefers_room_only_and_affected_stakeholders():
    original = [_block("a"), _block("b", class_id=11, teacher=21)]
    room_only = [_block("a", room=2), original[1]]
    unrelated_move = [original[0], _block("b", block_date="2026-03-09", class_id=11, teacher=21)]
    scorer = DisruptionScorer()

    low = scorer.score(
        original,
        room_only,
        school_today=date(2026, 2, 10),
        affected_class_ids={10},
        affected_teacher_ids={20},
    )
    high = scorer.score(
        original,
        unrelated_move,
        school_today=date(2026, 2, 10),
        affected_class_ids={10},
        affected_teacher_ids={20},
    )

    assert low.total < high.total
    assert low.room_only_changes == 1
    assert high.ripple_blocks == 1


def test_near_term_change_scores_higher_than_far_future_change():
    scorer = DisruptionScorer()
    original_near = [_block("a", block_date="2026-02-12")]
    proposed_near = [_block("a", block_date="2026-02-13")]
    original_far = [_block("a", block_date="2026-05-12")]
    proposed_far = [_block("a", block_date="2026-05-13")]

    near = scorer.score(
        original_near,
        proposed_near,
        school_today=date(2026, 2, 10),
        affected_class_ids={10},
        affected_teacher_ids={20},
    )
    far = scorer.score(
        original_far,
        proposed_far,
        school_today=date(2026, 2, 10),
        affected_class_ids={10},
        affected_teacher_ids={20},
    )

    assert near.total > far.total
    assert near.to_metrics()["date_time_changes"] == 1
