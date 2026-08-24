import { describe, expect, it } from 'vitest'
import {
  initialFoundationDraftValues,
  foundationReducer,
  validateFoundationStep,
  initialFoundationState,
  buildDailyTimeslots,
  STEP_PERIOD,
  STEP_DAYS,
  STEP_OPENING,
  STEP_SLOT_DURATION,
  STEP_BREAK_DURATION,
  STEP_LUNCH,
  STEP_PREVIEW,
  STEP_CONFIRMATION,
} from '../features/foundation/foundationModel'

describe('foundationModel', () => {
  it('requires school start date and hard end date with proper order (Step 1)', () => {
    expect(
      validateFoundationStep(STEP_PERIOD, {
        ...initialFoundationDraftValues,
        school_start_date: '',
        school_hard_end_date: '',
      }),
    ).toHaveProperty('school_start_date')

    expect(
      validateFoundationStep(STEP_PERIOD, {
        ...initialFoundationDraftValues,
        school_start_date: '2025-09-15',
        school_hard_end_date: '2025-09-14',
      }),
    ).toHaveProperty('school_hard_end_date')

    expect(
      validateFoundationStep(STEP_PERIOD, {
        ...initialFoundationDraftValues,
        school_start_date: '2025-09-15',
        school_hard_end_date: '2026-07-31',
      }),
    ).toEqual({})
  })

  it('validates days of week (Step 2)', () => {
    expect(
      validateFoundationStep(STEP_DAYS, {
        ...initialFoundationDraftValues,
        days_of_week: [],
      }),
    ).toHaveProperty('days_of_week')

    expect(
      validateFoundationStep(STEP_DAYS, {
        ...initialFoundationDraftValues,
        days_of_week: [0, 1, 2, 3, 4],
      }),
    ).toEqual({})
  })

  it('validates opening and closing hours (Step 3)', () => {
    expect(
      validateFoundationStep(STEP_OPENING, {
        ...initialFoundationDraftValues,
        opening_time: '',
      }),
    ).toHaveProperty('opening_time')

    expect(
      validateFoundationStep(STEP_OPENING, {
        ...initialFoundationDraftValues,
        opening_time: '18:00',
        closing_time: '08:00',
      }),
    ).toHaveProperty('closing_time')
  })

  it('validates slot duration and break duration (Steps 4 & 5)', () => {
    expect(
      validateFoundationStep(STEP_SLOT_DURATION, {
        ...initialFoundationDraftValues,
        slot_duration_minutes: 10,
      }),
    ).toHaveProperty('slot_duration_minutes')

    expect(
      validateFoundationStep(STEP_BREAK_DURATION, {
        ...initialFoundationDraftValues,
        break_duration_minutes: -1,
      }),
    ).toHaveProperty('break_duration_minutes')
  })

  it('validates lunch window constraints (Step 6)', () => {
    expect(
      validateFoundationStep(STEP_LUNCH, {
        ...initialFoundationDraftValues,
        lunch_window_start: '12:30',
        lunch_window_end: '13:00',
        lunch_min_duration_minutes: 60,
      }),
    ).toHaveProperty('lunch_min_duration_minutes')

    expect(
      validateFoundationStep(STEP_LUNCH, {
        ...initialFoundationDraftValues,
        lunch_window_start: '12:30',
        lunch_window_end: '14:00',
        lunch_min_duration_minutes: 60,
      }),
    ).toEqual({})
  })

  it('calculates grid slots and validates preview (Step 7)', () => {
    const slots = buildDailyTimeslots(initialFoundationDraftValues)
    expect(slots.length).toBeGreaterThan(0)
    expect(slots[0]).toHaveProperty('start')
    expect(slots[0]).toHaveProperty('end')

    expect(
      validateFoundationStep(STEP_PREVIEW, initialFoundationDraftValues),
    ).toEqual({})
  })

  it('validates confirmation cumulative requirements (Step 9)', () => {
    expect(
      validateFoundationStep(STEP_CONFIRMATION, {
        ...initialFoundationDraftValues,
        school_start_date: '',
      }),
    ).toHaveProperty('school_start_date')
  })

  it('requires at least one day of stability and preserves an explicit zero break', () => {
    expect(validateFoundationStep(STEP_PERIOD, {
      ...initialFoundationDraftValues,
      school_start_date: '2025-09-15',
      school_hard_end_date: '2026-07-31',
      repair_stability_window_days: 0,
    })).toHaveProperty('repair_stability_window_days')

    expect(buildDailyTimeslots({
      ...initialFoundationDraftValues,
      opening_time: '08:00',
      closing_time: '10:00',
      slot_duration_minutes: 50,
      break_duration_minutes: 0,
      lunch_window_start: '12:00',
      lunch_window_end: '13:00',
    }).map(({ start, end }) => `${start}-${end}`)).toEqual(['08:00-08:50', '08:50-09:40'])
  })

  it('rejects duplicate or invalid weekdays', () => {
    expect(validateFoundationStep(STEP_DAYS, {
      ...initialFoundationDraftValues,
      days_of_week: [0, 0],
    })).toHaveProperty('days_of_week')

    expect(validateFoundationStep(STEP_DAYS, {
      ...initialFoundationDraftValues,
      days_of_week: [7],
    })).toHaveProperty('days_of_week')
  })

  it('handles server initialization, versioning, and conflict states', () => {
    let state = foundationReducer(initialFoundationState, {
      type: 'INIT_FROM_SERVER',
      payload: {
        version: 3,
        current_step: 2,
        data: { school_start_date: '2025-09-15' },
      },
    })
    expect(state.version).toBe(3)
    expect(state.currentStep).toBe(2)
    expect(state.values.school_start_date).toBe('2025-09-15')

    // Version conflict
    state = foundationReducer(state, {
      type: 'VERSION_CONFLICT',
      payload: { expected_version: 3, current_version: 4 },
    })
    expect(state.status).toBe('conflict')
    expect(state.conflictData.current_version).toBe(4)

    // Reload conflict
    state = foundationReducer(state, {
      type: 'RESOLVE_CONFLICT_RELOAD',
      payload: {
        version: 4,
        current_step: 2,
        data: { school_start_date: '2025-09-20' },
      },
    })
    expect(state.status).toBe('idle')
    expect(state.version).toBe(4)
    expect(state.values.school_start_date).toBe('2025-09-20')
  })
})
