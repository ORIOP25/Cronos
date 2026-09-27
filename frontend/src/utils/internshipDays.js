import { addDays } from './formatUtils'

const MAX_FLOW_DAYS = 400

/**
 * Dias da semana em que a turma está em estágio segundo os fluxos do ano atual.
 */
export function collectInternshipDays(events, classId, weekStart, weekEnd) {
  if (!classId || !weekStart || !weekEnd) return []
  const days = new Set()
  for (const event of events) {
    if (event.event_type !== 'internship_flow') continue
    if (event.applies_to_current_school_year === false) continue
    if (!event.class_ids?.includes(classId)) continue
    let current = event.start_date
    let guard = 0
    while (current <= event.end_date && guard < MAX_FLOW_DAYS) {
      if (current >= weekStart && current <= weekEnd) days.add(current)
      current = addDays(current, 1)
      guard += 1
    }
  }
  return [...days]
}
