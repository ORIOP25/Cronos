import { describe, expect, it } from 'vitest'
import { TUTORIAL_STEPS } from '../features/tutorial/tutorialContent'
import {
  INITIAL_TUTORIAL_STATE,
  applyTutorialTransition,
  deriveCompletedStepIds,
} from '../features/tutorial/tutorialModel'

describe('Tutorial v3 state transitions', () => {
  it('starts with the first feature and persists only the four state fields', () => {
    const state = applyTutorialTransition(INITIAL_TUTORIAL_STATE, { type: 'START', tutorialRunId: 'run-1' })
    expect(state).toEqual({
      version: 3,
      tutorialRunId: 'run-1',
      status: 'IN_PROGRESS',
      stepId: 'curriculum',
    })
    expect(state).not.toHaveProperty('chapter')
    expect(state).not.toHaveProperty('values')
  })

  it('advances one step at a time and derives completed steps', () => {
    let state = applyTutorialTransition(INITIAL_TUTORIAL_STATE, { type: 'START', tutorialRunId: 'run-steps' })
    state = applyTutorialTransition(state, { type: 'ADVANCE', expectedStepId: 'curriculum' })
    expect(state.stepId).toBe('courses_classes')
    expect(deriveCompletedStepIds(state)).toEqual(['curriculum'])
  })

  it('completes only after the last expected step is advanced', () => {
    let state = applyTutorialTransition(INITIAL_TUTORIAL_STATE, { type: 'START', tutorialRunId: 'run-last' })
    for (const step of TUTORIAL_STEPS.slice(0, -1)) {
      state = applyTutorialTransition(state, { type: 'ADVANCE', expectedStepId: step.id })
    }
    expect(state.status).toBe('IN_PROGRESS')
    expect(state.stepId).toBe(TUTORIAL_STEPS.at(-1).id)
    state = applyTutorialTransition(state, { type: 'ADVANCE', expectedStepId: TUTORIAL_STEPS.at(-1).id })
    expect(state.status).toBe('COMPLETED')
    expect(deriveCompletedStepIds(state)).toEqual(TUTORIAL_STEPS.map((step) => step.id))
  })
})
