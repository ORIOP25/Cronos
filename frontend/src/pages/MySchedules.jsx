import { useEffect, useMemo, useRef, useState } from 'react'
import PageHeader from '../components/PageHeader'
import { CAlert, CBadge, CButton, CCard, CCardBody, CCardHeader, CSpinner } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilArrowLeft, cilArrowRight, cilCalendar } from '@coreui/icons'
import WeekGrid from '../components/WeekGrid'
import LessonLogModal from '../components/LessonLogModal'
import ConfirmationModal from '../components/ConfirmationModal'
import { TXT } from '../utils/terminology'
import {
  useTeacherScheduleHorizon,
  useWeekSchedule,
} from '../features/scheduling/data'
import { useTimeslots } from '../features/catalog/data'
import {
  useMyTimesheet,
  useSubmitMyTimesheet,
} from '../features/operations/data'
import { useCurrentMember } from '../features/members/data'
import { getCurrentWeekMonday, addDays, formatWeekRange, formatDate, toWeekMonday, isAfterDate } from '../utils/formatUtils'
import { getApiErrorMessage } from '../utils/apiErrors'
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
    isError: hasWeekError,
    refetch: refetchWeekSchedule,
  } = useWeekSchedule(null, effectiveTeacherId, weekStart)

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

  const { data: timesheet } = useMyTimesheet(weekStart)
  const submitMutation = useSubmitMyTimesheet()

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
    try {
      await submitMutation.mutateAsync(weekStart)
    } catch (err) {
      setSubmitError(getApiErrorMessage(err, 'Erro ao submeter a semana. Tente novamente.'))
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
      title={<span>Meus <span className="text-editorial">Horários</span></span>}
    />
  )

  if (!effectiveTeacherId) {
    return (
      <div className="p-4">
        {pageHeader}
        <CAlert color="danger" className="mb-0">
          Conta de professor sem perfil associado. Contacte um admin para associar o perfil docente.
        </CAlert>
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
        <CAlert color="danger" className="mb-0">
          {resolveHorizonErrorMessage(horizonError)}
        </CAlert>
      </div>
    )
  }

  let weekContent = (
    <WeekGrid
      slots={weekSlots}
      isLoading={isLoadingWeek}
      baseTimeslots={timeslots}
      weekStart={weekStart}
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
      <div className="text-center p-5 text-danger" style={{ fontSize: '0.9rem' }}>
        Não foi possível carregar o seu horário semanal. Verifique a ligação e volte a tentar dentro de alguns minutos.
      </div>
    )
  }

  return (
    <div className="p-4">
      {pageHeader}
      <div className="d-flex justify-content-between align-items-center mb-4 flex-wrap gap-3">
        <div></div>
        <div className="d-flex gap-2 align-items-center flex-wrap">
          {horizon?.active_generation_id ? (
            <CBadge color="success" className="px-3 py-2">
              Versão ativa: {horizon.active_generation_id.slice(0, 8)}...
            </CBadge>
          ) : (
            <CBadge color="secondary" className="px-3 py-2">
              Sem versão ativa
            </CBadge>
          )}
        </div>
      </div>

      <CCard className="border-0 shadow-sm mb-4">
        <CCardHeader className="bg-light border-0 d-flex justify-content-between align-items-center flex-wrap gap-2">
          <div className="fw-semibold">Semana: {formatWeekRange(weekStart)}</div>
          <div className="d-flex gap-2 align-items-center">
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
              Submeter Semana
            </CButton>

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
          </div>
        </CCardHeader>
        <CCardBody>
          <div className="small text-muted mb-3">
            Limite de navegação: {minWeekStart ? `de ${formatDate(minWeekStart)} ` : ''}até {formatDate(hardEndDate)}.
          </div>

          {submitError && (
            <CAlert color="danger" className="mb-3">
              {submitError}
            </CAlert>
          )}

          {limitFeedback ? (
            <CAlert color="warning" className="mb-3">
              {limitFeedback}
            </CAlert>
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
        title="Submeter Semana"
        message={TXT.WEEK_SUBMIT_CONFIRM}
        confirmText="Submeter"
        isLoading={submitMutation.isPending}
        variant="primary"
      />
    </div>
  )
}

export default MySchedules
