---
name: cronos-domain
description: Specialist domain skill for Portuguese Professional Education (Ensino Profissional). Use when working on course structures, subject modules, hour tracking, or class invariants.
argument-hint: Requires cronos-base.
---

# Cronos Domain Skill

> ⚠️ **IMPORTANT**: Load `.agents/skills/cronos-base/SKILL.md` before using this skill.

You are the domain expert for Portuguese Professional Education (*Ensino Profissional*).

## Domain Invariants
- **Modular Structure**: Subjects contain ordered modules (*Módulos*) with positive required minutes.
- **Progress Accounting**: The append-only ledger records completed and debt minute deltas.
- **Non-Linear Schedule**: Generation places remaining module minutes within configured dates and timeslots.

## Relevant Documentation
- [Professional Education](../../../documentation/02_domain_model/PROFESSIONAL_EDUCATION.md)
- [Members and Access](../../../documentation/02_domain_model/MEMBERS_AND_ACCESS.md)
