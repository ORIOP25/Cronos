import { describe, expect, it } from 'vitest'
import {
  initialFoundationDraftValues,
  foundationReducer,
  validateFoundationStep,
  initialFoundationState,
  buildDailyTimeslots,
  buildDailyTimeline,
  serializeFoundationDraftValues,
  STEP_PERIOD,
  STEP_DAYS,
  STEP_OPENING,
  STEP_SLOT_DURATION,
  STEP_BREAK_DURATION,
  STEP_LUNCH,
  STEP_PREVIEW,
  STEP_INTERNSHIP,
  STEP_CONFIRMATION,
} from '../features/foundation/foundationModel'

describe('foundationModel', () => {
  it('proposes the new default grid and generates eight lessons (R21)', () => {
    expect(initialFoundationDraftValues).toMatchObject({
      opening_time: '09:00',
      closing_time: '18:00',
      slot_duration_minutes: 60,
      break_duration_minutes: 5,
      lunch_window_start: '12:00',
      lunch_window_end: '14:00',
      lunch_min_duration_minutes: 60,
    })

    expect(buildDailyTimeslots(initialFoundationDraftValues).map(({ start, end }) => `${start}-${end}`)).toEqual([
      '09:00-10:00',
      '10:05-11:05',
      '11:10-12:10',
      '12:15-13:15',
      '13:20-14:20',
      '14:25-15:25',
      '15:30-16:30',
      '16:35-17:35',
    ])
  })

  it('keeps a configured grid when the server draft provides it', () => {
    const state = foundationReducer(initialFoundationState, {
      type: 'INIT_FROM_SERVER',
      payload: {
        version: 1,
        current_step: 3,
        data: {
          opening_time: '08:30',
          closing_time: '17:30',
          slot_duration_minutes: 50,
          break_duration_minutes: 10,
          lunch_window_start: '12:30',
        },
      },
    })

    expect(state.values).toMatchObject({
      opening_time: '08:30',
      closing_time: '17:30',
      slot_duration_minutes: 50,
      break_duration_minutes: 10,
      lunch_window_start: '12:30',
    })
  })

  it.each(['2025-09-14', '2026-08-01'])('rejects preferred end %s outside the school period', (preferredEnd) => {
    expect(validateFoundationStep(STEP_PERIOD, {
      ...initialFoundationDraftValues,
      school_start_date: '2025-09-15',
      school_hard_end_date: '2026-07-31',
      preferred_end_date: preferredEnd,
    })).toHaveProperty('preferred_end_date')
  })

  it.each(['', '2025-09-15', '2026-06-30', '2026-07-31'])('accepts optional preferred end %s within the school period', (preferredEnd) => {
    expect(validateFoundationStep(STEP_PERIOD, {
      ...initialFoundationDraftValues,
      school_start_date: '2025-09-15',
      school_hard_end_date: '2026-07-31',
      preferred_end_date: preferredEnd,
    })).toEqual({})
  })

  it('serializes empty draft fields as nullable values for the partial backend contract', () => {
    expect(serializeFoundationDraftValues({ school_start_date: '2025-09-15', school_hard_end_date: '' })).toEqual({
      school_start_date: '2025-09-15',
      school_hard_end_date: null,
    })
  })

  it('serializes an empty stability window as zero and keeps zero intact', () => {
    expect(serializeFoundationDraftValues({ repair_stability_window_days: '' })).toEqual({
      repair_stability_window_days: 0,
    })
    expect(serializeFoundationDraftValues({ repair_stability_window_days: 0 })).toEqual({
      repair_stability_window_days: 0,
    })
  })

  it('normalizes valid hours and blanks incomplete drafts before autosave', () => {
    expect(serializeFoundationDraftValues({
      opening_time: '8:30',
      closing_time: '8:3',
      lunch_window_start: '12:30:00',
      lunch_window_end: '',
    })).toEqual({
      opening_time: '08:30',
      closing_time: null,
      lunch_window_start: '12:30',
      lunch_window_end: null,
    })
  })

  it('rejects incomplete and out-of-range hours in opening and lunch steps', () => {
    expect(validateFoundationStep(STEP_OPENING, {
      ...initialFoundationDraftValues,
      opening_time: '8:3',
      closing_time: '17:30',
    })).toHaveProperty('opening_time')

    expect(validateFoundationStep(STEP_OPENING, {
      ...initialFoundationDraftValues,
      opening_time: '25:00',
      closing_time: '17:30',
    })).toHaveProperty('opening_time')

    expect(validateFoundationStep(STEP_LUNCH, {
      ...initialFoundationDraftValues,
      lunch_window_start: '12:30 PM',
      lunch_window_end: '14:00',
    })).toHaveProperty('lunch_window_start')

    expect(validateFoundationStep(STEP_OPENING, {
      ...initialFoundationDraftValues,
      opening_time: '8:30',
      closing_time: '17:30',
    })).toEqual({})
  })

  it('builds the daily grid from valid 24h hours', () => {
    const slots = buildDailyTimeslots({
      ...initialFoundationDraftValues,
      opening_time: '8:30',
      closing_time: '10:30',
      slot_duration_minutes: 50,
      break_duration_minutes: 10,
    })
    expect(slots.map(({ start, end }) => `${start}-${end}`)).toEqual(['08:30-09:20', '09:30-10:20'])
  })

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

  it('validates confirmation cumulative requirements (Step 10)', () => {
    expect(
      validateFoundationStep(STEP_CONFIRMATION, {
        ...initialFoundationDraftValues,
        school_start_date: '',
      }),
    ).toHaveProperty('school_start_date')
  })

  it('accepts the optional internship step without flows (Step 9)', () => {
    expect(
      validateFoundationStep(STEP_INTERNSHIP, {
        ...initialFoundationDraftValues,
        school_start_date: '2025-09-15',
        school_hard_end_date: '2026-07-31',
      }),
    ).toEqual({})
  })

  it('validates internship flow rows inside the school period', () => {
    const base = {
      ...initialFoundationDraftValues,
      school_start_date: '2025-09-15',
      school_hard_end_date: '2026-07-31',
    }
    expect(validateFoundationStep(STEP_INTERNSHIP, {
      ...base,
      internship_flows: [{ name: 'Estágio', start_date: '2026-02-02', end_date: '2026-02-13' }],
    })).toEqual({})
    expect(validateFoundationStep(STEP_INTERNSHIP, {
      ...base,
      internship_flows: [{ name: '', start_date: '2026-02-02', end_date: '2026-02-13' }],
    })).toHaveProperty('internship_flows')
    expect(validateFoundationStep(STEP_INTERNSHIP, {
      ...base,
      internship_flows: [{ name: 'Estágio', start_date: '2026-02-13', end_date: '2026-02-02' }],
    })).toHaveProperty('internship_flows')
    expect(validateFoundationStep(STEP_INTERNSHIP, {
      ...base,
      internship_flows: [{ name: 'Estágio', start_date: '2026-08-01', end_date: '2026-08-10' }],
    })).toHaveProperty('internship_flows')
  })

  it('persists partially filled internship flows and drops empty rows', () => {
    expect(serializeFoundationDraftValues({
      internship_flows: [
        { name: '  Estágio A  ', start_date: '2026-02-02', end_date: '2026-02-13' },
        { name: 'Incompleto', start_date: '', end_date: '' },
        { name: '', start_date: '', end_date: '' },
      ],
    })).toEqual({
      internship_flows: [
        { name: 'Estágio A', start_date: '2026-02-02', end_date: '2026-02-13' },
        { name: 'Incompleto', start_date: null, end_date: null },
      ],
    })
  })

  it('accepts zero days of stability and preserves an explicit zero break', () => {
    expect(validateFoundationStep(STEP_PERIOD, {
      ...initialFoundationDraftValues,
      school_start_date: '2025-09-15',
      school_hard_end_date: '2026-07-31',
      repair_stability_window_days: 0,
    })).not.toHaveProperty('repair_stability_window_days')

    expect(validateFoundationStep(STEP_PERIOD, {
      ...initialFoundationDraftValues,
      school_start_date: '2025-09-15',
      school_hard_end_date: '2026-07-31',
      repair_stability_window_days: 61,
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

  it('supports Sunday as the canonical weekday value 6', () => {
    expect(validateFoundationStep(STEP_DAYS, {
      ...initialFoundationDraftValues,
      days_of_week: [6],
    })).toEqual({})
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

  it('stores structured errors and clears them when the edited value changes', () => {
    let state = foundationReducer(initialFoundationState, {
      type: 'SAVE_FAILED',
      error: 'Não foi possível guardar o rascunho.',
      errorCode: 'HOLIDAY_SYNC_FAILED',
    })
    expect(state.errorCode).toBe('HOLIDAY_SYNC_FAILED')

    state = foundationReducer(state, { type: 'SET_FIELD', field: 'school_start_date', value: '2025-09-15' })
    expect(state.error).toBe('')
    expect(state.errorCode).toBe('')
  })

  describe('variable breaks', () => {
    const variableValues = {
      ...initialFoundationDraftValues,
      opening_time: '09:00',
      closing_time: '11:45',
      slot_duration_minutes: 50,
      break_duration_minutes: 10,
      break_overrides: [{ after_slot: 2, duration_minutes: 5 }],
    }

    it('builds the same sequence as the backend contract example', () => {
      const slots = buildDailyTimeslots(variableValues)
      expect(slots.map(({ start, end }) => `${start}-${end}`)).toEqual([
        '09:00-09:50',
        '10:00-10:50',
        '10:55-11:45',
      ])
      expect(slots.map(({ index }) => index)).toEqual([1, 2, 3])
      expect(slots.map(({ breakAfter }) => breakAfter)).toEqual([10, 5, 0])
    })

    it('keeps legacy payloads uniform when overrides are absent or empty', () => {
      const legacy = {
        ...initialFoundationDraftValues,
        opening_time: '08:00',
        closing_time: '10:00',
        slot_duration_minutes: 50,
        break_duration_minutes: 10,
      }
      const withoutField = buildDailyTimeslots(legacy)
      expect(withoutField.map(({ start, end }) => `${start}-${end}`)).toEqual([
        '08:00-08:50',
        '09:00-09:50',
      ])

      const withEmpty = buildDailyTimeslots({ ...legacy, break_overrides: [] })
      expect(withEmpty.map(({ start, end }) => `${start}-${end}`)).toEqual([
        '08:00-08:50',
        '09:00-09:50',
      ])
    })

    it('honours zero and longer overrides when generating lessons', () => {
      const zero = buildDailyTimeslots({
        ...variableValues,
        opening_time: '09:00',
        closing_time: '12:00',
        break_duration_minutes: 0,
        break_overrides: [{ after_slot: 2, duration_minutes: 30 }],
      })
      expect(zero.map(({ start, end }) => `${start}-${end}`)).toEqual([
        '09:00-09:50',
        '09:50-10:40',
        '11:10-12:00',
      ])
    })

    it('reports overrides that lost their following lesson', () => {
      const values = {
        ...variableValues,
        opening_time: '09:00',
        closing_time: '09:50',
        break_duration_minutes: 0,
        break_overrides: [{ after_slot: 2, duration_minutes: 5 }],
      }
      const errors = validateFoundationStep(STEP_BREAK_DURATION, values)
      expect(errors).toHaveProperty('break_overrides')
      expect(errors.break_overrides).toContain('2')
    })

    it('rejects duplicate and out-of-range overrides', () => {
      expect(validateFoundationStep(STEP_BREAK_DURATION, {
        ...variableValues,
        break_overrides: [
          { after_slot: 1, duration_minutes: 5 },
          { after_slot: 1, duration_minutes: 10 },
        ],
      })).toHaveProperty('break_overrides')

      expect(validateFoundationStep(STEP_BREAK_DURATION, {
        ...variableValues,
        break_overrides: [{ after_slot: 0, duration_minutes: 5 }],
      })).toHaveProperty('break_overrides')

      expect(validateFoundationStep(STEP_BREAK_DURATION, {
        ...variableValues,
        break_overrides: [{ after_slot: 1, duration_minutes: 61 }],
      })).toHaveProperty('break_overrides')

      expect(validateFoundationStep(STEP_BREAK_DURATION, variableValues)).toEqual({})
    })

    it('serializes overrides untouched for autosave', () => {
      expect(serializeFoundationDraftValues({
        break_overrides: [{ after_slot: 2, duration_minutes: 5 }],
      }).break_overrides).toEqual([{ after_slot: 2, duration_minutes: 5 }])
    })

    it('ignores invalid override durations without moving the clock backwards', () => {
      const timeline = buildDailyTimeline({
        ...variableValues,
        break_overrides: [
          { after_slot: 1, duration_minutes: -50 },
          { after_slot: 2, duration_minutes: 5 },
        ],
      })

      expect(timeline.slots.map(({ start, end }) => `${start}-${end}`)).toEqual([
        '09:00-09:50',
        '10:00-10:50',
        '10:55-11:45',
      ])
      expect(timeline.invalidOverrides).toEqual([
        { after_slot: 1, duration_minutes: -50, reason: 'duration' },
      ])
    })

    it('reports malformed positions without blocking the timeline', () => {
      const timeline = buildDailyTimeline({
        ...variableValues,
        break_overrides: [{ after_slot: 0, duration_minutes: 5 }],
      })

      expect(timeline).not.toBeNull()
      expect(timeline.slots.length).toBeGreaterThan(0)
      expect(timeline.invalidOverrides[0].reason).toBe('position')
    })

    it('separates unused overrides so the interface can remove them', () => {
      const timeline = buildDailyTimeline({
        ...initialFoundationDraftValues,
        opening_time: '09:00',
        closing_time: '09:50',
        slot_duration_minutes: 50,
        break_duration_minutes: 10,
        break_overrides: [{ after_slot: 2, duration_minutes: 5 }],
      })

      expect(timeline.slots).toHaveLength(1)
      expect(timeline.unusedOverrides).toEqual([2])
      expect(timeline.invalidOverrides).toEqual([])
    })
  })
})
