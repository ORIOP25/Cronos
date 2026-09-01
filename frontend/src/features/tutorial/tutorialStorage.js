import {
  TUTORIAL_VERSION,
  TUTORIAL_STEPS,
  getLegacyTutorialStorageKey,
} from './tutorialContent'
import { validateTutorialState } from './tutorialModel'

const PERSISTED_KEYS = ['version', 'tutorialRunId', 'status', 'stepId']

function rejectState(initialState, savedState, reason) {
  console.error('Tutorial storage state rejected.', { reason, savedState })
  return initialState
}

export function serializeTutorialState(state) {
  return Object.fromEntries(PERSISTED_KEYS.map((key) => [key, state[key]]))
}

export function createTutorialState(initialState, savedState) {
  if (!savedState || typeof savedState !== 'object' || Array.isArray(savedState)) {
    return rejectState(initialState, savedState, 'state must be an object')
  }

  if (!isValidTutorialStepId(savedState.stepId)) {
    return rejectState(initialState, savedState, 'step does not exist')
  }
  const validation = validateTutorialState(savedState)
  if (!validation.valid) return rejectState(initialState, savedState, validation.reason)
  return serializeTutorialState(savedState)
}

export function loadTutorialState(storage, key, initialState) {
  if (!key || !storage) return initialState
  try {
    const raw = storage.getItem(key)
    return raw ? createTutorialState(initialState, JSON.parse(raw)) : initialState
  } catch (error) {
    console.error('Tutorial storage could not be read.', { key, error })
    return initialState
  }
}

export function saveTutorialState(storage, key, state) {
  if (!key || !storage) {
    const error = new Error('Tutorial identity is unavailable; progress was not persisted.')
    console.error('Tutorial storage could not be written.', { key, error })
    return { ok: false, error }
  }
  try {
    storage.setItem(key, JSON.stringify(serializeTutorialState(state)))
    return { ok: true }
  } catch (error) {
    console.error('Tutorial storage could not be written.', { key, error })
    return { ok: false, error }
  }
}

export function hasLegacyTutorialState(storage, userId, organizationId) {
  const key = getLegacyTutorialStorageKey(userId, organizationId)
  if (!key || !storage) return false
  try {
    return storage.getItem(key) !== null
  } catch (error) {
    console.error('Legacy tutorial storage could not be inspected.', { key, error })
    return false
  }
}

export function isValidTutorialStepId(stepId) {
  return TUTORIAL_STEPS.some((step) => step.id === stepId)
}

export { TUTORIAL_VERSION }
