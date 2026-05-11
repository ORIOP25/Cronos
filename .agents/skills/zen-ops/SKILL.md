# Zen Ops Skill

> ⚠️ **IMPORTANT**: This skill REQUIRES `.agents/skills/SKILL_BASE.md` to be loaded first.
> The base skill contains shared rules (4 pillars, delivery protocol, documentation workflow, safety rules).
> Always load SKILL_BASE.md + this skill together.

You manage the day-to-day operational features of Aperius, with a priority focus on Absences and Substitutions.

## 1. Absences and Substitutions
Design for:
1. **Immutable occurrence history** (what actually happened).
2. Clear distinction between planned schedule and executed lesson outcomes.
3. **Safe substitution eligibility checks**:
   - same organization,
   - teacher from a different subject but from the same affected class,
   - never same subject teacher from a different class,
   - no conflict in slot,
   - consistent progression/accounting updates.
4. **Recommendation-assisted decision for substitutions**:
   - system ranks eligible candidates with deterministic criteria,
   - admin makes the final decision.
5. Explicit handling of `GAP`, `GIVEN`, `SUBSTITUTED` states.
6. Transparent debt/progress impact after each occurrence decision.

## 2. Key Files
- `app/services/occurrence_service.py` — Occurrence state machine, auto-confirm, debt calc, substitution recommendations
- `app/services/substitution_service.py` — Substitution eligibility and creation
- `app/services/lesson_log_service.py` — Lesson execution records (PENDING/COMPLETED/OCCURRENCE)
- `app/services/timesheet_service.py` — Teacher weekly timesheet workflow (OPEN→SUBMITTED→APPROVED)
- `app/api/v1/endpoints/occurrences.py` — Occurrence endpoints
- `app/api/v1/endpoints/substitutions.py` — Substitution endpoints
- `app/api/v1/endpoints/timesheets.py` — Timesheet endpoints
