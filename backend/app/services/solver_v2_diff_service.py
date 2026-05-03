"""
Service for generating statistical diff summary between active schedule and draft schedule.
"""
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.services.schedule_service import _resolve_repair_window_days_sync


def get_diff_summary_sync(db: Session, organization_id: int, gen_id: str) -> dict:
    """Computes the 6 statistical indicators for Phase H."""
    today = date.today()
    repair_window_days = _resolve_repair_window_days_sync(db, organization_id)
    frozen_until = today + timedelta(days=repair_window_days)
    compared_from_date = frozen_until + timedelta(days=1)

    # 1 & 2. Dates per class
    def get_class_max_dates(is_draft: bool) -> dict[int, date]:
        q = db.query(
            models.Lesson.class_id,
            func.max(models.ScheduleOutput.date).label("max_date")
        ).join(
            models.Lesson, models.Lesson.id == models.ScheduleOutput.lesson_id
        ).filter(
            models.ScheduleOutput.organization_id == organization_id,
            models.ScheduleOutput.is_draft.is_(is_draft),
            models.ScheduleOutput.date >= compared_from_date
        )
        if is_draft:
            q = q.filter(models.ScheduleOutput.generation_id == gen_id)
        
        q = q.group_by(models.Lesson.class_id)
        return {row.class_id: row.max_date for row in q.all() if row.max_date}

    active_dates = get_class_max_dates(False)
    draft_dates = get_class_max_dates(True)

    # Calculate delta_projected_end_date_days
    global_active_max = max(active_dates.values()) if active_dates else today
    global_draft_max = max(draft_dates.values()) if draft_dates else today
    delta_projected_end_date_days = (global_draft_max - global_active_max).days

    # Calculate end_date_spread_days (in draft)
    if draft_dates:
        end_date_spread_days = (max(draft_dates.values()) - min(draft_dates.values())).days
    else:
        end_date_spread_days = 0

    # 3 & 4. Churn and total blocks changed
    def fetch_blocks(is_draft: bool):
        q = db.query(
            models.ScheduleOutput.lesson_id,
            models.ScheduleOutput.timeslot_id,
            models.ScheduleOutput.date,
        ).filter(
            models.ScheduleOutput.organization_id == organization_id,
            models.ScheduleOutput.is_draft.is_(is_draft),
            models.ScheduleOutput.date >= compared_from_date,
        )
        if is_draft:
            q = q.filter(models.ScheduleOutput.generation_id == gen_id)
        return {(r.lesson_id, r.timeslot_id, r.date) for r in q.all()}

    active_blocks = fetch_blocks(False)
    draft_blocks = fetch_blocks(True)

    added = len(draft_blocks - active_blocks)
    removed = len(active_blocks - draft_blocks)
    total_blocks_changed = added + removed

    total_outside_frozen = len(active_blocks)
    churn_ratio = 0.0
    if total_outside_frozen > 0:
        churn_ratio = round(total_blocks_changed / total_outside_frozen, 3)

    # 5. Backlog Remaining Hours (Formula 2: Theoretical demand - Draft scheduled)
    class_subject_pairs = db.query(models.ClassSubjectLink).join(models.Class).filter(
        models.Class.organization_id == organization_id,
        models.Class.is_archived.is_(False)
    ).all()
    
    total_demand_hours = 0
    for link in class_subject_pairs:
        subj_hours = db.query(func.sum(models.Module.hours_total)).filter(
            models.Module.subject_id == link.subject_id
        ).scalar() or 0
        total_demand_hours += subj_hours

    q_scheduled = db.query(func.count(models.ScheduleOutput.id)).filter(
        models.ScheduleOutput.organization_id == organization_id,
        (
            (models.ScheduleOutput.is_draft.is_(False) & (models.ScheduleOutput.date <= frozen_until)) |
            (models.ScheduleOutput.is_draft.is_(True) & (models.ScheduleOutput.generation_id == gen_id))
        )
    )
    scheduled_hours = q_scheduled.scalar() or 0
    backlog_remaining_hours = max(0.0, float(total_demand_hours - scheduled_hours))

    # 6. Aggregate Gap Variation
    def calculate_gaps(is_draft: bool) -> int:
        ts_rows = db.query(models.Timeslot).filter(models.Timeslot.organization_id == organization_id).all()
        ts_rows.sort(key=lambda t: (t.day_of_week, t.start_time))
        ts_order = {ts.id: idx for idx, ts in enumerate(ts_rows)}

        q = db.query(
            models.Lesson.class_id,
            models.ScheduleOutput.date,
            models.ScheduleOutput.timeslot_id
        ).join(
            models.Lesson, models.Lesson.id == models.ScheduleOutput.lesson_id
        ).filter(
            models.ScheduleOutput.organization_id == organization_id
        )
        if is_draft:
            q = q.filter(
                (models.ScheduleOutput.is_draft.is_(False) & (models.ScheduleOutput.date <= frozen_until)) |
                (models.ScheduleOutput.is_draft.is_(True) & (models.ScheduleOutput.generation_id == gen_id))
            )
        else:
            q = q.filter(models.ScheduleOutput.is_draft.is_(False))

        blocks = q.all()
        day_class_slots = {}
        for b in blocks:
            if b.date is None: continue
            key = (b.class_id, b.date)
            day_class_slots.setdefault(key, []).append(ts_order.get(b.timeslot_id, 0))

        total_gaps = 0
        for slots in day_class_slots.values():
            if not slots: continue
            mi, ma = min(slots), max(slots)
            span = ma - mi + 1
            actual = len(set(slots))
            total_gaps += max(0, span - actual)
        
        return total_gaps

    active_gaps = calculate_gaps(False)
    draft_gaps = calculate_gaps(True)
    aggregate_gap_variation = draft_gaps - active_gaps

    return {
        "delta_projected_end_date_days": delta_projected_end_date_days,
        "end_date_spread_days": end_date_spread_days,
        "churn_outside_frozen_ratio": churn_ratio,
        "total_blocks_changed": total_blocks_changed,
        "backlog_remaining_hours": backlog_remaining_hours,
        "aggregate_gap_variation": aggregate_gap_variation,
    }
