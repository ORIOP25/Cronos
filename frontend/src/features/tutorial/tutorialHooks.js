import { useReducer, useEffect, useCallback } from 'react'
import { useUser } from '@clerk/react'
import { TUTORIAL_STEPS, getTutorialStorageKey as buildTutorialStorageKey } from './contracts'
import { simulationReducer, INITIAL_SIMULATION_STATE } from './simulationEngine'
import { sendTutorialTelemetryEvent } from './tutorialTelemetry'
import { loadTutorialState, saveTutorialState } from './tutorialStorage'

function createTutorialRunId() {
  return globalThis.crypto?.randomUUID?.() || `run-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export function useTutorialSimulation({ orgId, userId } = {}) {
  const { user } = useUser()
  const effectiveUserId = userId || user?.id
  const storageKey = buildTutorialStorageKey(effectiveUserId, orgId)

  const [state, dispatch] = useReducer(simulationReducer, INITIAL_SIMULATION_STATE, (initial) => {
    return loadTutorialState(localStorage, storageKey, initial)
  })

  useEffect(() => {
    const saved = loadTutorialState(localStorage, storageKey, INITIAL_SIMULATION_STATE)
    dispatch({ type: 'HYDRATE_TUTORIAL', payload: saved, storageKey })
  }, [storageKey])

  useEffect(() => {
    if (state.hydratedStorageKey === storageKey) saveTutorialState(localStorage, storageKey, state)
  }, [state, storageKey])

  const currentStep = TUTORIAL_STEPS[state.currentStepIndex] || TUTORIAL_STEPS[0]
  const progressPercent = Math.round(((state.currentStepIndex + 1) / TUTORIAL_STEPS.length) * 100)

  const openTutorial = useCallback(() => {
    const runId = state.status === 'IN_PROGRESS' ? state.tutorialRunId : createTutorialRunId()
    const action = { type: 'OPEN_TUTORIAL', payload: { tutorialRunId: runId, resume: state.status === 'IN_PROGRESS' } }
    const nextState = simulationReducer(state, action)
    saveTutorialState(localStorage, storageKey, nextState)
    dispatch(action)
    void sendTutorialTelemetryEvent({
      tutorialRunId: runId,
      eventName: 'tutorial_opened',
      chapter: nextState.chapter,
      stepId: nextState.stepId,
    })
  }, [state, storageKey])

  const nextStep = useCallback(() => {
    const action = { type: 'NEXT_STEP' }
    const nextState = simulationReducer(state, action)
    saveTutorialState(localStorage, storageKey, nextState)
    const isLast = state.currentStepIndex >= TUTORIAL_STEPS.length - 1
    dispatch(action)
    if (isLast) {
      void sendTutorialTelemetryEvent({
        tutorialRunId: state.tutorialRunId,
        eventName: 'tutorial_completed',
        chapter: nextState.chapter,
        stepId: nextState.stepId,
      })
    } else {
      const nextStepObj = TUTORIAL_STEPS[nextState.currentStepIndex]
      if (nextStepObj && nextStepObj.chapter !== currentStep.chapter) {
        void sendTutorialTelemetryEvent({
          tutorialRunId: state.tutorialRunId,
          eventName: 'chapter_started',
          chapter: nextStepObj.chapter,
          stepId: nextStepObj.id,
        })
      }
    }
  }, [state, storageKey, currentStep])

  const prevStep = useCallback(() => {
    const action = { type: 'PREV_STEP' }
    saveTutorialState(localStorage, storageKey, simulationReducer(state, action))
    dispatch(action)
  }, [state, storageKey])

  const skipStep = useCallback(() => {
    if (!currentStep.isSkippable) return
    void sendTutorialTelemetryEvent({
      tutorialRunId: state.tutorialRunId,
      eventName: 'step_skipped',
      chapter: currentStep.chapter,
      stepId: currentStep.id,
    })
    const action = { type: 'SKIP_STEP' }
    saveTutorialState(localStorage, storageKey, simulationReducer(state, action))
    dispatch(action)
  }, [state, storageKey, currentStep])

  const exitTutorial = useCallback(() => {
    void sendTutorialTelemetryEvent({
      tutorialRunId: state.tutorialRunId,
      eventName: 'tutorial_exited',
      chapter: currentStep.chapter,
      stepId: currentStep.id,
    })
    const action = { type: 'EXIT_TUTORIAL' }
    saveTutorialState(localStorage, storageKey, simulationReducer(state, action))
    dispatch(action)
  }, [state, storageKey, currentStep])

  const skipTutorial = useCallback(() => {
    void sendTutorialTelemetryEvent({
      tutorialRunId: state.tutorialRunId,
      eventName: 'tutorial_exited',
      chapter: currentStep.chapter,
      stepId: currentStep.id,
    })
    const action = { type: 'SKIP_TUTORIAL' }
    saveTutorialState(localStorage, storageKey, simulationReducer(state, action))
    dispatch(action)
  }, [state, storageKey, currentStep])

  const completeTutorial = useCallback(() => {
    void sendTutorialTelemetryEvent({
      tutorialRunId: state.tutorialRunId,
      eventName: 'tutorial_completed',
      chapter: currentStep.chapter,
      stepId: currentStep.id,
    })
    const action = { type: 'COMPLETE_TUTORIAL' }
    saveTutorialState(localStorage, storageKey, simulationReducer(state, action))
    dispatch(action)
  }, [state, storageKey, currentStep])

  const repeatTutorial = useCallback(() => {
    const runId = createTutorialRunId()
    const action = { type: 'REPEAT_TUTORIAL', payload: { tutorialRunId: runId } }
    const nextState = simulationReducer(state, action)
    saveTutorialState(localStorage, storageKey, nextState)
    dispatch(action)
    void sendTutorialTelemetryEvent({ tutorialRunId: runId, eventName: 'tutorial_repeated', chapter: 1, stepId: TUTORIAL_STEPS[0].id })
  }, [state, storageKey])

  return {
    isOpen: state.isOpen,
    isHydrated: state.hydratedStorageKey === storageKey,
    currentStepIndex: state.currentStepIndex,
    currentStep,
    totalSteps: TUTORIAL_STEPS.length,
    progressPercent,
    completed: state.completed,
    status: state.status,
    tutorialRunId: state.tutorialRunId,
    skippedSteps: state.skippedSteps,
    simulationData: state.simulationData,
    openTutorial,
    nextStep,
    prevStep,
    skipStep,
    exitTutorial,
    skipTutorial,
    completeTutorial,
    repeatTutorial,
  }
}
