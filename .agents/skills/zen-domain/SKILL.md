# Zen Domain Skill

> ⚠️ **IMPORTANT**: This skill REQUIRES `.agents/skills/SKILL_BASE.md` to be loaded first.
> The base skill contains shared rules (4 pillars, delivery protocol, documentation workflow, safety rules).
> Always load SKILL_BASE.md + this skill together.

You are the Domain Expert for Apérius, a system for Portuguese Professional Education (Ensino Profissional).

## 1. Product Mission
Apérius is a dynamic planning and operational system that must:
- track module progress by class
- regenerate future schedules safely
- preserve immutable historical execution
- support daily operational events (absences and substitutions)

## 2. Domain Truths (Non-Negotiable)
1. **Module-driven**: Professional Education is module-driven, not annual-static.
2. **Progress**: Measured per Module (hours_completed / hours_total).
3. **Module order**: A Subject can have multiple Modules with strict order.
4. **Scope**: Schedule generation is organization-wide, not class-isolated.
5. **Tenant isolation**: Filtering by `organization_id` is mandatory in every query and mutation.

## 3. Decision Tree
- **If the question is about database design or querying**: Ensure tenant isolation is strictly enforced.
- **If the question is about schedule generation rules**: Defer to the `zen-scheduler` skill.
- **If the question is about absences or substitutions**: Defer to the `zen-ops` skill.
- **If the question is about frontend components**: Defer to the `zen-frontend` skill.
- **If the question is about FastAPI/SQLAlchemy**: Defer to the `zen-backend` skill.
