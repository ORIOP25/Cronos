import { TUTORIAL_VERSION, TUTORIAL_STEPS } from './tutorialScenario'
import { validateTutorialState } from './tutorialModel'

const PERSISTED_STATUSES = new Set(['NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'SKIPPED'])

function rejectState(initialState, savedState, reason) {
  console.error('Tutorial storage state rejected.', { reason, savedState })
  return initialState
}
export function createTutorialState(initialState, savedState) {
  if (!savedState || typeof savedState !== 'object' || Array.isArray(savedState)) {
    return rejectState(initialState, savedState, 'state must be an object')
  }
  if (savedState.version !== TUTORIAL_VERSION) return rejectState(initialState, savedState, 'version is not supported')
  if (!PERSISTED_STATUSES.has(savedState.status)) return rejectState(initialState, savedState, 'status is not supported')
  if (savedState.status !== 'NOT_STARTED' && (typeof savedState.tutorialRunId !== 'string' || savedState.tutorialRunId.length === 0)) {
    return rejectState(initialState, savedState, 'active state requires tutorialRunId')
  }
  if (savedState.status === 'NOT_STARTED' && savedState.tutorialRunId !== null && savedState.tutorialRunId !== undefined) {
    return rejectState(initialState, savedState, 'NOT_STARTED cannot have tutorialRunId')
  }
  if (!TUTORIAL_STEPS.some((step) => step.id === savedState.stepId)) return rejectState(initialState, savedState, 'stepId does not exist')
  if (!Number.isInteger(savedState.chapter)) return rejectState(initialState, savedState, 'chapter must be an integer')
  if (!Array.isArray(savedState.skippedStepIds)) return rejectState(initialState, savedState, 'skippedStepIds must be an array')
  if (!savedState.values || typeof savedState.values !== 'object' || Array.isArray(savedState.values)) return rejectState(initialState, savedState, 'values must be an object')

  const candidate = {
    version: TUTORIAL_VERSION,
    tutorialRunId: savedState.tutorialRunId ?? null,
    status: savedState.status,
    chapter: savedState.chapter,
    stepId: savedState.stepId,
    values: savedState.values,
    skippedStepIds: savedState.skippedStepIds,
  }
  const validation = validateTutorialState(candidate)
  if (!validation.valid) return rejectState(initialState, savedState, validation.reason)
  return candidate
}

export function loadTutorialState(storage, key, initialState) {
  try {
    const raw = storage?.getItem(key)
    return raw ? createTutorialState(initialState, JSON.parse(raw)) : initialState
  } catch (error) {
    console.error('Tutorial storage could not be read.', { key, error })
    return initialState
  }
}

export function serializeTutorialState(state) {
  return {
    version: TUTORIAL_VERSION,
    tutorialRunId: state.tutorialRunId ?? null,
    status: state.status,
    chapter: state.chapter,
    stepId: state.stepId,
    values: state.values || {},
    skippedStepIds: state.skippedStepIds || [],
  }
}

export function saveTutorialState(storage, key, state) {
  try {
    storage?.setItem(key, JSON.stringify(serializeTutorialState(state)))
    return { ok: true }
  } catch (error) {
    console.error('Tutorial storage could not be written.', { key, error })
    return { ok: false, error }
  }
}
