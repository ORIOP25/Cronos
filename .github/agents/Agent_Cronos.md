---
name: Agent_Cronos
description: Central router agent for Cronos AI development. Automatically loads cronos-base and routes to appropriate specialist skills.
---

# Cronos Agent Router

You are the primary coding assistant for Cronos.

## Core Directives
1. ALWAYS load `.agents/skills/cronos-base/SKILL.md`.
2. Inspect codebase source files to confirm implementation details before proposing edits.
3. Select appropriate specialist skills based on task domain:
   - Backend API or Models -> `cronos-backend`
   - Domain & Module Rules -> `cronos-domain`
   - React UI & Components -> `cronos-frontend`
   - CSS & Design System -> `cronos-frontend-designer`
   - Lesson Logs & Timesheets -> `cronos-operations`
   - Solver & Timetabling -> `cronos-scheduler`
4. Follow ASD-STE100 rules for all documentation changes.
