---
name: zen-base
description: Base rules shared by ALL Aperius skills. ALWAYS load this together with any domain skill.
argument-hint: Shared rules: 4 engineering pillars, delivery protocol, documentation workflow, safety rules.
---

# Aperius — Base Rules (ALL Skills)

These rules apply to EVERY task in Aperius, regardless of the domain skill in use.

## 1. Non-negotiable engineering pillars (ALWAYS)
Every product and technical decision MUST preserve all four pillars:
1. Optimization
2. Stability
3. Scalability
4. Security

If a proposed change improves one pillar but degrades another, the change is not acceptable until all four are protected.

## 2. Delivery Protocol
For any requested implementation:
1. Confirm domain alignment first.
2. Implement smallest safe change set.
3. Validate with focused tests and direct sanity queries.
4. Report outcomes with concrete metrics.
5. Explicitly verify compliance with the four pillars.

Default heavy validation should target one organization unless explicitly requested otherwise.

## 3. Documentation Protocol
Mandatory documentation workflow:
- Always consult existing documentation in `/documentation` before proposing or implementing changes.
- **CRITICAL REQUIREMENT**: Whenever you change application code, logic, features, or architecture, YOU MUST update the relevant markdown files in `/documentation` in the exact same tool call or immediately after. This is non-negotiable.
- Do not leave domain-relevant changes undocumented. If you change code, you MUST change the documentation.
- **NEVER finish a task without ensuring the documentation reflects the new state.**
- If something is not yet decided, document it explicitly as "a definir" instead of assuming.

## 4. Safety and Operational Rules
- Never commit or push automatically.
- Never bypass tenant isolation.
- Never mutate past execution history to "make metrics look good".
- Never trade hard constraints for prettier output.

## 5. Documentation-first execution rule
Before coding or recommending architecture:
1. Read the relevant docs for Interface, Business Rules, and Database layers.
2. Align decisions with documented invariants and current phase constraints.
3. After implementation, **SYNC DOCS TO MATCH FINAL BEHAVIOR**. Every code change must be accompanied by a documentation update.
4. If there is a conflict between code and docs, fix the documentation immediately or raise the mismatch explicitly.

## 6. Stack Baseline
- **Backend**: Python 3.12, FastAPI, SQLAlchemy Async (Mapped[T] style), Pydantic v2, Celery, Alembic.
- **Frontend**: React + CoreUI + React Query + Zustand + React Router v7.
- **Infra**: Docker Compose, PostgreSQL 15, Redis 7.
- **Tenant isolation**: Filtering by `organization_id` is mandatory in every query and mutation.
- **Performance**: Prevent N+1 patterns; use `selectinload` / `joinedload`. Treat cache as optimization, never as source of truth.
