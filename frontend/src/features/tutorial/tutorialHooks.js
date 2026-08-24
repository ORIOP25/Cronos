import { useCallback, useEffect, useReducer, useState } from 'react'
import { useUser } from '@clerk/react'
import { getTutorialStorageKey, TUTORIAL_STEPS } from './tutorialScenario'
import { INITIAL_TUTORIAL_STATE, deriveCompletedStepIds, getTutorialScenario, isTutorialComplete, tutorialReducer } from './tutorialModel'
import { loadTutorialState, saveTutorialState } from './tutorialStorage'
import { sendTutorialTelemetryEvent } from './tutorialTelemetry'

function createTutorialRunId() {
  return globalThis.crypto?.randomUUID?.() || `run-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function getStorage() {
  return globalThis.localStorage
}

export function useTutorialSimulation({ orgId, userId } = {}) {
  const { user } = useUser()
  const effectiveUserId = userId || user?.id
  const storageKey = getTutorialStorageKey(effectiveUserId, orgId)
  const [isOpen, setIsOpen] = useState(false)
  const [hydratedStorageKey, setHydratedStorageKey] = useState(null)
  const [persistenceError, setPersistenceError] = useState(null)
  const [state, dispatch] = useReducer(
    tutorialReducer,
    INITIAL_TUTORIAL_STATE,
    (initialState) => loadTutorialState(getStorage(), storageKey, initialState),
  )

  useEffect(() => {
    const savedState = loadTutorialState(getStorage(), storageKey, INITIAL_TUTORIAL_STATE)
    dispatch({ type: 'HYDRATE', payload: savedState })
    const hydrationTimer = window.setTimeout(() => setHydratedStorageKey(storageKey), 0)
    return () => window.clearTimeout(hydrationTimer)
  }, [storageKey])

  const currentStepIndex = Math.max(0, TUTORIAL_STEPS.findIndex((step) => step.id === state.stepId))
  const currentStep = TUTORIAL_STEPS[currentStepIndex] || TUTORIAL_STEPS[0]
  const completed = isTutorialComplete(state)
  const progressPercent = Math.round(((completed ? TUTORIAL_STEPS.length : currentStepIndex + 1) / TUTORIAL_STEPS.length) * 100)
  const scenario = getTutorialScenario(state)

  const persist = useCallback((nextState) => {
    const result = saveTutorialState(getStorage(), storageKey, nextState)
    setPersistenceError(result.ok ? null : result.error)
    return nextState
  }, [storageKey])

  const emit = useCallback((eventName, eventState = state, step = currentStep) => {
    void sendTutorialTelemetryEvent({
      tutorialRunId: eventState.tutorialRunId,
      eventName,
      chapter: step?.chapter ?? eventState.chapter,
      stepId: step?.id ?? eventState.stepId,
    })
  }, [currentStep, state])

  const startTutorial = useCallback(() => {
    if (state.status === 'IN_PROGRESS') {
      setIsOpen(true)
      return state
    }
    const action = { type: 'START', tutorialRunId: createTutorialRunId() }
    const nextState = tutorialReducer(state, action)
    persist(nextState)
    dispatch(action)
    setIsOpen(true)
    emit('tutorial_opened', nextState, TUTORIAL_STEPS[0])
    return nextState
  }, [emit, persist, state])

  const openTutorial = useCallback(() => {
    if (state.status === 'NOT_STARTED') return startTutorial()
    if (!isOpen && state.status === 'IN_PROGRESS') emit('tutorial_opened', state, currentStep)
    setIsOpen(true)
    return state
  }, [currentStep, emit, isOpen, startTutorial, state])

  const completeCurrentAction = useCallback((actionId, changes = {}) => {
    const action = { type: 'COMPLETE_STEP', actionId, changes }
    const nextState = tutorialReducer(state, action)
    if (nextState === state) return false
    persist(nextState)
    dispatch(action)
    if (nextState.status === 'COMPLETED') {
      setIsOpen(false)
      emit('tutorial_completed', nextState, currentStep)
    } else if (nextState.chapter !== state.chapter) {
      emit('chapter_started', nextState, TUTORIAL_STEPS[currentStepIndex + 1])
    }
    return true
  }, [currentStep, currentStepIndex, emit, persist, state])

  const completeActionSequence = useCallback((completions) => {
    const action = {
      type: 'COMPLETE_SEQUENCE',
      completions: completions.map((completion) => typeof completion === 'string' ? { actionId: completion } : completion),
    }
    const nextState = tutorialReducer(state, action)
    if (nextState === state) return false
    persist(nextState)
    dispatch(action)
    if (nextState.status === 'COMPLETED') {
      setIsOpen(false)
      emit('tutorial_completed', nextState, currentStep)
    } else if (nextState.chapter !== state.chapter) {
      emit('chapter_started', nextState, TUTORIAL_STEPS.find((step) => step.id === nextState.stepId))
    }
    return true
  }, [currentStep, emit, persist, state])

  const skipStep = useCallback(() => {
    if (!currentStep.isSkippable) return false
    const action = { type: 'SKIP_STEP' }
    const nextState = tutorialReducer(state, action)
    if (nextState === state) return false
    persist(nextState)
    dispatch(action)
    emit('step_skipped', state, currentStep)
    if (nextState.chapter !== state.chapter) emit('chapter_started', nextState, TUTORIAL_STEPS[currentStepIndex + 1])
    return true
  }, [currentStep, currentStepIndex, emit, persist, state])

  const exitTutorial = useCallback(() => {
    const action = { type: 'EXIT' }
    const nextState = tutorialReducer(state, action)
    persist(nextState)
    dispatch(action)
    setIsOpen(false)
    emit('tutorial_exited', state, currentStep)
  }, [currentStep, emit, persist, state])

  const skipTutorial = useCallback(() => {
    const action = { type: 'SKIP_TUTORIAL' }
    const nextState = tutorialReducer(state, action)
    persist(nextState)
    dispatch(action)
    setIsOpen(false)
    emit('tutorial_exited', state, currentStep)
  }, [currentStep, emit, persist, state])

  const continueLater = useCallback(() => {
    if (currentStep.id !== 'chapter_transition') return false
    const action = { type: 'SKIP_STEP' }
    const nextState = tutorialReducer(state, action)
    if (nextState === state) return false
    persist(nextState)
    dispatch(action)
    setIsOpen(false)
    emit('step_skipped', state, currentStep)
    emit('tutorial_exited', nextState, TUTORIAL_STEPS[currentStepIndex + 1])
    return true
  }, [currentStep, currentStepIndex, emit, persist, state])

  const repeatTutorial = useCallback(() => {
    const action = { type: 'REPEAT', tutorialRunId: createTutorialRunId() }
    const nextState = tutorialReducer(state, action)
    persist(nextState)
    dispatch(action)
    setIsOpen(true)
    emit('tutorial_repeated', nextState, TUTORIAL_STEPS[0])
    emit('tutorial_opened', nextState, TUTORIAL_STEPS[0])
    return nextState
  }, [emit, persist, state])

  return {
    isOpen,
    isHydrated: hydratedStorageKey === storageKey,
    status: state.status,
    tutorialRunId: state.tutorialRunId,
    chapter: state.chapter,
    stepId: state.stepId,
    currentStepIndex,
    currentStep,
    totalSteps: TUTORIAL_STEPS.length,
    progressPercent,
    values: state.values,
    skippedStepIds: state.skippedStepIds,
    completedStepIds: deriveCompletedStepIds(state),
    completed,
    scenario,
    simulationData: scenario,
    startTutorial,
    openTutorial,
    completeCurrentAction,
    completeActionSequence,
    onAction: completeCurrentAction,
    skipStep,
    exitTutorial,
    skipTutorial,
    continueLater,
    repeatTutorial,
    persistenceError,
  }
}
