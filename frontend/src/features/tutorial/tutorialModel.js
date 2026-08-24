import {
  TUTORIAL_STEPS,
  TUTORIAL_STATUSES,
  TUTORIAL_VERSION,
  getTutorialStep,
  getTutorialStepIndex,
  getNextTutorialStep,
  tutorialScenarioInvariants,
  createTutorialScenario,
  normalizeTutorialChanges,
} from './tutorialScenario'

export const INITIAL_TUTORIAL_STATE = Object.freeze({
  version: TUTORIAL_VERSION,
  tutorialRunId: null,
  status: 'NOT_STARTED',
  chapter: 1,
  stepId: TUTORIAL_STEPS[0].id,
  values: {},
  skippedStepIds: [],
})

function createRunId() {
  return globalThis.crypto?.randomUUID?.() || `run-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function createStartedState(tutorialRunId = createRunId()) {
  return {
    ...INITIAL_TUTORIAL_STATE,
    tutorialRunId,
    status: 'IN_PROGRESS',
  }
}

function getActionId(action) {
  return action?.actionId || action?.action?.id || action?.payload?.actionId || action?.payload?.id || action?.payload?.action?.id || null
}

function reportInvalidTransition(state, action, reason) {
  console.error('Invalid tutorial transition.', {
    action: action?.type,
    actionId: getActionId(action),
    stepId: state?.stepId,
    reason,
  })
  return state
}

function advanceState(state, step, values) {
  const nextStep = getNextTutorialStep(step.id)
  if (!nextStep) {
    return {
      ...state,
      version: TUTORIAL_VERSION,
      status: 'COMPLETED',
      chapter: step.chapter,
      stepId: step.id,
      values,
    }
  }
  return {
    ...state,
    version: TUTORIAL_VERSION,
    status: 'IN_PROGRESS',
    chapter: nextStep.chapter,
    stepId: nextStep.id,
    values,
  }
}

function completeCurrentStep(state, action) {
  const step = getTutorialStep(state.stepId)
  if (!step) return reportInvalidTransition(state, action, 'current step does not exist')
  const actionId = getActionId(action)
  if (step.action.id !== actionId) {
    return reportInvalidTransition(state, action, `expected ${step.action.id}`)
  }
  const changes = normalizeTutorialChanges(
    step.id,
    action.changes ?? action.payload?.changes ?? action.payload?.value ?? {},
  )
  if (changes === null) return reportInvalidTransition(state, action, 'changes are not valid for the current step')
  const values = { ...state.values }
  if (Object.keys(changes).length > 0) values[step.id] = { completed: true, ...changes }
  return advanceState(state, step, values)
}

export function applyTutorialTransition(state = INITIAL_TUTORIAL_STATE, action) {
  if (!action) return state

  switch (action.type) {
    case 'START': {
      if (state.status === 'IN_PROGRESS') return state
      return createStartedState(action.tutorialRunId || action.payload?.tutorialRunId)
    }

    case 'COMPLETE_STEP':
      if (state.status !== 'IN_PROGRESS') return reportInvalidTransition(state, action, 'tutorial is not in progress')
      return completeCurrentStep(state, action)

    case 'COMPLETE_SEQUENCE': {
      if (state.status !== 'IN_PROGRESS') return reportInvalidTransition(state, action, 'tutorial is not in progress')
      const completions = action.completions || (action.actionIds || []).map((actionId) => ({ actionId }))
      let candidate = state
      for (const completion of completions) {
        const next = completeCurrentStep(candidate, {
          type: 'COMPLETE_STEP',
          actionId: completion.actionId,
          changes: completion.changes,
        })
        if (next === candidate) return state
        candidate = next
      }
      return candidate
    }

    case 'SKIP_STEP': {
      const step = getTutorialStep(state.stepId)
      if (state.status !== 'IN_PROGRESS') return reportInvalidTransition(state, action, 'tutorial is not in progress')
      if (!step) return reportInvalidTransition(state, action, 'current step does not exist')
      if (!step.isSkippable) return reportInvalidTransition(state, action, 'current step is mandatory')
      const skippedStepIds = state.skippedStepIds.includes(step.id)
        ? state.skippedStepIds
        : [...state.skippedStepIds, step.id]
      return advanceState(
        { ...state, skippedStepIds },
        step,
        state.values,
      )
    }

    case 'EXIT':
      return state

    case 'SKIP_TUTORIAL':
      return {
        ...state,
        tutorialRunId: state.tutorialRunId || createRunId(),
        status: 'SKIPPED',
      }

    case 'REPEAT':
      return createStartedState(action.tutorialRunId || action.payload?.tutorialRunId)

    default:
      return reportInvalidTransition(state, action, 'unsupported action')
  }
}

export function tutorialReducer(state = INITIAL_TUTORIAL_STATE, action) {
  if (action?.type === 'HYDRATE') {
    const payload = action.payload || state
    return { ...payload, values: { ...payload.values }, skippedStepIds: [...payload.skippedStepIds] }
  }
  return applyTutorialTransition(state, action)
}

export function deriveCompletedStepIds(state) {
  const index = getTutorialStepIndex(state.stepId)
  const end = state.status === 'COMPLETED' ? TUTORIAL_STEPS.length : Math.max(0, index)
  return TUTORIAL_STEPS
    .slice(0, end)
    .map((step) => step.id)
    .filter((stepId) => !state.skippedStepIds.includes(stepId) || state.values?.[stepId]?.completed)
}

export function getTutorialScenario(state) {
  return createTutorialScenario(state)
}

export function isTutorialComplete(state) {
  return state.status === 'COMPLETED'
}

export function validateTutorialState(state) {
  if (!state || typeof state !== 'object') return { valid: false, reason: 'state is not an object' }
  if (state.version !== TUTORIAL_VERSION) return { valid: false, reason: 'unsupported version' }
  if (!TUTORIAL_STATUSES.includes(state.status)) return { valid: false, reason: 'unsupported status' }
  if (state.status === 'NOT_STARTED') {
    if (state.tutorialRunId !== null && state.tutorialRunId !== undefined) return { valid: false, reason: 'NOT_STARTED cannot have a run id' }
  } else if (typeof state.tutorialRunId !== 'string' || state.tutorialRunId.length === 0) {
    return { valid: false, reason: 'active state requires a run id' }
  }
  const step = getTutorialStep(state.stepId)
  if (!step) return { valid: false, reason: 'step does not exist' }
  if (state.chapter !== step.chapter) return { valid: false, reason: 'chapter does not match step' }
  if (state.status === 'NOT_STARTED' && (state.stepId !== TUTORIAL_STEPS[0].id || state.chapter !== 1)) return { valid: false, reason: 'NOT_STARTED must point to the first step' }
  if (state.status === 'COMPLETED' && state.stepId !== TUTORIAL_STEPS.at(-1).id) return { valid: false, reason: 'COMPLETED must point to the last step' }
  if (!Array.isArray(state.skippedStepIds)) return { valid: false, reason: 'skippedStepIds must be an array' }
  if (new Set(state.skippedStepIds).size !== state.skippedStepIds.length) return { valid: false, reason: 'skippedStepIds must be unique' }
  if (state.skippedStepIds.some((stepId) => !getTutorialStep(stepId)?.isSkippable)) return { valid: false, reason: 'mandatory step was skipped' }
  if (!state.values || typeof state.values !== 'object' || Array.isArray(state.values)) return { valid: false, reason: 'values must be an object' }
  for (const [stepId, value] of Object.entries(state.values)) {
    if (!getTutorialStep(stepId)) return { valid: false, reason: 'values contain an unknown step' }
    if (!value || typeof value !== 'object' || Array.isArray(value) || value.completed !== true) {
      return { valid: false, reason: 'step values must be normalized objects' }
    }
    for (const scalar of Object.values(value)) {
      if (typeof scalar === 'string' && scalar.length > 120) return { valid: false, reason: 'step value is too long' }
      if (Array.isArray(scalar) || (scalar && typeof scalar === 'object')) return { valid: false, reason: 'step value contains an unexpected object' }
    }
  }
  const scenario = getTutorialScenario(state)
  if (!Object.values(tutorialScenarioInvariants(scenario)).every(Boolean)) return { valid: false, reason: 'scenario invariants failed' }
  return { valid: true }
}
