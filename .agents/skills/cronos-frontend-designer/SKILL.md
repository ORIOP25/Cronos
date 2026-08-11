---
name: cronos-frontend-designer
description: Specialist UI design system skill for Cronos. Use when editing CSS styles, page layouts, component tokens, or visual branding.
argument-hint: Requires cronos-base.
---

# Cronos Frontend Designer Skill

> ⚠️ **IMPORTANT**: Load `.agents/skills/cronos-base/SKILL.md` before using this skill.

You are the UI designer for Cronos.

## Design Token Rules
- **60-30-10 Color Rule**: 60% Warm White (`#faf8f5`), 30% Deep Brown (`#3d2b1f`), 10% Amber Gold (`#d4940b`).
- **Typography**: Headings use `Playfair Display`. Body text uses `Outfit`.
- **CSS Variables**: Use shared properties from `frontend/src/index.css` and scoped properties from `frontend/src/pages/MarketingSite.css`.
- **Marketing Isolation**: Marketing site styles use the `.cronos-marketing` root and `cronos-*` class namespace.

## Relevant Documentation
- [Design System](../../../documentation/06_frontend_ux/DESIGN_SYSTEM.md)
- [Accessibility](../../../documentation/06_frontend_ux/ACCESSIBILITY.md)
