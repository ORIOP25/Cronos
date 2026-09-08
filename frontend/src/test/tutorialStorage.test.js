import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  TUTORIAL_STEPS,
  TUTORIAL_VERSION,
  getTutorialStorageKey,
} from '../features/tutorial/tutorialContent'
import { INITIAL_TUTORIAL_STATE, applyTutorialTransition } from '../features/tutorial/tutorialModel'
import {
  createTutorialState,
  loadTutorialState,
  saveTutorialState,
  serializeTutorialState,
} from '../features/tutorial/tutorialStorage'

describe('tutorialStorage v3', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('persists exactly the minimum resumable state', () => {
    const state = applyTutorialTransition(INITIAL_TUTORIAL_STATE, { type: 'START', tutorialRunId: 'run-1' })
    const next = applyTutorialTransition(state, { type: 'ADVANCE', expectedStepId: TUTORIAL_STEPS[0].id })
    const key = getTutorialStorageKey('user_1', 'org_1')

    expect(saveTutorialState(localStorage, key, next)).toEqual({ ok: true })
    const envelope = JSON.parse(localStorage.getItem(key))
    expect(envelope.value).toEqual({
      version: TUTORIAL_VERSION,
      tutorialRunId: 'run-1',
      status: 'IN_PROGRESS',
      stepId: 'courses_classes',
    })
    expect(envelope.expiresAt).toBeGreaterThan(Date.now())
    expect(Object.keys(envelope.value)).toHaveLength(4)
    expect(loadTutorialState(localStorage, key, INITIAL_TUTORIAL_STATE)).toEqual(envelope.value)
    expect(serializeTutorialState({ ...next, values: { ignored: true } })).not.toHaveProperty('values')
  })

  it('rejects malformed or legacy-shaped v3 state', () => {
    const key = getTutorialStorageKey('user_1', 'org_1')
    localStorage.setItem(key, JSON.stringify({
      version: 3,
      tutorialRunId: 'run-1',
      status: 'IN_PROGRESS',
      stepId: 'curriculum',
      chapter: 1,
    }))
    expect(loadTutorialState(localStorage, key, INITIAL_TUTORIAL_STATE)).toBe(INITIAL_TUTORIAL_STATE)
    localStorage.setItem(key, '{invalid-json')
    expect(loadTutorialState(localStorage, key, INITIAL_TUTORIAL_STATE)).toBe(INITIAL_TUTORIAL_STATE)
    expect(localStorage.getItem(key)).toBeNull()
  })

  it('requires authenticated user and organization identity for persistence', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(getTutorialStorageKey(null, 'org_1')).toBeNull()
    expect(getTutorialStorageKey('user_1', null)).toBeNull()
    expect(saveTutorialState(localStorage, null, INITIAL_TUTORIAL_STATE).ok).toBe(false)
    expect(localStorage.length).toBe(0)
  })

  it('uses only the v3 key and does not read unrelated storage', () => {
    const unrelatedKey = 'cronos:tutorial:v2:user:user_1:org:org_1'
    localStorage.setItem(unrelatedKey, JSON.stringify({ old: true }))
    expect(loadTutorialState(localStorage, getTutorialStorageKey('user_1', 'org_1'), INITIAL_TUTORIAL_STATE)).toBe(INITIAL_TUTORIAL_STATE)
    expect(localStorage.getItem(unrelatedKey)).toBe(JSON.stringify({ old: true }))
  })

  it('validates the initial state as a valid not-started checkpoint', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(createTutorialState(INITIAL_TUTORIAL_STATE, INITIAL_TUTORIAL_STATE)).toEqual(INITIAL_TUTORIAL_STATE)
    expect(createTutorialState(INITIAL_TUTORIAL_STATE, {
      ...INITIAL_TUTORIAL_STATE,
      status: 'IN_PROGRESS',
    })).toBe(INITIAL_TUTORIAL_STATE)
  })
})
