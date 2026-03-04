/**
 * Deterministic color palette for subjects.
 * Shared between WeekGrid.jsx (cell backgrounds) and Schedules.jsx (KPI sidebar).
 * Using subject ID modulo ensures the same subject always gets the same color,
 * regardless of list order or which component renders first.
 */
export const SUBJECT_COLORS = [
  '#4e79a7', '#f28e2b', '#e15759', '#76b7b2',
  '#59a14f', '#edc948', '#b07aa1', '#ff9da7',
  '#9c755f', '#bab0ac',
]

/** Returns a deterministic hex color for a subject ID. */
export function getSubjectColor(subjectId) {
  return SUBJECT_COLORS[subjectId % SUBJECT_COLORS.length]
}
