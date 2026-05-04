/**
 * Deterministic color palette for subjects.
 * Shared between WeekGrid.jsx (cell backgrounds) and Schedules.jsx (KPI sidebar).
 * Using subject ID modulo ensures the same subject always gets the same color,
 * regardless of list order or which component renders first.
 */
export const SUBJECT_COLORS = [
  '#5c3d2e', // Brown Medium (Brand Primary)
  '#15803d', // Green (Success)
  '#2563eb', // Blue (Info)
  '#d4940b', // Amber Yellow (Accent)
  '#9333ea', // Purple
  '#0891b2', // Cyan
  '#c2410c', // Burnt Orange
  '#4f46e5', // Indigo
  '#0d9488', // Teal
  '#be185d', // Deep Pink
]

/** Returns a deterministic hex color for a subject ID. */
export function getSubjectColor(subjectId) {
  return SUBJECT_COLORS[subjectId % SUBJECT_COLORS.length]
}
