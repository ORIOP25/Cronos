---
name: cronos-frontend-designer
description: Cronos visual design skill. Use when editing CSS, design tokens, page layouts, visual branding, or the marketing site styles.
---

# Cronos Frontend Designer

Load `cronos-base`, `ponytail`, and `cronos-frontend` first.

## Start here

- Brand tokens: `frontend/src/styles/brand.tokens.css`.
- Application styles: `frontend/src/index.css` and `frontend/src/styles/`.
- Marketing styles: `frontend/src/features/marketing/styles/` and `frontend/src/pages/MarketingSite.css`.

## Rules

- Read the [Design System](../../../documentation/06_frontend_ux/DESIGN_SYSTEM.md) and inspect a comparable screen before styling. Prefer established web-app patterns adapted to Cronos.
- Preserve the warm neutral surfaces, brown structure and amber accents. Resolve current colors through the canonical tokens, not historical hex values.
- Use the display font for page titles and the body font for controls. Preserve the existing component typography for section and modal headings.
- Use existing CSS custom properties. Do not hard-code colors or add a CSS framework.
- Equivalent actions share their button variant, icon, text scale and interaction states. Follow the action and icon conventions in the Design System.
- Reuse the shared control sizes, row spacing and action gaps. Do not add isolated size or spacing overrides for an equivalent control.
- Keep cancellation secondary and distinct from saving. Keep semantic colors for operational states and destructive actions.
- Use one compact `PageHeader` per page. Keep divided rows, contextual selection actions and progressive disclosure consistent with existing screens.
- Put reset/cancel before save and keep final form actions at the lower right. Keep required information and accessible focus visible.
- Adjust dense grids or other specialized views only when their context requires it. Preserve meaning and usability instead of forcing identical layouts.
- Marketing styles stay under the `.cronos-marketing` root and the `cronos-*` class namespace.
- Keep contrast, focus states, and keyboard navigation from the [Accessibility](../../../documentation/06_frontend_ux/ACCESSIBILITY.md) guide.

## Pitfalls

- Search the existing selector and its callers before adding an override. Prefer fixing the shared component or token over repeating page-level fixes.
- Marketing pages are also pre-rendered at build time. Check them with `npm run build` and `npm run test:marketing-assets` in `frontend/`.

## Done when

- `npm run verify:checks` passes in `frontend/`.
- The local stack is rebuilt from the worktree that holds the change, and the changed screens are checked in the browser.
  See [Local stack in a worktree](../../../documentation/00_getting_started/COMMAND_REFERENCE.md#local-stack-in-a-worktree).
- The [Design System](../../../documentation/06_frontend_ux/DESIGN_SYSTEM.md) reflects any new token or pattern.

## Documentation

- [Design System](../../../documentation/06_frontend_ux/DESIGN_SYSTEM.md)
- [Accessibility](../../../documentation/06_frontend_ux/ACCESSIBILITY.md)
