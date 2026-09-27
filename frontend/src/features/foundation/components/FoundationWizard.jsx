import { useEffect, useReducer, useCallback, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CButton, CSpinner, CBadge } from '@coreui/react'
import {
  useFoundationStatus,
  useFoundationDraft,
  useSaveFoundationDraft,
  useCompleteFoundation,
} from '../foundationData'
import {
  foundationReducer,
  initialFoundationState,
  serializeFoundationDraftValues,
  validateFoundationStep,
  FOUNDATION_STEP_COUNT,
  STEP_PERIOD,
  STEP_DAYS,
  STEP_OPENING,
  STEP_SLOT_DURATION,
  STEP_BREAK_DURATION,
  STEP_LUNCH,
  STEP_PREVIEW,
  STEP_CALENDAR,
  STEP_INTERNSHIP,
  STEP_CONFIRMATION,
} from '../foundationModel'
import { PeriodStep } from './PeriodStep'
import { DaysStep } from './DaysStep'
import { OpeningStep } from './OpeningStep'
import { SlotDurationStep } from './SlotDurationStep'
import { BreakDurationStep } from './BreakDurationStep'
import { LunchStep } from './LunchStep'
import { PreviewStep } from './PreviewStep'
import { SchoolCalendarStep } from './SchoolCalendarStep'
import { InternshipFlowsStep } from './InternshipFlowsStep'
import { SummaryStep } from './SummaryStep'
import { ConflictResolutionModal } from './ConflictResolutionModal'
import GuidedFormShell from '../../../components/GuidedFormShell'
import GuidedFormProgress from '../../../components/GuidedFormProgress'
import FeedbackBanner from '../../../components/FeedbackBanner'
import StatePanel from '../../../components/StatePanel'
import { getApiErrorCode } from '../../../utils/apiErrors'

function apiErrorMessage(detail, fallback) {
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object') return detail.message || detail.error || fallback
  return fallback
}

