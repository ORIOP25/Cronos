import { describe, expect, it, vi } from 'vitest'
import {
  TUTORIAL_STEPS,
  TUTORIAL_VERSION,
  getTutorialStorageKey,
  matchTutorialMutation,
  matchTutorialMutations,
  createTutorialScenario,
  tutorialScenarioInvariants,
} from '../features/tutorial/tutorialScenario'
import {
  INITIAL_TUTORIAL_STATE,
  applyTutorialTransition,
  getTutorialScenario,
  validateTutorialState,
} from '../features/tutorial/tutorialModel'

describe('tutorial v2 domain', () => {
  it('declares exactly 24 deterministic steps and 17 skips', () => {
    expect(TUTORIAL_VERSION).toBe(2)
    expect(TUTORIAL_STEPS).toHaveLength(24)
    expect(new Set(TUTORIAL_STEPS.map((step) => step.id)).size).toBe(24)
    expect(TUTORIAL_STEPS.filter((step) => step.isSkippable)).toHaveLength(17)
    expect(TUTORIAL_STEPS.filter((step) => step.kind === 'observation').every((step) => step.action.id === 'continue')).toBe(true)
    expect(TUTORIAL_STEPS.every((step) => step.action.id && step.activeNavItem && step.screen)).toBe(true)
  })

  it('contains the required local scenario dimensions', () => {
    const scenario = createTutorialScenario(INITIAL_TUTORIAL_STATE)
    expect(tutorialScenarioInvariants(scenario)).toEqual({
      courses: true,
      classes: true,
      subjects: true,
      modules: true,
      teachers: true,
      rooms: true,
      demoIds: true,
      weeklyGrid: true,
      historyPreserved: true,
    })
  })

  it('uses the v2 tenant-isolated storage key', () => {
    expect(getTutorialStorageKey('user_123', 'org_abc')).toBe('cronos:tutorial:v2:user:user_123:org:org_abc')
    expect(getTutorialStorageKey(null, null)).toBe('cronos:tutorial:v2:user:anonymous:org:personal')
  })

  it('accepts only the action declared by the current step', () => {
    const started = applyTutorialTransition(INITIAL_TUTORIAL_STATE, { type: 'START', tutorialRunId: 'run-1' })
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    const invalid = applyTutorialTransition(started, { type: 'COMPLETE_STEP', actionId: 'wrong-action' })
    expect(invalid).toBe(started)
    expect(consoleError).toHaveBeenCalled()
    consoleError.mockRestore()

    const completed = applyTutorialTransition(started, { type: 'COMPLETE_STEP', actionId: 'continue' })
    expect(completed.stepId).toBe('subject_create')
    expect(completed.chapter).toBe(1)
  })

  it('completes related fields saved by one real form as one sequence', () => {
    let state = applyTutorialTransition(INITIAL_TUTORIAL_STATE, { type: 'START', tutorialRunId: 'run-sequence' })
    state = applyTutorialTransition(state, { type: 'COMPLETE_STEP', actionId: 'continue' })
    state = applyTutorialTransition(state, {
      type: 'COMPLETE_SEQUENCE',
      actionIds: ['save-subject', 'add-module'],
    })
    expect(state.stepId).toBe('course_create')
  })

  it('matches a real form mutation to one or more declared tutorial objectives', () => {
    const matches = matchTutorialMutations({
      method: 'post',
      path: '/courses/',
      body: {
        name: 'Técnico de Eletrónica',
        abbreviation: 'TE',
        classes_config: [{ name: '10.º TE', grade_level: 10, size: 24 }],
      },
    })
    expect(matches.map((match) => match.stepId)).toEqual(['course_create', 'class_create'])
    expect(matchTutorialMutation({
      stepId: 'course_create',
      method: 'post',
      path: '/courses/',
      body: { name: 'Técnico de Eletrónica', abbreviation: 'TE' },
    })?.expectedActionId).toBe('save-course')

    expect(matchTutorialMutation({
      stepId: 'teacher_add',
      method: 'post',
      path: '/members',
      body: { organization_display_name: 'Rui Almeida', email: '', subject_ids: [] },
    })).toMatchObject({ expectedActionId: 'save-teacher', changes: { name: 'Rui Almeida' } })
  })

  it('keeps exit as an in-progress checkpoint and repeats with a new run', () => {
    const started = applyTutorialTransition(INITIAL_TUTORIAL_STATE, { type: 'START', tutorialRunId: 'run-1' })
    const exited = applyTutorialTransition(started, { type: 'EXIT' })
    expect(exited).toEqual(started)
    expect(exited.status).toBe('IN_PROGRESS')

    const repeated = applyTutorialTransition(exited, { type: 'REPEAT', tutorialRunId: 'run-2' })
    expect(repeated).toMatchObject({ tutorialRunId: 'run-2', status: 'IN_PROGRESS', stepId: 'structure_overview', skippedStepIds: [], values: {} })
  })

  it('completes deterministic skip boundary and representative masks with valid data', () => {
    const skippable = TUTORIAL_STEPS.filter((step) => step.isSkippable)
    const total = 2 ** skippable.length
    expect(total).toBe(131072)
    const masks = [
      0,
      total - 1,
      1,
      2,
      0x01555,
      0x0AAAA,
      0x12345,
    ]

    for (const mask of masks) {
      let state = applyTutorialTransition(INITIAL_TUTORIAL_STATE, {
        type: 'START',
        tutorialRunId: `run-exhaustive-${mask}`,
      })
      let skipPointer = 0
      while (state.status === 'IN_PROGRESS') {
        const step = TUTORIAL_STEPS.find((item) => item.id === state.stepId)
        const shouldSkip = step.isSkippable && (mask & (1 << skipPointer++)) !== 0
        const nextState = applyTutorialTransition(state, shouldSkip
          ? { type: 'SKIP_STEP' }
          : { type: 'COMPLETE_STEP', actionId: step.action.id })
        const validation = validateTutorialState(nextState)
        const scenario = getTutorialScenario(nextState)
        const invariants = tutorialScenarioInvariants(scenario)
        if (nextState === state || !validation.valid || !Object.values(invariants).every(Boolean)) {
          throw new Error(`Tutorial transition diverged at mask ${mask}, step ${step.id}: ${validation.reason || JSON.stringify(invariants)}`)
        }
        state = nextState
      }
      const scenario = getTutorialScenario(state)
      expect(state.status).toBe('COMPLETED')
      expect(state.stepId).toBe(TUTORIAL_STEPS.at(-1).id)
      expect(state.skippedStepIds.every((stepId) => skippable.some((step) => step.id === stepId))).toBe(true)
      expect(scenario.debt.originalHours).toBe(2)
      expect(scenario.repair.history[0].preserved).toBe(true)
    }
  })
})
