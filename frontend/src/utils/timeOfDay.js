const TIME_PATTERN = /^(\d{1,2}):(\d{2})(?::00)?$/

export function parseTimeOfDay(value) {
  if (typeof value !== 'string') return null
  const match = TIME_PATTERN.exec(value.trim())
  if (!match) return null
  const hours = Number(match[1])
  const minutes = Number(match[2])
  if (hours > 23 || minutes > 59) return null
  return { hours, minutes }
}

export function normalizeTimeOfDay(value) {
  const parsed = parseTimeOfDay(value)
  if (!parsed) return null
  return `${String(parsed.hours).padStart(2, '0')}:${String(parsed.minutes).padStart(2, '0')}`
}

export function formatTimeOfDay(value) {
  const parsed = parseTimeOfDay(value)
  if (!parsed) return typeof value === 'string' ? value.trim() : ''
  return `${parsed.hours}:${String(parsed.minutes).padStart(2, '0')}`
}

export function timeOfDayToMinutes(value) {
  const parsed = parseTimeOfDay(value)
  if (!parsed) return NaN
  return parsed.hours * 60 + parsed.minutes
}
