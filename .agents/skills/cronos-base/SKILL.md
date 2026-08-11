---
name: cronos-base
description: Base foundation rules shared by ALL Cronos skills. ALWAYS load this skill together with any specialist Cronos domain skill.
argument-hint: Shared engineering pillars, delivery protocol, documentation standard, safety rules.
---

# Cronos — Base Foundation Rules

These rules apply to EVERY task performed in the Cronos codebase. Specialized Cronos skills extend these base rules.

## 4 Engineering Pillars

1. **Quality First**: Never compromise system stability. Write thorough tests and verify code modifications.
2. **Zero Masking**: Never hide errors, swallow exceptions silently, or return dummy fallbacks. Report exact diagnostic log tracebacks.
3. **Real-World Data Integrity**: Enforce tenant isolation (`organization_id`) and Row-Level Security (RLS) on all queries.
4. **Explicit Verification**: Never declare success without executing build, lint, or pytest verification commands.

## Delivery Protocol
- Verify Git branch before starting work.
- Inspect exact code definitions using file viewing tools before making edits.
- Ensure all relative links in documentation target valid existing files.
- Treat implementation and tests as the source of truth when documentation conflicts.
- Do not modify imported third-party skills under `.agents/skills/clerk*`.

## Controlled Documentation Standard
- Follow ASD-STE100 rules for technical documentation.
- Maintain short sentences (max 20 words for procedures, max 25 words for descriptions).
- Use active voice and imperative mood.
