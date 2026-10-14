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

- **60-30-10 color rule**: 60% warm light yellow (`#fef9e7`), 30% deep brown (`#3B2415`), 10% amber gold (`#d4940b`).
- **Typography**: headings use `Playfair Display`; body text uses `IBM Plex Sans`.
- Use existing CSS custom properties. Do not hard-code colors or add a CSS framework.
- Marketing styles stay under the `.cronos-marketing` root and the `cronos-*` class namespace.
- Keep contrast, focus states, and keyboard navigation from the [Accessibility](../../../documentation/06_frontend_ux/ACCESSIBILITY.md) guide.

## Pitfalls

- `frontend/src/index.css` is about 1,300 lines. Search for the selector before you add a new one.
- Marketing pages are also pre-rendered at build time. Check them with `npm run build` and `npm run test:marketing-assets` in `frontend/`.

## Done when

- `npm run verify:checks` passes in `frontend/`.
- The local frontend container is rebuilt with `docker compose up -d --build frontend`, and the changed screens are checked in the browser.
- The [Design System](../../../documentation/06_frontend_ux/DESIGN_SYSTEM.md) reflects any new token or pattern.

## Documentation

- [Design System](../../../documentation/06_frontend_ux/DESIGN_SYSTEM.md)
- [Accessibility](../../../documentation/06_frontend_ux/ACCESSIBILITY.md)
