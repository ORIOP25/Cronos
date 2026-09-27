export function toSchoolSettingsPayload(form) {
  const payload = {
    school_start_date: form.school_start_date || null,
    school_hard_end_date: form.school_hard_end_date || null,
    preferred_end_date: form.preferred_end_date || null,
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
  days: { 0: true, 1: true, 2: true, 3: true, 4: true, 5: false, 6: false },
}

const withSeconds = (value) => (value?.length === 5 ? `${value}:00` : value)
const minuteOfDay = (value) => {
  const match = /^(\d{2}):(\d{2})/.exec(value || '')
  if (!match) throw new Error('A grelha horária guardada é irregular.')
  return Number(match[1]) * 60 + Number(match[2])
}

export function toGridConfigurationPayload({ formData, gridSettings }) {
  const selectedDays = Object.keys(formData.days)
    .filter((day) => formData.days[day])
    .map((day) => Number.parseInt(day, 10))
  return {
    grid_settings: {
      lunch_window_start: gridSettings.lunch_window_start ? withSeconds(gridSettings.lunch_window_start) : null,
      lunch_window_end: gridSettings.lunch_window_end ? withSeconds(gridSettings.lunch_window_end) : null,
      lunch_min_duration_minutes: Number.parseInt(gridSettings.lunch_min_duration_minutes, 10),
    },
    timeslots: {
      start_time: withSeconds(formData.start_time),
      end_time: withSeconds(formData.end_time),
      slot_duration_minutes: Number.parseInt(formData.slot_duration_minutes, 10),
      break_duration_minutes: Number.parseInt(formData.break_duration_minutes, 10),
      days_of_week: selectedDays,
    },
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
      start: slot.start_time.slice(0, 5),
      end: slot.end_time.slice(0, 5),
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
  const breaks = new Set()
  for (const sequence of sequences) {
    sequence.forEach((slot, index) => {
      const duration = minuteOfDay(slot.end) - minuteOfDay(slot.start)
      if (duration <= 0) throw new Error('A grelha horária guardada é irregular.')
      durations.add(duration)
      if (index > 0) breaks.add(minuteOfDay(slot.start) - minuteOfDay(sequence[index - 1].end))
    })
  }
  if (durations.size !== 1 || breaks.size > 1 || [...breaks].some((value) => value < 0)) {
    throw new Error('A grelha horária guardada é irregular e não pode ser editada neste formulário.')
  }

  const sequence = sequences[0]
  return {
    start_time: sequence[0].start,
    end_time: sequence.at(-1).end,
    slot_duration_minutes: [...durations][0],
    break_duration_minutes: breaks.size ? [...breaks][0] : 0,
    days: Object.fromEntries(Array.from({ length: 7 }, (_, day) => [day, byDay.has(day)])),
  }
}
