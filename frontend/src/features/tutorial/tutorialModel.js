import {
  TUTORIAL_STATUSES,
  TUTORIAL_STEPS,
  TUTORIAL_VERSION,
  getNextTutorialStep,
  getTutorialStep,
  getTutorialStepIndex,
} from './tutorialContent'

export const INITIAL_TUTORIAL_STATE = Object.freeze({
  version: TUTORIAL_VERSION,
  tutorialRunId: null,
  status: 'NOT_STARTED',
  stepId: TUTORIAL_STEPS[0].id,
})

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

export function createTutorialRunId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  const bytes = new Uint8Array(16)
  if (globalThis.crypto?.getRandomValues) globalThis.crypto.getRandomValues(bytes)
  else for (let index = 0; index < bytes.length; index += 1) bytes[index] = Math.floor(Math.random() * 256)
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

function isRunId(value) {
  // Test doubles may use deterministic identifiers. Production identifiers are UUIDs.
  return typeof value === 'string' && value.length > 0 && (UUID_PATTERN.test(value) || value.startsWith('run-'))
}

function reportInvalidTransition(state, action, reason) {
  console.error('Invalid tutorial transition.', {
    action: action?.type,
    expectedStepId: action?.expectedStepId,
    stepId: state?.stepId,
    reason,
  })
  return state
}

function getRequestedRunId(action) {
  if (Object.prototype.hasOwnProperty.call(action || {}, 'tutorialRunId')) return action.tutorialRunId
  if (Object.prototype.hasOwnProperty.call(action?.payload || {}, 'tutorialRunId')) return action.payload.tutorialRunId
  return undefined
}

function createStartedState(tutorialRunId) {
  return {
    ...INITIAL_TUTORIAL_STATE,
    tutorialRunId: tutorialRunId || createTutorialRunId(),
    status: 'IN_PROGRESS',
  }
}

function startWithRunId(state, action) {
  const requestedRunId = getRequestedRunId(action)
  const tutorialRunId = requestedRunId === undefined ? createTutorialRunId() : requestedRunId
  if (!isRunId(tutorialRunId)) return reportInvalidTransition(state, action, 'initialized state requires a UUID run id')
  return createStartedState(tutorialRunId)
}

function advance(state, action) {
  const currentStep = getTutorialStepContext(state)
  if (!currentStep) return reportInvalidTransition(state, action, 'current step does not exist')
  if (action.expectedStepId !== currentStep.id) {
    return reportInvalidTransition(state, action, 'expectedStepId does not match the current checkpoint')
  }

  const nextStep = getNextTutorialStep(currentStep.id)
  if (!nextStep) {
    return {
      version: TUTORIAL_VERSION,
      tutorialRunId: state.tutorialRunId,
      status: 'COMPLETED',
      stepId: currentStep.id,
    }
  }
  return {
    version: TUTORIAL_VERSION,
    tutorialRunId: state.tutorialRunId,
    status: 'IN_PROGRESS',
    stepId: nextStep.id,
  }
}

export function applyTutorialTransition(state = INITIAL_TUTORIAL_STATE, action) {
  if (!action) return state

  switch (action.type) {
    case 'START':
      if (state.status !== 'NOT_STARTED') return reportInvalidTransition(state, action, 'START requires NOT_STARTED')
      return startWithRunId(state, action)

    case 'ADVANCE':
      if (state.status !== 'IN_PROGRESS') return reportInvalidTransition(state, action, 'ADVANCE requires IN_PROGRESS')
      return advance(state, action)

    case 'EXIT':
      if (!['IN_PROGRESS', 'COMPLETED', 'SKIPPED'].includes(state.status)) {
        return reportInvalidTransition(state, action, 'EXIT requires an initialized visit')
      }
      return state

    case 'SKIP_TUTORIAL':
      if (state.status !== 'IN_PROGRESS') return reportInvalidTransition(state, action, 'SKIP_TUTORIAL requires IN_PROGRESS')
      return {
        ...state,
        status: 'SKIPPED',
      }

    case 'REPEAT':
      if (!['COMPLETED', 'SKIPPED'].includes(state.status)) {
        return reportInvalidTransition(state, action, 'REPEAT requires a completed or skipped tutorial')
      }
      return startWithRunId(state, action)

    case 'HYDRATE': {
      const candidate = action.payload
      const validation = validateTutorialState(candidate)
      if (!validation.valid) return reportInvalidTransition(state, action, validation.reason)
      return candidate
    }

    default:
      return reportInvalidTransition(state, action, 'unsupported action')
  }
}

export function tutorialReducer(state = INITIAL_TUTORIAL_STATE, action) {
  return applyTutorialTransition(state, action)
}

export function getTutorialProgressPercent(state) {
  if (state.status === 'COMPLETED') return 100
  const index = getTutorialStepIndex(state.stepId)
  if (index < 0) return 0
  return Math.round((index / TUTORIAL_STEPS.length) * 100)
}

export function deriveCompletedStepIds(state) {
  if (state.status === 'COMPLETED') return TUTORIAL_STEPS.map((step) => step.id)
  const index = getTutorialStepIndex(state.stepId)
  return index < 0 ? [] : TUTORIAL_STEPS.slice(0, index).map((step) => step.id)
}

export function isTutorialComplete(state) {
  return state.status === 'COMPLETED'
}

export function validateTutorialState(state) {
  if (!state || typeof state !== 'object' || Array.isArray(state)) {
    return { valid: false, reason: 'state is not an object' }
  }

  const allowedKeys = ['version', 'tutorialRunId', 'status', 'stepId']
  if (Object.keys(state).some((key) => !allowedKeys.includes(key))) {
    return { valid: false, reason: 'state contains fields outside the v3 contract' }
  }
  if (state.version !== TUTORIAL_VERSION) return { valid: false, reason: 'unsupported version' }
  if (!TUTORIAL_STATUSES.includes(state.status)) return { valid: false, reason: 'unsupported status' }
  if (!getTutorialStep(state.stepId)) return { valid: false, reason: 'step does not exist' }

  if (state.status === 'NOT_STARTED') {
    if (state.tutorialRunId !== null) return { valid: false, reason: 'NOT_STARTED requires a null run id' }
    if (state.stepId !== TUTORIAL_STEPS[0].id) return { valid: false, reason: 'NOT_STARTED must point to the first step' }
  } else if (!isRunId(state.tutorialRunId)) {
    return { valid: false, reason: 'initialized state requires a run id' }
  }

  if (state.status === 'COMPLETED' && state.stepId !== TUTORIAL_STEPS.at(-1).id) {
    return { valid: false, reason: 'COMPLETED must point to the last step' }
  }
  return { valid: true }
}

export function getTutorialStepContext(state) {
  return getTutorialStep(state.stepId)
}
