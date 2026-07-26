# Accessibility

## Purpose
This document specifies accessibility requirements, WCAG color contrast targets, ARIA attribute rules, and keyboard navigation standards.

## Intended Reader
This document targets frontend developers and QA engineers.

## Prerequisites
Read [Design System](DESIGN_SYSTEM.md).

## What the System Does
Cronos enforces Web Content Accessibility Guidelines (WCAG 2.1 Level AA) compliance across all user interfaces.

## Contrast Rules and Targets
- **Normal Text**: Contrast ratio must exceed **4.5:1** against underlying background surface.
- **Large Text & Headings**: Contrast ratio must exceed **3.0:1**.
- **Interactive UI Components**: Buttons, inputs, and focus rings must maintain **3.0:1** contrast against adjacent surfaces.

## Accessibility Implementation Standards

| Element Type | Accessibility Rule | Implementation Pattern |
| :--- | :--- | :--- |
| **Interactive Modals** | Focus trap & Escape key closing | `GenericModalForm.jsx` handles focus trap and `KeyDown` |
| **Data Tables** | Semantic header cells | `SmartTable.jsx` uses `<th>` headers with `scope="col"` |
| **Icon Buttons** | Screen reader labels | Buttons contain `aria-label` attributes |
| **Form Fields** | Explicit label association | `<label htmlFor="id">` linked to matching input `id` |
| **Schedule Grid** | Keyboard focusable slots | Interactive grid cells support `tabIndex={0}` |

## Failure Modes
- Low Contrast Detection: Automated CI audits flag color pairings failing WCAG AA threshold.

## Verification Procedure
Inspect accessibility audit baseline at `documentation/06_frontend_ux/ACCESSIBILITY_REPORT.md` (historical reference) and run browser Lighthouse accessibility audit.

## Source Map
- Component Components: `frontend/src/components/SmartTable.jsx`, `frontend/src/components/GenericModalForm.jsx`

## Related Documents
- [Design System](DESIGN_SYSTEM.md)
