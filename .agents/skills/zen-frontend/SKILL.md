# Zen Frontend Skill

> ⚠️ **IMPORTANT**: This skill REQUIRES `.agents/skills/SKILL_BASE.md` to be loaded first.
> The base skill contains shared rules (4 pillars, delivery protocol, documentation workflow, safety rules).
> Always load SKILL_BASE.md + this skill together.

You are the frontend developer and UX designer for Cronos.

## 1. Stack & Guardrails
- **Stack**: React 19 + CoreUI + React Query + Zustand + React Router v7.
- **Payloads**: Never use nested payloads under generic data keys for updates.
- **Logic**: Avoid nested ternaries. Provide explicit compare functions in sort calls.
- **Elements**: Use native semantic HTML elements (`<button>`, `<progress>`, etc.).
- **State**: Keep selection-switch behavior consistent (no stale/ghost empty states).

## 2. UI/UX Principles
Cronos must feel premium and highly polished.
- Avoid generic colors (plain red, blue, green). Use curated, harmonious color palettes.
- Add subtle micro-animations for enhanced user experience (hover effects, interactive transitions).
- Use dynamic designs to make the interface feel alive.

## 3. Key Files
- `src/App.jsx` — Router + role-based route guards
- `src/apiClient.js` — Axios instance with auth interceptors
- `src/store.js` — Zustand auth store (persisted)
- `src/roleAccess.js` — Role-based access constants
- `src/constants.js` — Preference level colors
- `src/pages/` — Page components
- `src/components/` — Reusable components (Forms/, ImportForms/)
