# Design System

## Purpose
This document specifies the Cronos visual design system, color palette tokens, typography rules, and component patterns.

## Intended Reader
This document targets UI designers and frontend engineers.

## Prerequisites
Read [Frontend Architecture](FRONTEND_ARCHITECTURE.md).

## Aesthetic Foundation: The 60-30-10 Color Rule
Cronos employs a warm, authoritative visual identity designed for educational trust and operational clarity:
- **60% Dominant Base Surfaces**: Warm light yellow, `#fef9e7`.
- **30% Structural Navigation**: Deep brown, `#3B2415`.
- **10% Action Accents**: Amber gold, `#d4940b`.

`frontend/src/index.css` defines these values (`--brand-50`, `--brand-950`, `--brand-500`). `frontend/src/styles/brand.tokens.css` defines the `--cronos-*` tokens and their aliases.

## Color Palette Tokens Table

| Token Name | Hex Value | Usage Purpose |
| :--- | :--- | :--- |
| `--cronos-bg` | `#faf8f5` | Main application background |
| `--cronos-surface` | `#fffdf9` | Cards and table headers |
| `--cronos-ink` | `#3d2b1f` | Primary controls and headings |
| `--cronos-ink-muted` | `#67584c` | Muted text and secondary elements |
| `--brand-500` | `#d4940b` | Calls to action and active states |
| `--cronos-success` | `#23634f` | Toast success icon |
| `--cronos-danger` | `#8f2d0b` | Toast error icon |
| `--rs-teal` | `#15803d` | Success and completed states (`index.css`) |
| `--rs-deep` | `#b91c1c` | Error and gap states (`index.css`) |

## Typography Pairings
- **Headings**: `Playfair Display` (Editorial Serif, authoritative tone).
- **Body & UI Controls**: `IBM Plex Sans` (clear operational text and controls).

## Marketing Landing Page Aesthetics & Performance
- **CSS Namespace**: Marketing components use the `.cronos-marketing` root and `cronos-*` classes.
- **Asset Standards**: Image graphics must use `<picture>` elements with WebP formats (`.webp`), fallback PNG/JPG formats, explicit width/height parameters, and `decoding="async"`.
- **Motion & Hardware Acceleration**: Continuous CSS marquees must use GPU compositing transforms (`translate3d`), pause on hover, and respect `@media (prefers-reduced-motion: reduce)`.
- **Layer Isolation**: Fixed elements with backdrop blur (`.cronos-header`) use composite layer isolation (`isolation: isolate; contain: layout style;`).

## Feedback Components
- Transient toasts use the `--cronos-font-body` font, the `--cronos-surface` background, and the `--cronos-ink` text.
- Toast icons use the `--cronos-success` and `--cronos-danger` semantic tokens.
- Contextual warnings and business blocks use `FeedbackBanner` without a filled box or lateral border.
- The banner shows a decorative icon, readable text, and an optional adjacent action.

## Contracts and Invariants

- Use compact rows for related settings and import resources. Separate rows with a divider instead of repeated cards.
- Keep essential controls visible. Put longer instructions and impact explanations inside native `details` elements.
- Keep disclosure summaries keyboard accessible and preserve visible focus indicators.
- Dashboard lists show a compact overview. Users can expand class progress or conflict details without losing access to entries.
- The team table has one edit entry per member. The editor groups profile, availability and permitted access actions.
- Room forms create and select room types in context. Existing type management returns to the same room draft.
- Primary actions use the shared primary button theme, including activation. Contextual edit actions use the outlined primary variant.
- Cancellation retains its secondary variant. Primary button selection, hover and keyboard focus use Cronos colors.
- Bulk selection uses the shared checkbox, including its partial-selection state and keyboard focus. Selection actions appear only when records are selected, remain accessible while scrolling and clear back to the list's keyboard focus.
- Destructive controls use the shared danger theme. Bulk confirmation lists the selected records, keeps removal impacts visible and names the action explicitly.
- Place reset and save actions at the lower right, with the primary save action last.
- Course classes and class assignments use divided rows. Teacher progress and class module progress use native compact disclosures.
- Progress editing exposes module controls automatically. Optional proposal analysis starts closed; required warnings and approval controls remain visible.
- Weekly review uses selectable teacher rows with `aria-pressed`; filters keep their visible label associations.
- Authenticated application tokens live in `frontend/src/index.css`.
- Canonical shared tokens live in `frontend/src/styles/brand.tokens.css`.
- Marketing-specific tokens live in `frontend/src/features/marketing/styles/`.
- `index.css` defines `--color-state-*` tokens (with `-bg` variants) for given, gap, substituted, and open states.
- JSX can use inline layout styles, but colors should reference CSS variables.
- Date fields keep help text outside the calendar control and associate it through `aria-describedby`.

## Verification Procedure
Run `npm run lint` and `npm run test` inside `frontend/`, then review the changed screens in a browser at 375, 768, and 1440 px.

## Source Map
- Global CSS Tokens: `frontend/src/index.css`
- Marketing Styles: `frontend/src/features/marketing/styles/`
- Marketing Components: `frontend/src/features/marketing/components/`
- Marketing Pages: `frontend/src/pages/marketing/`
- Route Metadata: `frontend/src/features/marketing/content/metadata.js`

## Related Documents
- [Frontend Architecture](FRONTEND_ARCHITECTURE.md)
- [Accessibility](ACCESSIBILITY.md)
