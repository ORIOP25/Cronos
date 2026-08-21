import { TUTORIAL_STEPS, TUTORIAL_VERSION } from './contracts'
import { simulationInvariants } from './simulationEngine'

export function createTutorialState(initialState, savedState) {
  if (!savedState || typeof savedState !== 'object') return initialState

  const validStatus = ['NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'SKIPPED'].includes(savedState.status)
  const currentStepIndex = savedState.currentStepIndex
  const validStep = TUTORIAL_STEPS.some((step) => step.id === savedState.stepId)
  const validRun = typeof savedState.tutorialRunId === 'string' && savedState.tutorialRunId.length > 0
  const validIndex = Number.isInteger(currentStepIndex) && currentStepIndex >= 0 && currentStepIndex < TUTORIAL_STEPS.length
  const validArrays = [savedState.skippedStepIds, savedState.completedStepIds].every(
    (value) => Array.isArray(value) && value.every((stepId) => TUTORIAL_STEPS.some((step) => step.id === stepId)),
  )
  const validSkippedSteps = Array.isArray(savedState.skippedStepIds) && savedState.skippedStepIds.every(
    (stepId) => TUTORIAL_STEPS.find((step) => step.id === stepId)?.isSkippable === true,
  )
  const validCompleted = typeof savedState.completed === 'boolean'
  const validData = savedState.simulationData && typeof savedState.simulationData === 'object'
  const validScenario = validData && Object.values(simulationInvariants(savedState.simulationData)).every(Boolean)
  if (
    savedState.version !== TUTORIAL_VERSION ||
    !validStatus ||
    !validStep ||
    !validRun ||
    !validIndex ||
    TUTORIAL_STEPS[currentStepIndex].id !== savedState.stepId ||
    !validArrays ||
    !validSkippedSteps ||
    !validCompleted ||
    !validData ||
    !validScenario
  ) {
    return initialState
  }

  return {
    ...initialState,
    ...savedState,
    chapter: TUTORIAL_STEPS[currentStepIndex].chapter,
    skippedSteps: savedState.skippedStepIds || [],
    completedSteps: savedState.completedStepIds || [],
  }
}

export function loadTutorialState(storage, key, initialState) {
  try {
    const raw = storage.getItem(key)
    return raw ? createTutorialState(initialState, JSON.parse(raw)) : initialState
  } catch (error) {
    console.error('Tutorial storage could not be read.', error)
    return initialState
  }
}

export function saveTutorialState(storage, key, state) {
  try {
    storage.setItem(key, JSON.stringify({
      version: TUTORIAL_VERSION,
      tutorialRunId: state.tutorialRunId,
      status: state.status,
      chapter: state.chapter,
      stepId: state.stepId,
      currentStepIndex: state.currentStepIndex,
      completed: state.completed,
      values: state.values,
      skippedStepIds: state.skippedStepIds,
      completedStepIds: state.completedSteps,
      simulationData: state.simulationData,
    }))
  } catch (error) {
    console.error('Tutorial storage could not be written.', error)
  }
}
