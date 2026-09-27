// @vitest-environment node
import { describe, expect, it } from 'vitest'
import {
  gridConfigurationToFormData,
  timeslotsToGridFormData,
  toGridConfigurationPayload,
  toGridTimeslotsPayload,
  toSchoolSettingsPayload,
} from '../utils/schoolConfigPayloads'

describe('school configuration payloads', () => {
  it('serializes scheduler settings', () => {
    expect(toSchoolSettingsPayload({
      school_start_date: '2026-09-01',
      school_hard_end_date: '2027-07-31',
      preferred_end_date: '2027-06-11',
      repair_stability_window_days: '14',
    })).toEqual({
      school_start_date: '2026-09-01',
      school_hard_end_date: '2027-07-31',
      preferred_end_date: '2027-06-11',
      repair_stability_window_days: 14,
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
      preferred_end_date: null,
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
        break_duration_minutes: 10, break_overrides: [], days_of_week: [0, 2],
      },
    })
  })

  it('normalizes typed hours to HH:mm:ss in the grid payload', () => {
    expect(toGridConfigurationPayload({
      formData: {
        start_time: '8:30', end_time: '18:00', slot_duration_minutes: '50',
        break_duration_minutes: '10', days: { 0: true },
      },
      gridSettings: {
        lunch_window_start: '12:30', lunch_window_end: '14:00', lunch_min_duration_minutes: '60',
      },
    })).toEqual({
      grid_settings: {
        lunch_window_start: '12:30:00', lunch_window_end: '14:00:00', lunch_min_duration_minutes: 60,
      },
      timeslots: {
        start_time: '08:30:00', end_time: '18:00:00', slot_duration_minutes: 50,
        break_duration_minutes: 10, break_overrides: [], days_of_week: [0],
      },
    })
  })

  it('rejects persisted hours with non-zero seconds', () => {
    expect(() => timeslotsToGridFormData([
      { day_of_week: 0, start_time: '08:00:15', end_time: '08:50:15' },
    ])).toThrow(/irregular/i)
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
      break_overrides: [],
      days: { 0: true, 1: false, 2: true, 3: false, 4: false, 5: false, 6: false },
    })
  })

  it('hydrates variable gaps, using the most frequent gap as the usual pause', () => {
    expect(timeslotsToGridFormData([
      { day_of_week: 0, start_time: '09:00:00', end_time: '09:50:00' },
      { day_of_week: 0, start_time: '10:00:00', end_time: '10:50:00' },
      { day_of_week: 0, start_time: '10:55:00', end_time: '11:45:00' },
      { day_of_week: 0, start_time: '11:55:00', end_time: '12:45:00' },
      { day_of_week: 2, start_time: '09:00:00', end_time: '09:50:00' },
      { day_of_week: 2, start_time: '10:00:00', end_time: '10:50:00' },
      { day_of_week: 2, start_time: '10:55:00', end_time: '11:45:00' },
      { day_of_week: 2, start_time: '11:55:00', end_time: '12:45:00' },
    ])).toEqual({
      start_time: '09:00',
      end_time: '12:45',
      slot_duration_minutes: 50,
      break_duration_minutes: 10,
      break_overrides: [{ after_slot: 2, duration_minutes: 5 }],
      days: { 0: true, 1: false, 2: true, 3: false, 4: false, 5: false, 6: false },
    })
  })

  it('round-trips reconstructed overrides into the grid payload', () => {
    const variableGrid = [
      { day_of_week: 0, start_time: '09:00:00', end_time: '09:50:00' },
      { day_of_week: 0, start_time: '10:00:00', end_time: '10:50:00' },
      { day_of_week: 0, start_time: '10:55:00', end_time: '11:45:00' },
    ]
    const formData = timeslotsToGridFormData(variableGrid)

    expect(toGridConfigurationPayload({
      formData,
      gridSettings: {
        lunch_window_start: '12:00', lunch_window_end: '14:00', lunch_min_duration_minutes: '60',
      },
    })).toEqual({
      grid_settings: {
        lunch_window_start: '12:00:00', lunch_window_end: '14:00:00', lunch_min_duration_minutes: 60,
      },
      timeslots: {
        start_time: '09:00:00', end_time: '11:45:00', slot_duration_minutes: 50,
        break_duration_minutes: 10, break_overrides: [{ after_slot: 2, duration_minutes: 5 }],
        days_of_week: [0],
      },
    })
  })

  it('rejects a persisted grid the simplified editor cannot represent', () => {
    expect(() => timeslotsToGridFormData([
      { day_of_week: 0, start_time: '08:00:00', end_time: '08:50:00' },
      { day_of_week: 1, start_time: '08:00:00', end_time: '09:00:00' },
    ])).toThrow(/irregular/i)
  })

  it('serializes only the timeslot block for grid-change requests', () => {
    expect(toGridTimeslotsPayload({
      start_time: '09:00', end_time: '12:10', slot_duration_minutes: '50',
      break_duration_minutes: '10', break_overrides: [{ after_slot: 2, duration_minutes: 5 }],
      days: { 0: true, 2: true },
    })).toEqual({
      start_time: '09:00:00', end_time: '12:10:00', slot_duration_minutes: 50,
      break_duration_minutes: 10, break_overrides: [{ after_slot: 2, duration_minutes: 5 }],
      days_of_week: [0, 2],
    })
  })

  it('hydrates the editor from the stored grid configuration verbatim', () => {
    expect(gridConfigurationToFormData({
      opening_time: '08:30',
      closing_time: '18:30',
      slot_duration_minutes: 50,
      break_duration_minutes: 10,
      break_overrides: [{ after_slot: 2, duration_minutes: 5 }],
      days_of_week: [0, 2, 4],
    })).toEqual({
      start_time: '08:30',
      end_time: '18:30',
      slot_duration_minutes: 50,
      break_duration_minutes: 10,
      break_overrides: [{ after_slot: 2, duration_minutes: 5 }],
      days: { 0: true, 1: false, 2: true, 3: false, 4: true, 5: false, 6: false },
    })
  })

  it('keeps a stored closing time even when no lesson block reaches it', () => {
    const stored = gridConfigurationToFormData({
      opening_time: '08:30',
      closing_time: '19:00',
      slot_duration_minutes: 50,
      break_duration_minutes: 10,
      break_overrides: [],
      days_of_week: [0],
    })

    expect(toGridTimeslotsPayload(stored)).toEqual(expect.objectContaining({
      start_time: '08:30:00',
      end_time: '19:00:00',
    }))
  })
})
