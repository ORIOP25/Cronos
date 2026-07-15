import { describe, expect, it } from 'vitest'
import { toGridSettingsPayload, toSchoolSettingsPayload } from '../utils/schoolConfigPayloads'

describe('school configuration payloads', () => {
  it('serializes scheduler settings', () => {
    expect(toSchoolSettingsPayload({
      school_start_date: '2026-09-01', school_hard_end_date: '2027-07-31', repair_stability_window_days: '14',
    })).toEqual({
      school_start_date: '2026-09-01', school_hard_end_date: '2027-07-31', repair_stability_window_days: 14,
    })
  })
  it('serializes grid and lunch settings', () => {
    expect(toGridSettingsPayload({
      formData: {
        start_time: '08:00', end_time: '18:00', slot_duration_minutes: '50',
        break_duration_minutes: '10', days: { 0: true, 1: false, 2: true },
      },
      gridSettings: {
        lunch_window_start: '12:00', lunch_window_end: '14:00', lunch_min_duration_minutes: '60',
      },
    })).toEqual({
      gridSettings: {
        lunch_window_start: '12:00:00', lunch_window_end: '14:00:00', lunch_min_duration_minutes: 60,
      },
      timeslots: {
        start_time: '08:00:00', end_time: '18:00:00', slot_duration_minutes: 50,
        break_duration_minutes: 10, days_of_week: [0, 2],
      },
    })
  })
})
