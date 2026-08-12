# Design System

## Purpose
This document specifies the Cronos visual design system, color palette tokens, typography rules, component patterns, and visual baseline standards.

## Intended Reader
This document targets UI designers and frontend engineers.

## Prerequisites
Read [Frontend Architecture](FRONTEND_ARCHITECTURE.md).

## Aesthetic Foundation: The 60-30-10 Color Rule
Cronos employs a warm, authoritative visual identity designed for educational trust and operational clarity:
- **60% Dominant Base Surfaces**: Warm light surfaces, including `#fef9e7`.
- **30% Structural Navigation**: Deep brown, including `#3b2415`.
- **10% Action Accents**: Amber gold, including `#d4940b`.

## Color Palette Tokens Table

| Token Name | Hex Value | Usage Purpose |
| :--- | :--- | :--- |
| `--brand-50` | `#fef9e7` | Main application background |
| `--brand-100` | `#fffbef` | Cards and table headers |
| `--brand-800` | `#3b2415` | Primary controls and headings |
| `--brand-600` | `#8b6f5c` | Muted text and secondary elements |
| `--brand-500` | `#d4940b` | Calls to action and active states |
| `--rs-teal` | `#15803d` | Success and completed states |
| `--rs-deep` | `#b91c1c` | Error and gap states |

## Typography Pairings
- **Headings**: `Playfair Display` (Editorial Serif, authoritative tone).
- **Body & UI Controls**: `Outfit` (Clean Geometric Sans-Serif, maximum legibility).

## Marketing Landing Page Aesthetics & Performance
- **CSS Namespace**: Marketing components use the `.cronos-marketing` root and `cronos-*` classes.
- **Asset Standards**: Image graphics must use `<picture>` elements with WebP formats (`.webp`), fallback PNG/JPG formats, explicit width/height parameters, and `decoding="async"`.
- **Motion & Hardware Acceleration**: Continuous CSS marquees must use GPU compositing transforms (`translate3d`), pause on hover, and respect `@media (prefers-reduced-motion: reduce)`.
- **Layer Isolation**: Fixed elements with backdrop blur (`.cronos-header`) use composite layer isolation (`isolation: isolate; contain: layout style;`).

## Visual Evidence Baseline Standards
The repository maintains visual snapshot baselines under `documentation/06_frontend_ux/visual-baselines/`:
- `css-coverage.json`: CSS execution coverage metrics.
- `login-1440.png`, `marketing-1440.png`: Visual reference screenshots.

*Note: Visual snapshots serve as design review evidence and baseline references.*

## Contracts and Invariants
- Authenticated application tokens live in `frontend/src/index.css`.
- Marketing-specific tokens live in `frontend/src/features/marketing/styles/`.
- The implementation contains semantic state tokens for given, gap, substituted, and open states.
- JSX can use inline layout styles, but colors should reference CSS variables.

## Verification Procedure
Run CSS coverage audit script: `node frontend/scripts/capture-css-coverage.mjs`.

## Source Map
- Global CSS Tokens: `frontend/src/index.css`
- Marketing Styles: `frontend/src/features/marketing/styles/`
- Marketing Components: `frontend/src/features/marketing/components/`
- Marketing Pages: `frontend/src/pages/marketing/`
- Route Metadata: `frontend/src/features/marketing/content/metadata.js`
- Visual Baseline Dir: `documentation/06_frontend_ux/visual-baselines/`

## Related Documents
- [Frontend Architecture](FRONTEND_ARCHITECTURE.md)
- [Accessibility](ACCESSIBILITY.md)
