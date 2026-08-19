import { describe, expect, it } from 'vitest'
import { initialOnboardingValues, onboardingReducer, validateOnboardingStep } from '../features/onboarding/onboardingModel'

describe('onboardingModel', () => {
  it('requires a final date after the start date', () => {
    expect(validateOnboardingStep(1, { ...initialOnboardingValues, school_start_date: '2026-09-15', school_hard_end_date: '2026-09-14' })).toEqual(expect.objectContaining({ school_hard_end_date: expect.any(String) }))
  })

  it('rejects a lunch duration longer than its window', () => {
    expect(validateOnboardingStep(2, { ...initialOnboardingValues, lunch_start: '12:00', lunch_end: '13:00', lunch_min_duration: 61 })).toEqual(expect.objectContaining({ lunch_min_duration: expect.any(String) }))
  })

  it('preserves values when moving back from the second step', () => {
    let state = onboardingReducer({ currentStep: 0, values: initialOnboardingValues, fieldErrors: {}, status: 'idle', error: '', completedThisSession: false }, { type: 'START' })
    state = onboardingReducer(state, { type: 'SET_FIELD', field: 'school_start_date', value: '2026-09-15' })
    state = onboardingReducer(state, { type: 'NEXT' })
    state = onboardingReducer(state, { type: 'BACK' })
    expect(state.currentStep).toBe(1)
    expect(state.values.school_start_date).toBe('2026-09-15')
  })
})
