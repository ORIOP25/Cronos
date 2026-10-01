# Accessibility

## Purpose
This document specifies accessibility requirements, WCAG color contrast targets, ARIA attribute rules, and keyboard navigation standards.

## Intended Reader
This document targets frontend developers and QA engineers.

## Prerequisites
Read [Design System](DESIGN_SYSTEM.md).

## What the System Does
Cronos implements accessibility patterns but does not claim repository-wide WCAG certification.
The repository does not run an automated full-page WCAG audit in CI.

## Contrast Rules and Targets
- **Normal Text**: Contrast ratio must exceed **4.5:1** against underlying background surface.
- **Large Text & Headings**: Contrast ratio must exceed **3.0:1**.
- **Interactive UI Components**: Buttons, inputs, and focus rings must maintain **3.0:1** contrast against adjacent surfaces.

## Accessibility Implementation Standards

| Element Type | Accessibility Rule | Implementation Pattern |
| :--- | :--- | :--- |
| **Interactive Modals** | Focus management and Escape behavior | CoreUI `CModal` supplies dialog behavior |
| **Data Tables** | Semantic header cells and keyboard rows | `SmartTable.jsx` uses `<th>` and Enter/Space activation |
| **Icon Buttons** | Screen reader labels | Buttons contain `aria-label` attributes |
| **Form Fields** | Explicit label association | `<label htmlFor="id">` linked to matching input `id` |
| **Schedule Grid** | Native interactive controls | `WeekGrid.jsx` places actionable content in buttons |
| **Keyboard rows** | Enter and Space activation | `SmartTable.jsx` handles keyboard activation for clickable rows |
| **Live feedback** | Errors alert immediately. Other feedback announces politely. | `FeedbackBanner.jsx` uses `role="alert"` or `role="status"`. |
| **Availability grid** | Only one cell is in the normal tab order. Arrows move between available cells. | `AvailabilityGrid.jsx` uses roving `tabIndex`. |
| **Scrollable grids** | Grid scrolling stays inside a labelled focusable region. | `WeekGrid.jsx` and `AvailabilityGrid.jsx` use contained scroll regions. |
| **Landmarks** | Content sits in labelled semantic regions. | The layout uses `main`, `nav`, and labelled regions. |
| **Current page** | The active breadcrumb is announced. | `Breadcrumbs.jsx` sets `aria-current="page"`. |
| **Motion** | Reduced-motion preferences remove transitions. | `@media (prefers-reduced-motion: reduce)` in `app-components.css` and `marketing.base.css`. |
| **Target size** | Primary controls approach 44 by 44 pixels. | Sidebar, modal, guided-form, and marketing controls use `44px` minimums. |

## Failure Modes
- Regression Risk: CI runs component tests but no automated full-page WCAG or contrast audit.

## Verification Procedure
Run frontend tests. Then use keyboard-only navigation and a browser accessibility audit on public, admin, and teacher routes.

## Source Map
- Components: `frontend/src/components/SmartTable.jsx`, `frontend/src/components/GenericModalForm.jsx`, `frontend/src/components/WeekGrid.jsx`

## Related Documents
- [Design System](DESIGN_SYSTEM.md)
