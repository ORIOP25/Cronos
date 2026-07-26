# Design System

## Purpose
This document specifies the Cronos visual design system, color palette tokens, typography rules, component patterns, and visual baseline standards.

## Intended Reader
This document targets UI designers and frontend engineers.

## Prerequisites
Read [Frontend Architecture](FRONTEND_ARCHITECTURE.md).

## Aesthetic Foundation: The 60-30-10 Color Rule
Cronos employs a warm, authoritative visual identity designed for educational trust and operational clarity:
- **60% Dominant Base Surfaces**: Warm White (`#faf8f5`, `#ffffff`).
- **30% Structural Navigation**: Deep Brown (`#3d2b1f`, `#2a1a0f`).
- **10% Action Accents**: Amber Gold (`#d4940b`, `#f0b429`).

## Color Palette Tokens Table

| Token Name | Hex Value | Usage Purpose |
| :--- | :--- | :--- |
| `surface` | `#faf8f5` | Main application background surface |
| `surface-bright` | `#ffffff` | Card containers and input background |
| `primary` | `#5c3d2e` | Primary buttons and key structural elements |
| `secondary` | `#8b6f5c` | Subdued text and secondary outlines |
| `tertiary` | `#d4940b` | Accent highlights, active tabs, warning callouts |
| `sidebar-bg-start` | `#3d2b1f` | Navigation sidebar background top gradient |
| `sidebar-bg-end` | `#2a1a0f` | Navigation sidebar background bottom gradient |
| `success` | `#15803d` | Approved statuses, completed lesson logs |
| `error` | `#b91c1c` | Error alerts, gap indicators, destructive actions |

## Typography Pairings
- **Headings**: `Playfair Display` (Editorial Serif, authoritative tone).
- **Body & UI Controls**: `Outfit` (Clean Geometric Sans-Serif, maximum legibility).

## Visual Evidence Baseline Standards
The repository maintains visual snapshot baselines under `documentation/06_frontend_ux/visual-baselines/`:
- `css-coverage.json`: CSS execution coverage metrics.
- `login-1440.png`, `marketing-1440.png`: Visual reference screenshots.

*Note: Visual snapshots serve as design review evidence and baseline references.*

## Contracts and Invariants
- All application styling must reference global CSS custom properties defined in `frontend/src/index.css`.
- Do not introduce inline color hex values in React component files.

## Verification Procedure
Run CSS coverage audit script: `node frontend/scripts/capture-css-coverage.mjs`.

## Source Map
- Global CSS Tokens: `frontend/src/index.css`
- Marketing Styles: `frontend/src/pages/MarketingSite.css`
- Visual Baseline Dir: `documentation/06_frontend_ux/visual-baselines/`

## Related Documents
- [Frontend Architecture](FRONTEND_ARCHITECTURE.md)
- [Accessibility](ACCESSIBILITY.md)
