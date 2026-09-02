// @vitest-environment node
import { describe, expect, it } from 'vitest'
import {
  timeslotsToGridFormData,
  toGridConfigurationPayload,
  toSchoolSettingsPayload,
} from '../utils/schoolConfigPayloads'

describe('school configuration payloads', () => {
  it('serializes scheduler settings', () => {
    expect(toSchoolSettingsPayload({
      school_start_date: '2026-09-01', school_hard_end_date: '2027-07-31', repair_stability_window_days: '14',
    })).toEqual({
      school_start_date: '2026-09-01', school_hard_end_date: '2027-07-31', repair_stability_window_days: 14,
    })
  })

  it('preserves zero stability and can explicitly disable automatic holidays', () => {
    expect(toSchoolSettingsPayload({
      school_start_date: '2026-09-01',
      school_hard_end_date: '2027-07-31',
      repair_stability_window_days: '0',
      automatic_holidays_enabled: false,
    })).toEqual({
      school_start_date: '2026-09-01',
      school_hard_end_date: '2027-07-31',
      repair_stability_window_days: 0,
      automatic_holidays_enabled: false,
    })
  })
  it('serializes grid and lunch settings', () => {
    expect(toGridConfigurationPayload({
      formData: {
        start_time: '08:00', end_time: '18:00', slot_duration_minutes: '50',
        break_duration_minutes: '10', days: { 0: true, 1: false, 2: true },
      },
      gridSettings: {
        lunch_window_start: '12:00', lunch_window_end: '14:00', lunch_min_duration_minutes: '60',
      },
    })).toEqual({
      grid_settings: {
        lunch_window_start: '12:00:00', lunch_window_end: '14:00:00', lunch_min_duration_minutes: 60,
      },
      timeslots: {
        start_time: '08:00:00', end_time: '18:00:00', slot_duration_minutes: 50,
        break_duration_minutes: 10, days_of_week: [0, 2],
      },
    })
  })

  it('hydrates the editor from a regular persisted grid', () => {
    expect(timeslotsToGridFormData([
      { day_of_week: 0, start_time: '08:00:00', end_time: '08:50:00' },
      { day_of_week: 0, start_time: '09:00:00', end_time: '09:50:00' },
      { day_of_week: 2, start_time: '08:00:00', end_time: '08:50:00' },
      { day_of_week: 2, start_time: '09:00:00', end_time: '09:50:00' },
    ])).toEqual({
      start_time: '08:00',
      end_time: '09:50',
      slot_duration_minutes: 50,
      break_duration_minutes: 10,
      days: { 0: true, 1: false, 2: true, 3: false, 4: false, 5: false, 6: false },
    })
  })

  it('rejects a persisted grid the simplified editor cannot represent', () => {
    expect(() => timeslotsToGridFormData([
      { day_of_week: 0, start_time: '08:00:00', end_time: '08:50:00' },
      { day_of_week: 1, start_time: '08:00:00', end_time: '09:00:00' },
    ])).toThrow(/irregular/i)
  })
})
