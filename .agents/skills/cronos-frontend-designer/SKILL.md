---
name: cronos-frontend-designer
description: Specialist UI design system skill for Cronos. Use when editing CSS styles, page layouts, component tokens, or visual branding.
argument-hint: Requires cronos-base.
---

# Cronos Frontend Designer Skill

> ⚠️ **IMPORTANT**: Load `.agents/skills/cronos-base/SKILL.md` before using this skill.

You are the UI designer for Cronos.

## Design Token Rules
- **60-30-10 Color Rule**: 60% warm light yellow (`#fef9e7`), 30% deep brown (`#3B2415`), 10% amber gold (`#d4940b`).
- **Typography**: Headings use `Playfair Display`. Body text uses `IBM Plex Sans`.
- **CSS Variables**: Use shared properties from `frontend/src/styles/brand.tokens.css` and `frontend/src/index.css`. Marketing tokens live in `frontend/src/features/marketing/styles/`.
- **Marketing Isolation**: Marketing site styles use the `.cronos-marketing` root and `cronos-*` class namespace.

## Relevant Documentation
- [Design System](../../../documentation/06_frontend_ux/DESIGN_SYSTEM.md)
- [Accessibility](../../../documentation/06_frontend_ux/ACCESSIBILITY.md)
