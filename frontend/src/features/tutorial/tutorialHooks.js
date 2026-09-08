import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { useOrganization, useUser } from '@clerk/react'
import {
  TUTORIAL_STEPS,
  getTutorialStorageKey,
  getTutorialStep,
} from './tutorialContent'
import {
  INITIAL_TUTORIAL_STATE,
  deriveCompletedStepIds,
  getTutorialProgressPercent,
  isTutorialComplete,
  tutorialReducer,
} from './tutorialModel'
import {
  loadTutorialState,
  saveTutorialState,
} from './tutorialStorage'
import { createTutorialScenario } from './tutorialScenario'

function getStorage() {
  return globalThis.localStorage
}

export function useTutorialSimulation({ orgId, userId } = {}) {
  const { organization } = useOrganization()
  const { user } = useUser()
  const effectiveUserId = userId ?? user?.id
  const effectiveOrgId = orgId ?? organization?.id
  const storageKey = getTutorialStorageKey(effectiveUserId, effectiveOrgId)
  const [isOpen, setIsOpen] = useState(false)
  const [hydratedStorageKey, setHydratedStorageKey] = useState(null)
  const [persistenceError, setPersistenceError] = useState(null)
  const [state, dispatch] = useReducer(
    tutorialReducer,
    INITIAL_TUTORIAL_STATE,
    (initialState) => loadTutorialState(getStorage(), storageKey, initialState),
  )
  const stateRef = useRef(state)
  const isOpenRef = useRef(isOpen)

  useEffect(() => {
    stateRef.current = state
    isOpenRef.current = isOpen
  }, [isOpen, state])

  useEffect(() => {
    // Hydrate persisted external state when the authenticated scope changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsOpen(false)
    isOpenRef.current = false
    setHydratedStorageKey(null)
    const loaded = loadTutorialState(getStorage(), storageKey, INITIAL_TUTORIAL_STATE)
    stateRef.current = loaded
    dispatch({ type: 'HYDRATE', payload: loaded })
    const hydrationTimer = globalThis.setTimeout(() => setHydratedStorageKey(storageKey), 0)
    return () => globalThis.clearTimeout(hydrationTimer)
  }, [effectiveOrgId, effectiveUserId, storageKey])

  const currentStepIndex = Math.max(0, TUTORIAL_STEPS.findIndex((step) => step.id === state.stepId))
  const currentStep = TUTORIAL_STEPS[currentStepIndex] || TUTORIAL_STEPS[0]
  const completed = isTutorialComplete(state)
  const progressPercent = getTutorialProgressPercent(state)
  const scenario = useMemo(() => createTutorialScenario(currentStep.id), [currentStep.id])

  const persist = useCallback((nextState) => {
    const result = saveTutorialState(getStorage(), storageKey, nextState)
    setPersistenceError(result.ok ? null : result.error)
    return result
  }, [storageKey])

  const transition = useCallback((action, { force = false, open = false, close = false } = {}) => {
    const current = stateRef.current
    const next = tutorialReducer(current, action)
    if (next === current && !force) return false

    const persistence = persist(next)
    stateRef.current = next
    if (next !== current) dispatch({ type: 'HYDRATE', payload: next })
    if (open) {
      isOpenRef.current = true
      setIsOpen(true)
    }
    if (close) {
      isOpenRef.current = false
      setIsOpen(false)
    }
    void persistence
    return next
  }, [persist])

  const startTutorial = useCallback(() => {
    const current = stateRef.current
    if (current.status === 'IN_PROGRESS') {
      isOpenRef.current = true
      setIsOpen(true)
      return current
    }
    if (current.status !== 'NOT_STARTED') return current
    const next = transition({ type: 'START' }, {
      open: true,
    })
    return next || current
  }, [transition])

  const openTutorial = useCallback(() => {
    const current = stateRef.current
    if (current.status === 'NOT_STARTED') return startTutorial()
    isOpenRef.current = true
    setIsOpen(true)
    return current
  }, [startTutorial])

  const advanceTutorial = useCallback((expectedStepId) => {
    const nextStep = getTutorialStep(stateRef.current.stepId)
    const next = transition({ type: 'ADVANCE', expectedStepId }, {
      close: nextStep?.id === TUTORIAL_STEPS.at(-1)?.id,
    })
    return Boolean(next)
  }, [transition])

  const exitTutorial = useCallback(() => {
    const current = stateRef.current
    if (!['IN_PROGRESS', 'COMPLETED', 'SKIPPED'].includes(current.status)) return false
    transition({ type: 'EXIT' }, {
      force: true,
      close: true,
    })
    return true
  }, [transition])

  const skipTutorial = useCallback(() => {
    const next = transition({ type: 'SKIP_TUTORIAL' }, {
      close: true,
    })
    return Boolean(next)
  }, [transition])

  const repeatTutorial = useCallback(() => {
    const next = transition({ type: 'REPEAT' }, {
      open: true,
    })
    return next || stateRef.current
  }, [transition])

  return {
    isOpen,
    storageKey,
    isHydrated: storageKey !== null && hydratedStorageKey === storageKey,
    status: state.status,
    tutorialRunId: state.tutorialRunId,
    chapter: currentStep.chapter,
    stepId: state.stepId,
    currentStepIndex,
    currentStep,
    totalSteps: TUTORIAL_STEPS.length,
    progressPercent,
    completedStepIds: deriveCompletedStepIds(state),
    completed,
    scenario,
    simulationData: scenario,
    startTutorial,
    openTutorial,
    advanceTutorial,
    exitTutorial,
    skipTutorial,
    repeatTutorial,
    persistenceError,
  }
}
