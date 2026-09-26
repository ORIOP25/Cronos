import { normalizeTimeOfDay, timeOfDayToMinutes } from './timeOfDay'

export function toSchoolSettingsPayload(form) {
  const payload = {
    school_start_date: form.school_start_date || null,
    school_hard_end_date: form.school_hard_end_date || null,
    repair_stability_window_days: form.repair_stability_window_days === '' || form.repair_stability_window_days == null
      ? 0
      : Number.parseInt(form.repair_stability_window_days, 10),
  }
  if (form.automatic_holidays_enabled !== undefined) {
    payload.automatic_holidays_enabled = Boolean(form.automatic_holidays_enabled)
  }
  return payload
}

const DEFAULT_GRID_FORM_DATA = {
  start_time: '08:00',
  end_time: '18:00',
  slot_duration_minutes: 50,
  break_duration_minutes: 10,
  break_overrides: [],
  days: { 0: true, 1: true, 2: true, 3: true, 4: true, 5: false, 6: false },
}

const withSeconds = (value) => {
  const normalized = normalizeTimeOfDay(value)
  return normalized ? `${normalized}:00` : null
}
const minuteOfDay = (value) => {
  const minutes = timeOfDayToMinutes(value)
  if (!Number.isFinite(minutes)) throw new Error('A grelha horária guardada é irregular.')
  return minutes
}

export function toGridTimeslotsPayload(formData) {
  const selectedDays = Object.keys(formData.days)
    .filter((day) => formData.days[day])
    .map((day) => Number.parseInt(day, 10))
  return {
    start_time: withSeconds(formData.start_time),
    end_time: withSeconds(formData.end_time),
    slot_duration_minutes: Number.parseInt(formData.slot_duration_minutes, 10),
    break_duration_minutes: Number.parseInt(formData.break_duration_minutes, 10),
    break_overrides: formData.break_overrides ?? [],
    days_of_week: selectedDays,
  }
}

export function toGridConfigurationPayload({ formData, gridSettings }) {
  return {
    grid_settings: {
      lunch_window_start: gridSettings.lunch_window_start ? withSeconds(gridSettings.lunch_window_start) : null,
      lunch_window_end: gridSettings.lunch_window_end ? withSeconds(gridSettings.lunch_window_end) : null,
      lunch_min_duration_minutes: Number.parseInt(gridSettings.lunch_min_duration_minutes, 10),
    },
    timeslots: toGridTimeslotsPayload(formData),
  }
}

export function gridConfigurationToFormData(configuration) {
  const daysOfWeek = configuration.days_of_week ?? []
  return {
    start_time: normalizeTimeOfDay(configuration.opening_time),
    end_time: normalizeTimeOfDay(configuration.closing_time),
    slot_duration_minutes: configuration.slot_duration_minutes,
    break_duration_minutes: configuration.break_duration_minutes,
    break_overrides: (configuration.break_overrides ?? []).map((override) => ({
      after_slot: override.after_slot,
      duration_minutes: override.duration_minutes,
    })),
    days: Object.fromEntries(
      Array.from({ length: 7 }, (_, day) => [day, daysOfWeek.includes(day)]),
    ),
  }
}

export function timeslotsToGridFormData(timeslots) {
  if (!timeslots?.length) {
    return { ...DEFAULT_GRID_FORM_DATA, days: { ...DEFAULT_GRID_FORM_DATA.days } }
  }

  const byDay = new Map()
  for (const slot of timeslots) {
    if (!Number.isInteger(slot.day_of_week) || slot.day_of_week < 0 || slot.day_of_week > 6) {
      throw new Error('A grelha horária guardada é irregular.')
    }
    const daySlots = byDay.get(slot.day_of_week) || []
    daySlots.push({
      start: normalizeTimeOfDay(slot.start_time),
      end: normalizeTimeOfDay(slot.end_time),
    })
    byDay.set(slot.day_of_week, daySlots)
  }

  for (const daySlots of byDay.values()) {
    daySlots.sort((a, b) => minuteOfDay(a.start) - minuteOfDay(b.start))
  }
  const sequences = [...byDay.values()]
  const expected = JSON.stringify(sequences[0])
  if (sequences.some((sequence) => JSON.stringify(sequence) !== expected)) {
    throw new Error('A grelha horária guardada é irregular e não pode ser editada neste formulário.')
  }

  const durations = new Set()
  for (const slot of sequences[0]) {
    const duration = minuteOfDay(slot.end) - minuteOfDay(slot.start)
    if (duration <= 0) throw new Error('A grelha horária guardada é irregular.')
    durations.add(duration)
  }
  if (durations.size !== 1) {
    throw new Error('A grelha horária guardada é irregular e não pode ser editada neste formulário.')
  }

  const sequence = sequences[0]
  const gaps = sequence
    .slice(1)
    .map((slot, index) => minuteOfDay(slot.start) - minuteOfDay(sequence[index].end))
  if (gaps.some((gap) => gap < 0)) {
    throw new Error('A grelha horária guardada é irregular e não pode ser editada neste formulário.')
  }

  const gapCounts = new Map()
  for (const gap of gaps) {
    gapCounts.set(gap, (gapCounts.get(gap) || 0) + 1)
  }
  let breakDuration = 0
  let mostFrequent = 0
  for (const gap of gaps) {
    const count = gapCounts.get(gap)
    if (count > mostFrequent) {
      breakDuration = gap
      mostFrequent = count
    }
  }
  const breakOverrides = gaps
    .map((gap, index) => ({ after_slot: index + 1, duration_minutes: gap }))
    .filter((override) => override.duration_minutes !== breakDuration)

  return {
    start_time: sequence[0].start,
    end_time: sequence.at(-1).end,
    slot_duration_minutes: [...durations][0],
    break_duration_minutes: breakDuration,
    break_overrides: breakOverrides,
    days: Object.fromEntries(Array.from({ length: 7 }, (_, day) => [day, byDay.has(day)])),
  }
}
