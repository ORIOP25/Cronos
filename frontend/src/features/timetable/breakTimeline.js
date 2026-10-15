import { timeOfDayToMinutes } from '../../utils/timeOfDay'

function minutesToTime(totalMinutes) {
  const hours = Math.floor(totalMinutes / 60)
  const mins = totalMinutes % 60
  return `${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}`
}

function splitBreakOverrides(raw) {
  const valid = []
  const rejected = []
  const seen = new Set()
  for (const entry of Array.isArray(raw) ? raw : []) {
    const afterSlot = Number(entry?.after_slot)
    const durationMinutes = Number(entry?.duration_minutes)
    const shaped = { after_slot: afterSlot, duration_minutes: durationMinutes }
    if (!Number.isInteger(afterSlot) || afterSlot < 1) {
      rejected.push({ ...shaped, reason: 'position' })
      continue
    }
    if (seen.has(afterSlot)) {
      rejected.push({ ...shaped, reason: 'duplicate' })
      continue
    }
    if (!Number.isInteger(durationMinutes) || durationMinutes < 0 || durationMinutes > 60) {
      rejected.push({ ...shaped, reason: 'duration' })
      continue
    }
    seen.add(afterSlot)
    valid.push({ after_slot: afterSlot, duration_minutes: durationMinutes })
  }
  return { valid, rejected }
}

export function normalizeBreakOverrides(raw) {
  return splitBreakOverrides(raw).valid
}

export function setBreakOverride(raw, afterSlot, durationMinutes, usualBreak) {
  const next = (Array.isArray(raw) ? raw : []).filter(
    (entry) => Number(entry?.after_slot) !== afterSlot,
  )
  if (durationMinutes !== usualBreak) {
    next.push({ after_slot: afterSlot, duration_minutes: durationMinutes })
  }
  next.sort((a, b) => Number(a?.after_slot) - Number(b?.after_slot))
  return next
}

export function removeBreakOverride(raw, afterSlot) {
  return (Array.isArray(raw) ? raw : []).filter(
    (entry) => Number(entry?.after_slot) !== afterSlot,
  )
}

export function buildDailyTimeline(values) {
  const openMin = timeOfDayToMinutes(values.opening_time)
  const closeMin = timeOfDayToMinutes(values.closing_time)
  const slotDur = values.slot_duration_minutes == null ? 60 : Number(values.slot_duration_minutes)
  const breakDur = values.break_duration_minutes == null ? 5 : Number(values.break_duration_minutes)

  if (
    Number.isNaN(openMin) ||
    Number.isNaN(closeMin) ||
    closeMin <= openMin ||
    !Number.isInteger(slotDur) ||
    !Number.isInteger(breakDur) ||
    slotDur < 15 ||
    slotDur > 120 ||
    breakDur < 0 ||
    breakDur > 60
  ) {
    return null
  }

  const { valid, rejected } = splitBreakOverrides(values.break_overrides)
  const overrideByPosition = new Map(
    valid.map((override) => [override.after_slot, override.duration_minutes]),
  )

  const slots = []
  let cur = openMin
  let slotIndex = 1

  while (cur + slotDur <= closeMin) {
    const slotEnd = cur + slotDur
    const breakAfter = overrideByPosition.has(slotIndex)
      ? overrideByPosition.get(slotIndex)
      : breakDur

    slots.push({
      id: `${minutesToTime(cur)}-${minutesToTime(slotEnd)}`,
      index: slotIndex++,
      start: minutesToTime(cur),
      end: minutesToTime(slotEnd),
      breakAfter,
    })

    cur = slotEnd + breakAfter
  }

  if (slots.length > 0) {
    slots[slots.length - 1] = { ...slots[slots.length - 1], breakAfter: 0 }
  }

  const unusedOverrides = [...overrideByPosition.keys()]
    .filter((position) => position >= slots.length)
    .sort((a, b) => a - b)

  return { slots, unusedOverrides, invalidOverrides: rejected }
}

export function validateBreakOverrides(values) {
  const { valid: overrides, rejected } = splitBreakOverrides(values.break_overrides)

  if (rejected.length > 0) {
    const first = rejected[0]
    if (first.reason === 'position') {
      return 'Cada ajuste deve indicar a aula após a qual ocorre a pausa (a primeira aula é 1).'
    }
    if (first.reason === 'duplicate') {
      return `Existe mais de um ajuste para a aula ${first.after_slot}.`
    }
    return 'Cada ajuste de intervalo deve ter entre 0 e 60 minutos.'
  }

  if (overrides.length > 0) {
    const timeline = buildDailyTimeline(values)
    if (timeline && timeline.unusedOverrides.length > 0) {
      return `O ajuste de intervalo após a aula ${timeline.unusedOverrides[0]} não tem aula seguinte na grelha resultante.`
    }
  }

  return ''
}
