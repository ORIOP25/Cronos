import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'react-hot-toast'
import PageHeader from '../components/PageHeader'
import { CBadge, CButton, CCard, CCardBody, CCardHeader, CSpinner } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilArrowLeft, cilArrowRight, cilCalendar } from '@coreui/icons'
import WeekGrid from '../components/WeekGrid'
import LessonLogModal from '../components/LessonLogModal'
import FeedbackBanner from '../components/FeedbackBanner'
import ConfirmationModal from '../components/ConfirmationModal'
import { TXT } from '../utils/terminology'
import {
  useTeacherScheduleHorizon,
  useWeekSchedule,
} from '../features/scheduling/data'
import { useTimeslots, useWeekGridVersions } from '../features/catalog/data'
import {
  useMyTimesheet,
  useSubmitMyTimesheet,
} from '../features/operations/data'
import { useCurrentMember } from '../features/members/data'
import { getCurrentWeekMonday, addDays, formatWeekRange, formatDate, toWeekMonday, isAfterDate } from '../utils/formatUtils'
import { getApiErrorMessage, getApiErrorPresentation, isApiErrorTransient } from '../utils/apiErrors'
import { useAttemptScope } from '../hooks/useAttemptScope'
import FailureState from '../components/FailureState'
import { getWeekSubmissionBlockers } from '../features/operations/weekSubmission'

const HORIZON_NOT_CONFIGURED_MESSAGE =
  'Não existe período semanal configurado para a escola. Contacte a equipa administrativa para validar o ano letivo ativo.'
const HORIZON_SYNC_POLLING_INTERVAL_MS = 30000
const HORIZON_NO_ACTIVE_GENERATION_KEY = '__no_active_generation__'
const EMPTY_ARRAY = []

function toGenerationCacheKey(activeGenerationId) {
  return activeGenerationId || HORIZON_NO_ACTIVE_GENERATION_KEY
}

function resolveHorizonErrorMessage(error) {
  const status = error?.response?.status
  if (status === 403) {
    return 'Sem permissões para consultar o seu horário semanal.'
  }
  if (status === 429) {
    return 'Atualização temporariamente limitada por excesso de pedidos. Aguarde alguns minutos e volte a tentar.'
  }
  if (status === 404) {
    return HORIZON_NOT_CONFIGURED_MESSAGE
  }
  return 'Não foi possível carregar o período semanal. Tente novamente em alguns minutos.'
}