export function FoundationWizard() {
  const navigate = useNavigate()
  const statusQuery = useFoundationStatus()
  const draftQuery = useFoundationDraft()
  const saveDraftMutation = useSaveFoundationDraft()
  const completeMutation = useCompleteFoundation()

  const [state, dispatch] = useReducer(foundationReducer, initialFoundationState)
  const [confirmed, setConfirmed] = useState(false)
  const [isRetrying, setIsRetrying] = useState(false)
  const [isRecoveringHolidays, setIsRecoveringHolidays] = useState(false)
  const [isTransitioning, setIsTransitioning] = useState(false)
  const [isReloadingConflict, setIsReloadingConflict] = useState(false)
  const [conflictReloadError, setConflictReloadError] = useState('')
  const [isInitialSynced, setIsInitialSynced] = useState(false)
  const [hasFailedSnapshot, setHasFailedSnapshot] = useState(false)
  const isInitialSync = useRef(false)
  const isDirtyRef = useRef(false)
  const autosaveTimerRef = useRef(null)
  const confirmedVersionRef = useRef(0)
  const pendingSnapshotRef = useRef(null)
  const failedSnapshotRef = useRef(null)
  const saveRunnerRef = useRef(null)
  const transitionInProgressRef = useRef(false)

  // 1. Initial Sync from Server Draft
  useEffect(() => {
    if (statusQuery.data && draftQuery.data && !isInitialSync.current) {
      isInitialSync.current = true
      setIsInitialSynced(true)
      confirmedVersionRef.current = draftQuery.data.version || 0
      dispatch({ type: 'INIT_FROM_SERVER', payload: draftQuery.data })
    }
  }, [draftQuery.data, statusQuery.data])

  useEffect(() => {
    if (!isInitialSync.current || !state.currentStep) return
    const focusTimer = window.setTimeout(() => {
      document.querySelector('.foundation-step-content h4')?.focus()
    }, 0)
    return () => window.clearTimeout(focusTimer)
  }, [state.currentStep])

  // 2. Redirect if already completed
  useEffect(() => {
    if (statusQuery.data?.foundation_status === 'COMPLETED' || state.completedThisSession) {
      navigate('/dashboard', { replace: true })
    }
  }, [statusQuery.data?.foundation_status, state.completedThisSession, navigate])

  const persistSnapshot = useCallback((snapshot, { explicitTransition = false } = {}) => {
    if (state.status === 'conflict') return Promise.resolve(false)
    if (autosaveTimerRef.current) {
      clearTimeout(autosaveTimerRef.current)
      autosaveTimerRef.current = null
    }
    if (explicitTransition) isDirtyRef.current = false
    pendingSnapshotRef.current = { snapshot, explicitTransition }
    if (saveRunnerRef.current) {
      return saveRunnerRef.current
    }

    const runner = (async () => {
      while (pendingSnapshotRef.current) {
        const queuedSnapshot = pendingSnapshotRef.current
        pendingSnapshotRef.current = null
        const nextSnapshot = queuedSnapshot.snapshot
        dispatch({ type: 'SAVE_STARTED' })
        try {
          const res = await saveDraftMutation.mutateAsync({
            expected_version: confirmedVersionRef.current,
            current_step: nextSnapshot.step,
            data: serializeFoundationDraftValues(nextSnapshot.values),
          })
          confirmedVersionRef.current = res.version
          failedSnapshotRef.current = null
          setHasFailedSnapshot(false)
          dispatch({ type: 'SAVE_SUCCEEDED', version: res.version })
        } catch (err) {
          if (err?.response?.status === 409) {
            // Preserve a newer edit queued while this request was in flight.
            if (!pendingSnapshotRef.current) {
              pendingSnapshotRef.current = {
                snapshot: nextSnapshot,
                explicitTransition: queuedSnapshot.explicitTransition,
              }
            }
            dispatch({ type: 'VERSION_CONFLICT', payload: err.response.data?.detail || {} })
          } else {
            failedSnapshotRef.current = nextSnapshot
            setHasFailedSnapshot(true)
            dispatch({
              type: 'SAVE_FAILED',
              error: apiErrorMessage(err?.response?.data?.detail, 'Não foi possível guardar o rascunho.'),
              errorCode: getApiErrorCode(err),
            })
            if (pendingSnapshotRef.current?.explicitTransition) continue
          }
          return false
        }
      }
      return true
    })()

    saveRunnerRef.current = runner.finally(() => {
      saveRunnerRef.current = null
    })
    return saveRunnerRef.current
  }, [saveDraftMutation, state.status])

  // 4. 600ms Debounced Autosave on user input
  useEffect(() => {
    if (
      !isInitialSync.current
      || !isDirtyRef.current
      || state.status === 'conflict'
      || isTransitioning
    ) {
      return
    }

    if (autosaveTimerRef.current) {
      clearTimeout(autosaveTimerRef.current)
    }

    autosaveTimerRef.current = setTimeout(() => {
      autosaveTimerRef.current = null
      isDirtyRef.current = false
      void persistSnapshot({ step: state.currentStep, values: state.values })
    }, 600)

    return () => {
      if (autosaveTimerRef.current) {
        clearTimeout(autosaveTimerRef.current)
      }
    }
  }, [state.values, state.currentStep, state.status, isTransitioning, persistSnapshot])

  const handleChange = (field, value) => {
    if (state.status === 'conflict') return
    isDirtyRef.current = true
    dispatch({ type: 'SET_FIELD', field, value })
  }

  const handleCalendarPreferenceChange = (_field, value) => {
    if (state.status === 'conflict') return
    const nextValues = { ...state.values, automatic_holidays_enabled: value }
    isDirtyRef.current = false
    dispatch({ type: 'SET_FIELD', field: 'automatic_holidays_enabled', value })
    void persistSnapshot({ step: state.currentStep, values: nextValues })
  }

  const handleRetrySave = () => {
    void persistSnapshot({ step: state.currentStep, values: state.values })
  }

  const canDisableAutomaticHolidays = state.status === 'error'
    && state.errorCode === 'HOLIDAY_SYNC_FAILED'
    && state.values.automatic_holidays_enabled

  const handleDisableAutomaticHolidays = async () => {
    if (!canDisableAutomaticHolidays || isRecoveringHolidays) return
    setIsRecoveringHolidays(true)
    const values = { ...state.values, automatic_holidays_enabled: false }
    try {
      const saved = await persistSnapshot({ step: state.currentStep, values })
      if (saved) {
        isDirtyRef.current = false
        dispatch({ type: 'SET_FIELD', field: 'automatic_holidays_enabled', value: false })
      }
    } finally {
      setIsRecoveringHolidays(false)
    }
  }

  // Navigation handlers
  const persistDestination = async (destinationStep) => {
    if (transitionInProgressRef.current || state.status === 'conflict') return false
    transitionInProgressRef.current = true
    setIsTransitioning(true)
    if (autosaveTimerRef.current) {
      clearTimeout(autosaveTimerRef.current)
      autosaveTimerRef.current = null
    }
    try {
      const saved = await persistSnapshot(
        { step: destinationStep, values: state.values },
        { explicitTransition: true },
      )
      if (saved) {
        dispatch({ type: 'SET_STEP', step: destinationStep })
      }
      return saved
    } finally {
      transitionInProgressRef.current = false
      setIsTransitioning(false)
    }
  }

  const handleNext = async () => {
    const errors = validateFoundationStep(state.currentStep, state.values)
    if (Object.keys(errors).length > 0) {
      dispatch({ type: 'SET_ERRORS', errors })
      return
    }

    const nextStep = Math.min(FOUNDATION_STEP_COUNT, state.currentStep + 1)
    await persistDestination(nextStep)
  }

  const handlePrev = async () => {
    const prevStep = Math.max(1, state.currentStep - 1)
    await persistDestination(prevStep)
  }

  const handleCompleteActivation = async () => {
    if (!confirmed) return

    const errors = validateFoundationStep(STEP_CONFIRMATION, state.values)
    if (Object.keys(errors).length > 0) {
      dispatch({ type: 'SET_ERRORS', errors })
      return
    }

    if (!await persistDestination(STEP_CONFIRMATION)) return
    dispatch({ type: 'COMPLETE_STARTED' })
    try {
      await completeMutation.mutateAsync({
        expected_version: confirmedVersionRef.current,
        confirmed: true,
      })
      dispatch({ type: 'COMPLETE_SUCCEEDED' })
      navigate('/dashboard', { replace: true })
    } catch (err) {
      if (err?.response?.status === 409) {
        const detail = err.response.data?.detail || {}
        dispatch({ type: 'VERSION_CONFLICT', payload: detail })
      } else {
        dispatch({
          type: 'COMPLETE_FAILED',
          error: apiErrorMessage(err?.response?.data?.detail, 'Falha ao ativar a escola. Tente novamente.'),
          errorCode: getApiErrorCode(err),
        })
      }
    }
  }

  // Conflict Resolution
  const handleReloadConflict = async () => {
    setConflictReloadError('')
    setIsReloadingConflict(true)
    try {
      const res = await draftQuery.refetch()
      if (res.error || !res.data) {
        throw res.error || new Error('O rascunho remoto não foi devolvido.')
      }
      confirmedVersionRef.current = res.data.version || 0
      failedSnapshotRef.current = null
      setHasFailedSnapshot(false)
      pendingSnapshotRef.current = null
      isDirtyRef.current = false
      dispatch({ type: 'RESOLVE_CONFLICT_RELOAD', payload: res.data })
    } catch (err) {
      setConflictReloadError(apiErrorMessage(err?.response?.data?.detail, 'Não foi possível recarregar os dados mais recentes.'))
    } finally {
      setIsReloadingConflict(false)
    }
  }

  const handleRetryHydration = async () => {
    setIsRetrying(true)
    await Promise.all([statusQuery.refetch(), draftQuery.refetch()])
    setIsRetrying(false)
  }

  const organizationName = statusQuery.data?.organization_name || 'a sua escola'
  const isBlocked = state.status === 'conflict' || isRetrying || isRecoveringHolidays || isTransitioning

  if (statusQuery.isError || draftQuery.isError) {
    return (
      <div className="guided-form-shell">
        <StatePanel
          state="error"
          title="Não foi possível carregar a fundação da escola"
          description="O estado e o rascunho não foram confirmados. Tente novamente para continuar."
          action={(
            <button type="button" onClick={handleRetryHydration} disabled={isRetrying}>
              {isRetrying ? 'A tentar novamente…' : 'Tentar novamente'}
            </button>
          )}
        />
      </div>
    )
  }

  if (statusQuery.isLoading || draftQuery.isLoading || !isInitialSynced || isRetrying) {
    return (
      <div className="guided-form-shell">
        <StatePanel state="loading" title="A carregar a fundação da escola" description="A obter dados e rascunho de configuração..." />
      </div>
    )
  }

  return (
    <div className="foundation-wizard-wrapper">
      <GuidedFormShell
        eyebrow="Fundação Escolar"
        title="Configuração Base da Escola"
        summary={`Defina o calendário e grelha letiva para ${organizationName}.`}
      >
        <div className="d-flex justify-content-between align-items-center mb-3">
          <GuidedFormProgress
            current={state.currentStep}
            total={FOUNDATION_STEP_COUNT}
          />
          <div className="ms-3 text-end" style={{ minWidth: '120px' }}>
            {state.status === 'saving' && (
              <span className="small text-muted d-flex align-items-center gap-1 justify-content-end" role="status">
                <CSpinner size="sm" /> A guardar...
              </span>
            )}
            {state.status === 'error' && (
              <CBadge color="danger" shape="rounded-pill" role="alert">Erro ao guardar</CBadge>
            )}
          </div>
        </div>

        {state.error && (
          <div className="mb-3">
            <FeedbackBanner
              tone="danger"
              action={(
                <div className="d-flex flex-wrap gap-2">
                  {state.status === 'error' && hasFailedSnapshot && (
                    <button type="button" onClick={handleRetrySave} disabled={isRecoveringHolidays}>
                      Tentar guardar novamente
                    </button>
                  )}
                  {canDisableAutomaticHolidays && (
                    <button
                      type="button"
                      onClick={handleDisableAutomaticHolidays}
                      disabled={isRecoveringHolidays}
                    >
                      Desativar feriados automáticos e guardar
                    </button>
                  )}
                </div>
              )}
            >{state.error}</FeedbackBanner>
          </div>
        )}

        <fieldset disabled={isBlocked || !isInitialSynced} className="foundation-step-content py-2 border-0 p-0 m-0">
          {state.currentStep === STEP_PERIOD && (
            <PeriodStep
              values={state.values}
              fieldErrors={state.fieldErrors}
              onChange={handleChange}
            />
          )}

          {state.currentStep === STEP_DAYS && (
            <DaysStep
              values={state.values}
              fieldErrors={state.fieldErrors}
              onChange={handleChange}
            />
          )}

          {state.currentStep === STEP_OPENING && (
            <OpeningStep
              values={state.values}
              fieldErrors={state.fieldErrors}
              onChange={handleChange}
            />
          )}

          {state.currentStep === STEP_SLOT_DURATION && (
            <SlotDurationStep
              values={state.values}
              fieldErrors={state.fieldErrors}
              onChange={handleChange}
            />
          )}

          {state.currentStep === STEP_BREAK_DURATION && (
            <BreakDurationStep
              values={state.values}
              fieldErrors={state.fieldErrors}
              onChange={handleChange}
            />
          )}

          {state.currentStep === STEP_LUNCH && (
            <LunchStep
              values={state.values}
              fieldErrors={state.fieldErrors}
              onChange={handleChange}
            />
          )}

          {state.currentStep === STEP_PREVIEW && (
            <PreviewStep
              values={state.values}
              fieldErrors={state.fieldErrors}
            />
          )}

          {state.currentStep === STEP_CALENDAR && (
            <SchoolCalendarStep
              values={state.values}
              onChange={handleCalendarPreferenceChange}
            />
          )}

          {state.currentStep === STEP_INTERNSHIP && (
            <InternshipFlowsStep
              values={state.values}
              fieldErrors={state.fieldErrors}
              onChange={handleChange}
            />
          )}

          {state.currentStep === STEP_CONFIRMATION && (
            <SummaryStep
              values={state.values}
              organizationName={organizationName}
              confirmed={confirmed}
              onConfirmedChange={setConfirmed}
            />
          )}
        </fieldset>

        <div className="d-flex justify-content-between align-items-center pt-4 border-top mt-4">
          <CButton
            color="secondary"
            variant="outline"
            disabled={state.currentStep === 1 || isBlocked}
            onClick={handlePrev}
          >
            ← Anterior
          </CButton>

          <div className="d-flex gap-2">
            {state.currentStep < STEP_CONFIRMATION ? (
              <CButton
                color="primary"
                disabled={isBlocked}
                onClick={handleNext}
              >
                {(state.currentStep === STEP_CALENDAR
                  && !state.values.automatic_holidays_enabled)
                || (state.currentStep === STEP_INTERNSHIP
                  && (state.values.internship_flows || []).length === 0)
                  ? 'Ignorar por agora'
                  : 'Seguinte →'}
              </CButton>
            ) : (
              <CButton
                color="success"
                disabled={isBlocked || !confirmed}
                onClick={handleCompleteActivation}
              >
                Ativar Escola
              </CButton>
            )}
          </div>
        </div>
      </GuidedFormShell>

      {/* Modal de Resolução de Conflitos 409 */}
      <ConflictResolutionModal
        isOpen={state.status === 'conflict'}
        conflictData={state.conflictData}
        onReload={handleReloadConflict}
        reloadError={conflictReloadError}
        isReloading={isReloadingConflict}
      />
    </div>
  )
}
