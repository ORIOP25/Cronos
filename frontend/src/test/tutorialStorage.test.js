import { beforeEach, describe, expect, it, vi } from 'vitest'
import { TUTORIAL_STEPS, TUTORIAL_VERSION } from '../features/tutorial/tutorialScenario'
import { INITIAL_TUTORIAL_STATE, applyTutorialTransition } from '../features/tutorial/tutorialModel'
import { createTutorialState, loadTutorialState, saveTutorialState } from '../features/tutorial/tutorialStorage'

describe('tutorialStorage v2', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('persists only the minimum resumable checkpoint', () => {
    let state = applyTutorialTransition(INITIAL_TUTORIAL_STATE, { type: 'START', tutorialRunId: 'run-1' })
    state = applyTutorialTransition(state, { type: 'COMPLETE_STEP', actionId: 'continue' })
    state = applyTutorialTransition(state, { type: 'SKIP_STEP' })
    saveTutorialState(localStorage, 'tutorial', state)
    const raw = JSON.parse(localStorage.getItem('tutorial'))
    const loaded = loadTutorialState(localStorage, 'tutorial', INITIAL_TUTORIAL_STATE)

    expect(raw).toEqual({
      version: TUTORIAL_VERSION,
      tutorialRunId: 'run-1',
      status: 'IN_PROGRESS',
      chapter: 1,
      stepId: 'module_add',
      values: {},
      skippedStepIds: ['subject_create'],
    })
    expect(raw).not.toHaveProperty('simulationData')
    expect(raw).not.toHaveProperty('currentStepIndex')
    expect(loaded).toEqual(raw)
  })

  it('rejects malformed, v1, inconsistent and mandatory-skip states', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    localStorage.setItem('tutorial', '{invalid-json')
    expect(loadTutorialState(localStorage, 'tutorial', INITIAL_TUTORIAL_STATE)).toBe(INITIAL_TUTORIAL_STATE)

    const base = {
      version: TUTORIAL_VERSION - 1,
      tutorialRunId: 'run-1',
      status: 'IN_PROGRESS',
      chapter: 1,
      stepId: TUTORIAL_STEPS[0].id,
      values: {},
      skippedStepIds: [],
    }
    expect(createTutorialState(INITIAL_TUTORIAL_STATE, base)).toBe(INITIAL_TUTORIAL_STATE)
    expect(createTutorialState(INITIAL_TUTORIAL_STATE, { ...base, version: TUTORIAL_VERSION, chapter: 2 })).toBe(INITIAL_TUTORIAL_STATE)
    expect(createTutorialState(INITIAL_TUTORIAL_STATE, { ...base, version: TUTORIAL_VERSION, skippedStepIds: ['structure_overview'] })).toBe(INITIAL_TUTORIAL_STATE)
    expect(consoleError).toHaveBeenCalled()
  })

  it('accepts NOT_STARTED without a run id and rejects active states without one', () => {
    const notStarted = { ...INITIAL_TUTORIAL_STATE, tutorialRunId: null }
    expect(createTutorialState(INITIAL_TUTORIAL_STATE, notStarted)).toEqual(INITIAL_TUTORIAL_STATE)
    expect(createTutorialState(INITIAL_TUTORIAL_STATE, { ...notStarted, status: 'IN_PROGRESS' })).toBe(INITIAL_TUTORIAL_STATE)
  })
})
