/**
 * Deterministic color palette for subjects.
 * Shared between WeekGrid.jsx (cell backgrounds) and Schedules.jsx (KPI sidebar).
 * Using subject ID modulo ensures the same subject always gets the same color,
 * regardless of list order or which component renders first.
 */
export const SUBJECT_COLORS = [
  '#4b2e19', // Deep Brown (Brand Primary)
  '#164a39', // Forest Green (Brand Success)
  '#d4af37', // Gold (Brand Accent)
  '#be5103', // Burnt Orange
  '#a97142', // Medium Brown (Brand Info)
  '#8ba88e', // Warm Sage
  '#b7410e', // Deep Terracotta
  '#c4a882', // Sandy Taupe
  '#8a7060', // Muted Brown
  '#5c3f2b', // Espresso
]

/** Returns a deterministic hex color for a subject ID. */
export function getSubjectColor(subjectId) {
  return SUBJECT_COLORS[subjectId % SUBJECT_COLORS.length]
}
