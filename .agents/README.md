# Cronos AI Agent Suite

This directory holds the agent skills for Cronos. [AGENTS.md](../AGENTS.md) defines when to load them.

## Layout

- `.agents/skills/<name>/SKILL.md` is the source of every skill. Codex and other agents read it here.
- `.claude/skills/<name>/SKILL.md` is a thin adapter so Claude Code discovers the same skill. It repeats the source frontmatter and points to the source.
  When you change a skill `name` or `description`, update its adapter in the same commit.

## Cronos Skills

| Skill | Trigger | Primary scope |
| :--- | :--- | :--- |
| [`cronos-base`](skills/cronos-base/SKILL.md) | Every task | Shared checklist and safety rules |
| [`cronos-backend`](skills/cronos-backend/SKILL.md) | API, services, models, migrations, backend Clerk | `backend/app/`, `backend/tests/` |
| [`cronos-domain`](skills/cronos-domain/SKILL.md) | Ensino Profissional rules, catalog, members, school configuration | `documentation/02_domain_model/` |
| [`cronos-frontend`](skills/cronos-frontend/SKILL.md) | React pages, hooks, routes, Clerk UI | `frontend/src/` |
| [`cronos-frontend-designer`](skills/cronos-frontend-designer/SKILL.md) | CSS, tokens, visual design | `frontend/src/styles/`, `frontend/src/index.css` |
| [`cronos-operations`](skills/cronos-operations/SKILL.md) | Sumários, Faltas, substitutions, timesheets, debt | `documentation/04_operational_features/` |
| [`cronos-scheduler`](skills/cronos-scheduler/SKILL.md) | CP-SAT solver, jobs, proposals | `backend/app/scheduler/` |
| [`cronos-infra`](skills/cronos-infra/SKILL.md) | Docker, CI, delivery, Railway, Cloudflare, Clerk dashboard, mail | `.github/`, `scripts/`, `docker-compose*.yml`, `backend/railway/` |

`ponytail` is required for every task. Git tracks it with the Cronos skills.

## Imported Skills

Imported skills are protected. Do not modify them.
Git ignores every imported skill except `ponytail`, so a clean clone does not contain them.

`skills-lock.json` lists the Clerk skills from the GitHub source `clerk/skills`, with the path and hash of each.
Cronos uses React with React Router, a Python backend, organizations, webhooks, and Clerk test users.
Install this subset for Cronos work:

| Skill | Why |
| :--- | :--- |
| `clerk` | Core Clerk concepts |
| `clerk-setup` | Keys, instances, environment variables |
| `clerk-react-patterns` | `@clerk/react` hooks and components |
| `clerk-react-router-patterns` | Routing with React Router |
| `clerk-custom-ui` | Customized sign-in and sign-up screens |
| `clerk-orgs` | Organizations, roles, invitations |
| `clerk-webhooks` | Svix-signed membership webhooks |
| `clerk-backend-api` | Backend API calls from `backend/app/services/clerk_access_service.py` |
| `clerk-testing` | Clerk test users for E2E |

The other lockfile entries (mobile, Next.js, Nuxt, Vue, Astro, TanStack, Chrome extension, billing) do not apply to Cronos.

To install a skill, copy the directory named by its `skillPath` in `clerk/skills` to `.agents/skills/<name>/`.
Compare its `SKILL.md` with the `computedHash` in `skills-lock.json` before you rely on it.
The optional local skills `grill-me` and `design-taste-frontend` are not in the lockfile.
