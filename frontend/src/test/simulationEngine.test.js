import { describe, expect, it } from 'vitest'
import { TUTORIAL_STEPS } from '../features/tutorial/tutorialScenario'
import { INITIAL_TUTORIAL_STATE, applyTutorialTransition, getTutorialScenario } from '../features/tutorial/tutorialModel'

describe('Tutorial model transitions', () => {
  it('starts at the first step without an open-state concern', () => {
    const state = applyTutorialTransition(INITIAL_TUTORIAL_STATE, { type: 'START', tutorialRunId: 'run-1' })
    expect(state).toMatchObject({ tutorialRunId: 'run-1', status: 'IN_PROGRESS', stepId: 'structure_overview', chapter: 1 })
    expect(state).not.toHaveProperty('isOpen')
  })

  it('applies a skip as the same local result as the main action', () => {
    const started = applyTutorialTransition(INITIAL_TUTORIAL_STATE, { type: 'START', tutorialRunId: 'run-1' })
    const afterIntro = applyTutorialTransition(started, { type: 'COMPLETE_STEP', actionId: 'continue' })
    const skipped = applyTutorialTransition(afterIntro, { type: 'SKIP_STEP' })
    const completed = applyTutorialTransition(afterIntro, { type: 'COMPLETE_STEP', actionId: 'save-subject' })
    expect(skipped.stepId).toBe(completed.stepId)
    expect(skipped.values).toEqual(completed.values)
    expect(getTutorialScenario(skipped).workflow.subjectCreated).toBe(true)
  })

  it('marks the final action as completed', () => {
    const state = {
      ...INITIAL_TUTORIAL_STATE,
      tutorialRunId: 'run-last',
      status: 'IN_PROGRESS',
      chapter: 2,
      stepId: TUTORIAL_STEPS.at(-1).id,
    }
    const completed = applyTutorialTransition(state, { type: 'COMPLETE_STEP', actionId: 'approve-repair' })
    expect(completed.status).toBe('COMPLETED')
    expect(completed.stepId).toBe('repair_approve')
    expect(getTutorialScenario(completed).workflow.repairApproved).toBe(true)
  })
})
