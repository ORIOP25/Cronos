export function toSchoolSettingsPayload(form) {
  return {
    school_start_date: form.school_start_date || null,
    school_hard_end_date: form.school_hard_end_date || null,
    repair_stability_window_days: form.repair_stability_window_days
      ? Number.parseInt(form.repair_stability_window_days, 10)
      : null,
  }
}

export function toGridSettingsPayload({ formData, gridSettings }) {
  const selectedDays = Object.keys(formData.days)
    .filter((day) => formData.days[day])
    .map((day) => Number.parseInt(day, 10))
  return {
    gridSettings: {
      lunch_window_start: gridSettings.lunch_window_start ? `${gridSettings.lunch_window_start}:00` : null,
      lunch_window_end: gridSettings.lunch_window_end ? `${gridSettings.lunch_window_end}:00` : null,
      lunch_min_duration_minutes: Number.parseInt(gridSettings.lunch_min_duration_minutes, 10),
    },
    timeslots: {
      start_time: `${formData.start_time}:00`,
      end_time: `${formData.end_time}:00`,
      slot_duration_minutes: Number.parseInt(formData.slot_duration_minutes, 10),
      break_duration_minutes: Number.parseInt(formData.break_duration_minutes, 10),
      days_of_week: selectedDays,
    },
  }
}
