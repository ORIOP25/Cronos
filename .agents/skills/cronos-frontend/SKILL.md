---
name: cronos-frontend
description: Specialist frontend development skill for Cronos. Use when working on React 19 pages, Vite build scripts, React Query data hooks, Clerk auth flows, or UI components.
argument-hint: Requires cronos-base.
---

# Cronos Frontend Skill

> ⚠️ **IMPORTANT**: Load `.agents/skills/cronos-base/SKILL.md` before using this skill.

You are the frontend developer for Cronos.

## Domain Guidelines
- **Framework**: React 19, Vite 8, React Router, CoreUI, TanStack React Query.
- **Authentication**: Use `@clerk/react` hooks and attach an organization-scoped Bearer JWT through `apiClient`.
- **Role Access**: Enforce `RequireAdmin` and `RequireTeacher` guards from `frontend/src/routeGuards.jsx`.

## Verification Checklist
- Run `npm run audit:production` inside `frontend/`.
- Run `npm run verify` inside `frontend/`.

## Relevant Documentation
- [Frontend Architecture](../../../documentation/06_frontend_ux/FRONTEND_ARCHITECTURE.md)
- [Routes and Permissions](../../../documentation/06_frontend_ux/ROUTES_AND_PERMISSIONS.md)