function MySchedules() {
  const { data: currentMember } = useCurrentMember()
  const teacherId = currentMember?.teacher_id
  const [selectedWeekStart, setSelectedWeekStart] = useState(null)
  const [limitFeedback, setLimitFeedback] = useState('')
  const [selectedSlot, setSelectedSlot] = useState(null)
  const [showSubmitConfirm, setShowSubmitConfirm] = useState(false)
  const hasInitializedGenerationRef = useRef(false)
  const generationKeyRef = useRef(HORIZON_NO_ACTIVE_GENERATION_KEY)

  const effectiveTeacherId = typeof teacherId === 'number' ? teacherId : null

  const {
    data: horizon,
    isLoading: isLoadingHorizon,
    isError: hasHorizonError,
    error: horizonError,
  } = useTeacherScheduleHorizon({
    enabled: Boolean(effectiveTeacherId),
    refetchInterval: HORIZON_SYNC_POLLING_INTERVAL_MS,
  })

  const hardEndDate = horizon?.hard_end_date ?? null
  const recommendedWeekStart = horizon?.week_start_recommended ?? null
  const minWeekStart = horizon?.min_week_start ?? recommendedWeekStart
  const requestedWeekStart = selectedWeekStart ?? recommendedWeekStart ?? getCurrentWeekMonday()
  const weekStart = minWeekStart && isAfterDate(minWeekStart, requestedWeekStart)
    ? minWeekStart
    : hardEndDate && isAfterDate(requestedWeekStart, hardEndDate)
      ? toWeekMonday(hardEndDate)
      : requestedWeekStart

  const prevWeekStart = useMemo(() => addDays(weekStart, -7), [weekStart])
  const nextWeekStart = useMemo(() => addDays(weekStart, 7), [weekStart])
  const prevWeekBlocked = useMemo(() => {
    if (!minWeekStart) {
      return false
    }
    return isAfterDate(minWeekStart, prevWeekStart)
  }, [minWeekStart, prevWeekStart])
  const nextWeekBlocked = useMemo(() => {
    if (!hardEndDate) {
      return false
    }
    return isAfterDate(nextWeekStart, hardEndDate)
  }, [hardEndDate, nextWeekStart])

  const {
    data: fetchedWeekSlots,
    isFetching: isLoadingWeek,
    error: weekError,
    refetch: refetchWeekSchedule,
  } = useWeekSchedule(null, effectiveTeacherId, weekStart)
  const hasWeekError = Boolean(weekError)

  useEffect(() => {
    if (!effectiveTeacherId || isLoadingHorizon || hasHorizonError) return

    const currentGenerationKey = toGenerationCacheKey(horizon?.active_generation_id)
    if (!hasInitializedGenerationRef.current) {
      generationKeyRef.current = currentGenerationKey
      hasInitializedGenerationRef.current = true
      return
    }
    if (generationKeyRef.current === currentGenerationKey) return

    generationKeyRef.current = currentGenerationKey
    void refetchWeekSchedule()
  }, [
    effectiveTeacherId,
    horizon?.active_generation_id,
    hasHorizonError,
    isLoadingHorizon,
    refetchWeekSchedule,
  ])

  const weekSlots = hasWeekError ? EMPTY_ARRAY : fetchedWeekSlots ?? EMPTY_ARRAY

  const { data: timeslots = [] } = useTimeslots()
  const { data: weekGridVersions } = useWeekGridVersions(weekStart)

  const { data: timesheet } = useMyTimesheet(weekStart)
  const submitMutation = useSubmitMyTimesheet()
  const attemptScope = useAttemptScope()

  const blockingSlots = useMemo(() => getWeekSubmissionBlockers(weekSlots), [weekSlots])
  const canSubmit = weekSlots.length > 0
    && (!timesheet || timesheet.status === 'OPEN')
    && blockingSlots.length === 0

  const submitTooltip = useMemo(() => {
    if (canSubmit) return ''
    if (weekSlots.length === 0) return 'Sem aulas para submeter.'
    if (!timesheet || timesheet.status === 'OPEN') {
      return `Bloqueios:\n${blockingSlots.join('\n')}`
    }
    if (timesheet.status === 'SUBMITTED') return 'Semana já submetida.'
    if (timesheet.status === 'APPROVED') return 'Semana já aprovada.'
    return ''
  }, [canSubmit, blockingSlots, timesheet, weekSlots])

  const [submitError, setSubmitError] = useState('')

  const handleSubmitWeek = async () => {
    setShowSubmitConfirm(true)
  }

  const handleConfirmSubmit = async () => {
    setShowSubmitConfirm(false)
    setSubmitError('')
    const attempt = attemptScope.capture()
    try {
      await submitMutation.mutateAsync(weekStart)
      if (!attemptScope.isCurrent(attempt)) return
      toast.success('Semana submetida.')
    } catch (err) {
      if (!attemptScope.isCurrent(attempt)) return
      const message = getApiErrorMessage(err, 'Não foi possível submeter a semana. Tente novamente.')
      if (isApiErrorTransient(err)) toast.error(message)
      else setSubmitError(message)
    }
  }

  const handlePrevWeek = () => {
    if (prevWeekBlocked && minWeekStart) {
      setLimitFeedback(`Semanas antes de ${formatDate(minWeekStart)} estão bloqueadas.`)
      return
    }
    setLimitFeedback('')
    setSelectedWeekStart(prevWeekStart)
  }

  const handleCurrentWeek = () => {
    const currentWeek = getCurrentWeekMonday()
    if (hardEndDate && isAfterDate(currentWeek, hardEndDate)) {
      setSelectedWeekStart(toWeekMonday(hardEndDate))
      setLimitFeedback(`A semana atual está após a data limite do ano letivo (${formatDate(hardEndDate)}).`)
      return
    }
    setLimitFeedback('')
    setSelectedWeekStart(currentWeek)
  }

  const handleNextWeek = () => {
    if (nextWeekBlocked && hardEndDate) {
      setLimitFeedback(`Semanas após ${formatDate(hardEndDate)} estão bloqueadas.`)
      return
    }
    setLimitFeedback('')
    setSelectedWeekStart(nextWeekStart)
  }

  const pageHeader = (
    <PageHeader
      preTitle="Professor"
      title="Meus horários"
    />
  )

  if (!effectiveTeacherId) {
    return (
      <div className="p-4">
        {pageHeader}
        <FeedbackBanner tone="danger">
          Conta de professor sem perfil associado. Contacte a administração para associar o perfil docente.
        </FeedbackBanner>
      </div>
    )
  }

  if (isLoadingHorizon) {
    return (
      <div className="p-4">
        {pageHeader}
        <CCard className="border-0 shadow-sm">
          <CCardBody className="py-4 d-flex align-items-center gap-2 text-muted">
            <CSpinner size="sm" />
            A carregar o seu horário semanal...
          </CCardBody>
        </CCard>
      </div>
    )
  }

  if (hasHorizonError) {
    return (
      <div className="p-4">
        {pageHeader}
        <FeedbackBanner tone="danger">
          {resolveHorizonErrorMessage(horizonError)}
        </FeedbackBanner>
      </div>
    )
  }

  let weekContent = (
    <WeekGrid
      slots={weekSlots}
      isLoading={isLoadingWeek}
      baseTimeslots={timeslots}
      weekStart={weekStart}
      dayGrids={weekGridVersions?.days ?? null}
      gridTransitionDate={weekGridVersions?.transition_date ?? ''}
      isOperationalEnabled={!timesheet || timesheet.status === 'OPEN'}
      onOpenOperationalAction={setSelectedSlot}
    />
  )

  if (!isLoadingWeek && weekSlots.length === 0) {
    weekContent = (
      <div className="text-center p-5 text-muted">
        <CIcon icon={cilCalendar} style={{ fontSize: '2rem', opacity: 0.35 }} />
        <div className="mt-2">Não existem blocos planeados para a semana selecionada.</div>
      </div>
    )
  }

  if (hasWeekError) {
    weekContent = (
      <FailureState
        variant="inline"
        presentation={{
          ...getApiErrorPresentation(weekError, 'schedule.week'),
          title: 'Não foi possível carregar o seu horário semanal',
          message: 'Verifique a ligação e volte a tentar. A semana selecionada mantém-se.',
        }}
        onRetry={() => refetchWeekSchedule()}
      />
    )
  }

  return (
    <div className="p-4">
      {pageHeader}
      <CCard className="border-0 shadow-sm mb-4" role="region" aria-label="Horário semanal">
        <CCardHeader className="bg-light border-0 d-flex justify-content-between align-items-center flex-wrap gap-3">
          <div className="d-flex gap-2 align-items-center flex-wrap">
          <div className="fw-semibold">Semana: {formatWeekRange(weekStart)}</div>
          {horizon?.active_generation_id ? (
            <CBadge color="success" className="px-3 py-2">
              Horário publicado
            </CBadge>
          ) : (
            <CBadge color="secondary" className="px-3 py-2">
              Ainda sem horário publicado
            </CBadge>
          )}
          </div>
          <div className="d-flex gap-2 align-items-center flex-wrap">
            {timesheet && timesheet.status === 'SUBMITTED' && (
              <CBadge color="info" className="me-2 px-3 py-2">Semana Submetida</CBadge>
            )}
            {timesheet && timesheet.status === 'APPROVED' && (
              <CBadge color="success" className="me-2 px-3 py-2">Semana Aprovada</CBadge>
            )}
            
            <CButton
              color="primary"
              size="sm"
              onClick={handleSubmitWeek}
              disabled={!canSubmit || submitMutation.isPending}
              title={submitTooltip}
            >
              {submitMutation.isPending ? <CSpinner size="sm" className="me-1" /> : <CIcon icon={cilCalendar} className="me-1" />}
              Submeter semana
            </CButton>
          </div>
        </CCardHeader>
        <CCardBody>
          <fieldset className="d-flex gap-2 align-items-center justify-content-end flex-wrap mb-3 border-0 p-0" aria-label="Navegar entre semanas">
            <CButton color="secondary" variant="outline" size="sm" onClick={handlePrevWeek}>
              <CIcon icon={cilArrowLeft} className="me-1" />
              Semana anterior
            </CButton>
            <CButton color="secondary" variant="outline" size="sm" onClick={handleCurrentWeek}>
              Semana atual
            </CButton>
            <CButton color="secondary" variant="outline" size="sm" onClick={handleNextWeek}>
              Próxima semana
              <CIcon icon={cilArrowRight} className="ms-1" />
            </CButton>
          </fieldset>
          <div className="small text-muted mb-3">
            Limite de navegação: {minWeekStart ? `de ${formatDate(minWeekStart)} ` : ''}até {formatDate(hardEndDate)}.
          </div>

          {submitError && (
            <div className="mb-3"><FeedbackBanner tone="danger">{submitError}</FeedbackBanner></div>
          )}

          {limitFeedback ? (
            <div className="mb-3"><FeedbackBanner tone="warning">{limitFeedback}</FeedbackBanner></div>
          ) : null}

          {weekContent}
        </CCardBody>
      </CCard>

      {selectedSlot && (
        <LessonLogModal
          key={selectedSlot.operational_block_id ?? selectedSlot.id}
          onClose={() => setSelectedSlot(null)}
          slot={selectedSlot}
        />
      )}

      <ConfirmationModal
        visible={showSubmitConfirm}
        onClose={() => setShowSubmitConfirm(false)}
        onConfirm={handleConfirmSubmit}
        title="Submeter semana"
        message={TXT.WEEK_SUBMIT_CONFIRM}
        confirmText="Submeter semana"
        pendingText="A submeter…"
        isLoading={submitMutation.isPending}
        variant="primary"
      />
    </div>
  )
}

export default MySchedules
