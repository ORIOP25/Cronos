import { beforeEach, describe, expect, it, vi } from 'vitest'
import { TUTORIAL_STEPS, TUTORIAL_VERSION } from '../features/tutorial/contracts'
import {
  createTutorialState,
  loadTutorialState,
  saveTutorialState,
} from '../features/tutorial/tutorialStorage'
import { INITIAL_SIMULATION_STATE } from '../features/tutorial/simulationEngine'

describe('tutorialStorage', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('round-trips only the canonical resumable state', () => {
    const state = {
      ...INITIAL_SIMULATION_STATE,
      tutorialRunId: 'run-1',
      status: 'IN_PROGRESS',
      stepId: TUTORIAL_STEPS[4].id,
      chapter: 1,
      values: { organizationName: 'Escola' },
      skippedStepIds: [TUTORIAL_STEPS[1].id],
      currentStepIndex: 4,
      completedSteps: [],
      completed: false,
    }

    saveTutorialState(localStorage, 'tutorial', state)
    const raw = JSON.parse(localStorage.getItem('tutorial'))
    const loaded = loadTutorialState(localStorage, 'tutorial', INITIAL_SIMULATION_STATE)

    expect(raw).toMatchObject({
      version: TUTORIAL_VERSION,
      tutorialRunId: 'run-1',
      status: 'IN_PROGRESS',
      chapter: 1,
      stepId: TUTORIAL_STEPS[4].id,
      currentStepIndex: 4,
      completed: false,
      values: { organizationName: 'Escola' },
      skippedStepIds: [TUTORIAL_STEPS[1].id],
      completedStepIds: [],
    })
    expect(raw.simulationData.sampleCourses).toHaveLength(2)
    expect(loaded.currentStepIndex).toBe(4)
    expect(loaded.skippedSteps).toEqual([TUTORIAL_STEPS[1].id])
  })

  it('rejects stale or malformed saved state', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    localStorage.setItem('tutorial', '{invalid-json')

    expect(loadTutorialState(localStorage, 'tutorial', INITIAL_SIMULATION_STATE)).toBe(INITIAL_SIMULATION_STATE)
    expect(consoleError).toHaveBeenCalled()
    expect(createTutorialState(INITIAL_SIMULATION_STATE, {
      version: TUTORIAL_VERSION - 1,
      tutorialRunId: 'run-1',
      status: 'IN_PROGRESS',
      stepId: TUTORIAL_STEPS[0].id,
    })).toBe(INITIAL_SIMULATION_STATE)
  })

  it('rejects a resumable state without the deterministic scenario', () => {
    const saved = {
      version: TUTORIAL_VERSION,
      tutorialRunId: 'run-1',
      status: 'IN_PROGRESS',
      stepId: TUTORIAL_STEPS[0].id,
      currentStepIndex: 0,
      skippedStepIds: [],
      completedStepIds: [],
      completed: false,
      simulationData: { sampleCourses: [] },
    }

    expect(createTutorialState(INITIAL_SIMULATION_STATE, saved)).toBe(INITIAL_SIMULATION_STATE)
  })
})
