export function getWeekSubmissionBlockers(slots, now = new Date()) {
  return slots.flatMap((slot) => {
    const reasons = []
    if (slot.date && slot.timeslot?.end_time) {
      const endDateTime = new Date(`${slot.date}T${slot.timeslot.end_time}`)
      if (endDateTime > now) reasons.push('aula futura')
    } else if (!slot.is_past) {
      reasons.push('aula futura')
    }

    const hasLessonLog = ['COMPLETED', 'OCCURRENCE'].includes(slot.lesson_log_status)
    if (!hasLessonLog && slot.occurrence_status == null) reasons.push('não registada')
    if (reasons.length === 0) return []

    const day = slot.date
      ? new Date(`${slot.date}T12:00:00`).toLocaleDateString('pt-PT', {
          weekday: 'short',
          day: 'numeric',
          month: 'short',
        })
      : '?'
    return [`${day} — ${slot.subject?.name ?? '?'} (${reasons.join(', ')})`]
  })
}
