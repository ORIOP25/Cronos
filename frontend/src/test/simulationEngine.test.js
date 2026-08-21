// @vitest-environment node
import { describe, expect, it } from 'vitest'
import {
  simulationReducer,
  INITIAL_SIMULATION_STATE,
} from '../features/tutorial/simulationEngine'
import { TUTORIAL_STEPS } from '../features/tutorial/contracts'

describe('Tutorial Simulation Engine Reducer', () => {
  it('initializes and opens tutorial with random run id', () => {
    const action = { type: 'OPEN_TUTORIAL', payload: { tutorialRunId: 'test-run-123' } }
    const state = simulationReducer(INITIAL_SIMULATION_STATE, action)
    expect(state.isOpen).toBe(true)
    expect(state.tutorialRunId).toBe('test-run-123')
    expect(state.currentStepIndex).toBe(0)
    expect(state.completed).toBe(false)
    expect(state.skippedSteps).toEqual([])
  })

  it('navigates next and previous steps deterministically', () => {
    let state = simulationReducer(INITIAL_SIMULATION_STATE, {
      type: 'OPEN_TUTORIAL',
      payload: { tutorialRunId: 'test-run' },
    })

    // Step 0 -> Step 1
    state = simulationReducer(state, { type: 'NEXT_STEP' })
    expect(state.currentStepIndex).toBe(1)

    // Step 1 -> Step 2
    state = simulationReducer(state, { type: 'NEXT_STEP' })
    expect(state.currentStepIndex).toBe(2)

    // Step 2 -> Step 1
    state = simulationReducer(state, { type: 'PREV_STEP' })
    expect(state.currentStepIndex).toBe(1)

    // Step 1 -> Step 0
    state = simulationReducer(state, { type: 'PREV_STEP' })
    expect(state.currentStepIndex).toBe(0)

    // Cannot go below 0
    state = simulationReducer(state, { type: 'PREV_STEP' })
    expect(state.currentStepIndex).toBe(0)
  })

  it('tracks skipped steps properly', () => {
    let state = simulationReducer(INITIAL_SIMULATION_STATE, {
      type: 'OPEN_TUTORIAL',
      payload: { tutorialRunId: 'test-run' },
    })

    // Advance past unskippable intro step 0
    state = simulationReducer(state, { type: 'NEXT_STEP' })
    expect(state.currentStepIndex).toBe(1)
    expect(TUTORIAL_STEPS[1].isSkippable).toBe(true)

    // Skip step 1
    state = simulationReducer(state, { type: 'SKIP_STEP' })
    expect(state.skippedSteps).toContain(TUTORIAL_STEPS[1].id)
    expect(state.currentStepIndex).toBe(2)
  })

  it('completes on last step next or explicit completion', () => {
    let state = {
      ...INITIAL_SIMULATION_STATE,
      isOpen: true,
      currentStepIndex: TUTORIAL_STEPS.length - 1,
    }

    state = simulationReducer(state, { type: 'NEXT_STEP' })
    expect(state.completed).toBe(true)

    // Explicit complete
    const directComplete = simulationReducer(INITIAL_SIMULATION_STATE, { type: 'COMPLETE_TUTORIAL' })
    expect(directComplete.completed).toBe(true)
    expect(directComplete.currentStepIndex).toBe(TUTORIAL_STEPS.length - 1)
  })

  it('persists the skipped status and starts a fresh run on repeat', () => {
    let state = simulationReducer(INITIAL_SIMULATION_STATE, {
      type: 'OPEN_TUTORIAL',
      payload: { tutorialRunId: 'run-1' },
    })
    state = simulationReducer(state, { type: 'SKIP_TUTORIAL' })

    expect(state.isOpen).toBe(false)
    expect(state.status).toBe('SKIPPED')

    state = simulationReducer(state, {
      type: 'REPEAT_TUTORIAL',
      payload: { tutorialRunId: 'run-2' },
    })
    expect(state.isOpen).toBe(true)
    expect(state.status).toBe('IN_PROGRESS')
    expect(state.tutorialRunId).toBe('run-2')
    expect(state.currentStepIndex).toBe(0)
  })
})
