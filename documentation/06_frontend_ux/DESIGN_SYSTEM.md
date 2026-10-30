# Design System

## Purpose
This document specifies the Cronos visual design system, color palette tokens, typography rules, and component patterns.

## Intended Reader
This document targets UI designers and frontend engineers.

## Prerequisites
Read [Frontend Architecture](FRONTEND_ARCHITECTURE.md).

## Aesthetic Foundation: The 60-30-10 Color Rule
Use warm neutral surfaces, deep brown structure and restrained amber accents.
Treat the ratio as visual hierarchy, not a reason to recolor semantic states.
The [canonical tokens](../../frontend/src/styles/brand.tokens.css) own current colors, aliases, text scales and control dimensions.
The [application styles](../../frontend/src/index.css) own CoreUI themes and operational state colors.
Do not restore historical hex values or copy token values into page-specific styles.

## Typography Pairings
- **Headings**: `Playfair Display` (Editorial Serif, authoritative tone).
- **Body & UI Controls**: `IBM Plex Sans` (clear operational text and controls).
Page titles use the display font. Section and modal headings follow their shared component styles.
Equivalent text roles use the shared scale; titles and supporting text retain distinct hierarchy.

## Choosing an Application Pattern

Inspect a comparable screen before adding a new layout or control.
Reuse established web-app patterns through the existing Cronos components and tokens.
Fix an inconsistency in the shared component when equivalent screens have the same problem.
Avoid page-specific colors, sizes, spacing or icons for an equivalent action.
Keep specialized grids and operational states distinct when their meaning requires it.

## Application Copy

Follow the [copy contract](FRONTEND_ARCHITECTURE.md#contracts-and-invariants) and reuse [shared terminology](../../frontend/src/utils/terminology.js).
Use the same label, icon and variant for the same action.
Distinguish opening a creation form from creating a record, and saving edits from applying a local draft.
Keep removal, archival and restoration distinct, including their impact warnings.
Use the same terms in visible labels, tooltips, accessible names, confirmations, help text and tutorial instructions.

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
- Dashboard lists show a compact overview. Users can expand class progress without losing access to entries.
- The team table has one edit entry per member. The editor groups profile, availability and permitted access actions.
- Room forms create and select room types in context. Existing type management returns to the same room draft.
- Primary actions use the shared primary button theme, including activation. Contextual edit actions use the outlined primary variant.
- Cancellation retains its secondary variant. Primary button selection, hover and keyboard focus use Cronos colors.
- Use outlined secondary buttons for cancellation, back navigation and reset; outlined primary buttons for contextual editing; ghost primary buttons for edit icons in rows. Keep cancel before save. Approval and import confirmation use the primary action theme. Operational state choices retain their semantic colors.
- Application control sizes, body and supporting text scales, row spacing and action gaps use the shared tokens in `frontend/src/styles/brand.tokens.css` and the scoped rules in `frontend/src/styles/app-components.css`. Compact CoreUI button variants retain the same readable text and minimum target size. Marketing keeps its own hierarchy.
- Use CoreUI `cilPencil` for editing, `cilTrash` for removal, `cilPlus` for adding records, `cilSave` for saving, `cilCheckCircle` for approval or completion, and `cilArrowLeft`/`cilArrowRight` for directional navigation. Action icons share the same size. Keep table actions visible without hovering.
- Bulk selection uses the shared checkbox, including its partial-selection state and keyboard focus. Selection actions appear only when records are selected and stay visible while scrolling. Clearing the selection returns keyboard focus to the list.
- Destructive controls use the shared danger theme. Bulk confirmation lists the selected records, keeps removal impacts visible and names the action explicitly.
- Place reset and save actions at the lower right, with the primary save action last.
- Course classes and class assignments use divided rows. Teacher progress and class module progress use native compact disclosures.
- Progress editing exposes module controls automatically. Optional proposal analysis starts closed; required warnings and approval controls remain visible.
- Weekly review uses selectable teacher rows with `aria-pressed`; filters keep their visible label associations.
- Every application page opens with `PageHeader`: one compact `h1` with the page name, shown beside the school selector on desktop. The sidebar already names the section, so the header has no section label. Page actions sit in a toolbar below the title, aligned to the right.
- Authenticated application tokens live in `frontend/src/index.css`.
- Canonical shared tokens live in `frontend/src/styles/brand.tokens.css`.
- Marketing-specific tokens live in `frontend/src/features/marketing/styles/`.
- `index.css` defines `--color-state-*` tokens (with `-bg` variants) for given, gap, substituted, and open states.
- JSX can use inline layout styles, but colors should reference CSS variables.
- Date fields keep help text outside the calendar control and associate it through `aria-describedby`.

## Verification Procedure
Run `npm run lint` and `npm run test` inside `frontend/`, then review the changed screens in a browser at 375, 768, and 1440 px.

## Source Map
- [Canonical tokens](../../frontend/src/styles/brand.tokens.css)
- [Shared application controls and spacing](../../frontend/src/styles/app-components.css)
- [Page header](../../frontend/src/components/PageHeader.jsx)
- [Shared terminology](../../frontend/src/utils/terminology.js)
- Global CSS Tokens: `frontend/src/index.css`
- Marketing Styles: `frontend/src/features/marketing/styles/`
- Marketing Components: `frontend/src/features/marketing/components/`
- Marketing Pages: `frontend/src/pages/marketing/`
- Route Metadata: `frontend/src/features/marketing/content/metadata.js`

## Related Documents
- [Frontend Architecture](FRONTEND_ARCHITECTURE.md)
- [Accessibility](ACCESSIBILITY.md)
