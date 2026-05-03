import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { CAlert, CBadge, CButton, CCard, CCardBody, CCardHeader, CSpinner } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilArrowLeft, cilArrowRight, cilCalendar } from '@coreui/icons'
import WeekGrid from '../components/WeekGrid'
import LessonLogModal from '../components/LessonLogModal'
import ConfirmationModal from '../components/ConfirmationModal'
import { TXT } from '../utils/terminology'
import {
  useTeacherScheduleHorizon,
  useTimeslots,
  useWeekSchedule,
  useMyTimesheet,
  useSubmitMyTimesheet
} from '../hooks/useSchoolData'
import { useAuthStore } from '../store'

const HORIZON_NOT_CONFIGURED_MESSAGE =
  'Não existe período semanal configurado para a escola. Contacte a equipa administrativa para validar o ano letivo ativo.'
const HORIZON_SYNC_POLLING_INTERVAL_MS = 30000
const HORIZON_NO_ACTIVE_GENERATION_KEY = '__no_active_generation__'
const HORIZON_SYNC_FEEDBACK_MESSAGE =
  'Horário atualizado com a versão mais recente publicada pela escola.'
const HORIZON_DEGRADED_FEEDBACK_MESSAGE =
  'Atualização semanal temporariamente indisponível. A mostrar o último estado válido.'
const WEEK_DEGRADED_FEEDBACK_MESSAGE =
  'Falha temporária ao carregar esta semana. A mostrar o último estado válido.'

function toGenerationCacheKey(activeGenerationId) {
  return activeGenerationId || HORIZON_NO_ACTIVE_GENERATION_KEY
}

function parseDateAtNoon(dateStr) {
  const [year, month, day] = dateStr.split('-').map(Number)
  return new Date(year, month - 1, day, 12, 0, 0, 0)
}

function toIsoDate(value) {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function toWeekMonday(dateStr) {
  const dateValue = parseDateAtNoon(dateStr)
  const dayOfWeek = dateValue.getDay()
  const offset = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
  dateValue.setDate(dateValue.getDate() + offset)
  return toIsoDate(dateValue)
}

function getCurrentWeekMonday() {
  return toWeekMonday(toIsoDate(new Date()))
}

function addDays(dateStr, days) {
  const dateValue = parseDateAtNoon(dateStr)
  dateValue.setDate(dateValue.getDate() + days)
  return toIsoDate(dateValue)
}

function isAfterDate(leftDate, rightDate) {
  return parseDateAtNoon(leftDate).getTime() > parseDateAtNoon(rightDate).getTime()
}

function formatWeekRange(weekStart) {
  const start = parseDateAtNoon(weekStart)
  const end = parseDateAtNoon(weekStart)
  end.setDate(end.getDate() + 4)

  const short = { day: '2-digit', month: 'short' }
  const full = { day: '2-digit', month: 'short', year: 'numeric' }
  return `${start.toLocaleDateString('pt-PT', short)} – ${end.toLocaleDateString('pt-PT', full)}`
}

function formatDatePt(dateStr) {
  return parseDateAtNoon(dateStr).toLocaleDateString('pt-PT', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
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
  const queryClient = useQueryClient()
  const teacherId = useAuthStore((state) => state.user?.teacherId)
  const orgId = useAuthStore((state) => state.user?.orgId)
  const [weekStart, setWeekStart] = useState(getCurrentWeekMonday)
  const [recommendedWeekApplied, setRecommendedWeekApplied] = useState(false)
  const [limitFeedback, setLimitFeedback] = useState('')
  const [syncFeedback, setSyncFeedback] = useState('')
  const [lastHealthyHorizon, setLastHealthyHorizon] = useState(null)
  const [lastHealthyWeekSlots, setLastHealthyWeekSlots] = useState([])
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

  useEffect(() => {
    if (!isLoadingHorizon && !hasHorizonError && horizon) {
      setLastHealthyHorizon(horizon)
    }
  }, [horizon, isLoadingHorizon, hasHorizonError])

  const effectiveHorizon = hasHorizonError ? lastHealthyHorizon : horizon
  const hardEndDate = effectiveHorizon?.hard_end_date ?? null
  const recommendedWeekStart = effectiveHorizon?.week_start_recommended ?? null
  const minWeekStart = effectiveHorizon?.min_week_start ?? recommendedWeekStart

  useEffect(() => {
    if (!recommendedWeekStart || recommendedWeekApplied) {
      return
    }
    setWeekStart(recommendedWeekStart)
    setRecommendedWeekApplied(true)
  }, [recommendedWeekApplied, recommendedWeekStart])

  useEffect(() => {
    if (minWeekStart && isAfterDate(minWeekStart, weekStart)) {
      setWeekStart(minWeekStart)
      setLimitFeedback(`A navegação foi limitada ao início do ano letivo (${formatDatePt(minWeekStart)}).`)
      return
    }
    if (hardEndDate && isAfterDate(weekStart, hardEndDate)) {
      setWeekStart(toWeekMonday(hardEndDate))
      setLimitFeedback(`A navegação foi limitada à data limite do ano letivo (${formatDatePt(hardEndDate)}).`)
    }
  }, [hardEndDate, minWeekStart, weekStart])

  useEffect(() => {
    if (!effectiveTeacherId || isLoadingHorizon || hasHorizonError) {
      return
    }

    const currentGenerationKey = toGenerationCacheKey(effectiveHorizon?.active_generation_id)
    if (!hasInitializedGenerationRef.current) {
      generationKeyRef.current = currentGenerationKey
      hasInitializedGenerationRef.current = true
      return
    }

    if (generationKeyRef.current === currentGenerationKey) {
      return
    }

    generationKeyRef.current = currentGenerationKey
    setSyncFeedback(HORIZON_SYNC_FEEDBACK_MESSAGE)

    void queryClient.invalidateQueries({
      predicate: (query) => {
        const key = query.queryKey
        return Array.isArray(key)
          && key[0] === 'weekSchedule'
          && key[1] === orgId
          && key[3] === effectiveTeacherId
      },
    })
  }, [
    effectiveTeacherId,
    effectiveHorizon?.active_generation_id,
    hasHorizonError,
    isLoadingHorizon,
    orgId,
    queryClient,
  ])

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
    data: fetchedWeekSlots = [],
    isFetching: isLoadingWeek,
    isError: hasWeekError,
  } = useWeekSchedule(null, effectiveTeacherId, weekStart)

  useEffect(() => {
    if (!hasWeekError) {
      setLastHealthyWeekSlots(fetchedWeekSlots)
    }
  }, [fetchedWeekSlots, hasWeekError])

  const weekSlots = hasWeekError ? lastHealthyWeekSlots : fetchedWeekSlots
  const hasWeekFallback = hasWeekError && lastHealthyWeekSlots.length > 0

  const { data: timeslots = [] } = useTimeslots()

  const { data: timesheet, isLoading: isLoadingTimesheet } = useMyTimesheet(weekStart)
  const submitMutation = useSubmitMyTimesheet()

  const canSubmit = useMemo(() => {
    if (weekSlots.length === 0) return false
    if (timesheet && timesheet.status !== 'OPEN') return false
    
    const now = new Date()
    for (const slot of weekSlots) {
      if (slot.date && slot.timeslot?.end_time) {
        const endDateTime = new Date(`${slot.date}T${slot.timeslot.end_time}`)
        if (endDateTime > now) return false
      } else if (!slot.is_past) {
        return false
      }
      
      const hasLessonLog = slot.lesson_log_status === 'COMPLETED' || slot.lesson_log_status === 'OCCURRENCE'
      const hasOccurrence = slot.occurrence_status != null
      if (!hasLessonLog && !hasOccurrence) {
        return false
      }
    }
    return true
  }, [weekSlots, timesheet])

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
      setSubmitError(err.response?.data?.detail || 'Erro ao submeter a semana. Tente novamente.')
    }
  }

  const handlePrevWeek = () => {
    setSyncFeedback('')
    if (prevWeekBlocked && minWeekStart) {
      setLimitFeedback(`Semanas antes de ${formatDatePt(minWeekStart)} estão bloqueadas.`)
      return
    }
    setLimitFeedback('')
    setWeekStart(prevWeekStart)
  }

  const handleCurrentWeek = () => {
    setSyncFeedback('')
    const currentWeek = getCurrentWeekMonday()
    if (hardEndDate && isAfterDate(currentWeek, hardEndDate)) {
      setWeekStart(toWeekMonday(hardEndDate))
      setLimitFeedback(`A semana atual está após a data limite do ano letivo (${formatDatePt(hardEndDate)}).`)
      return
    }
    setLimitFeedback('')
    setWeekStart(currentWeek)
  }

  const handleNextWeek = () => {
    setSyncFeedback('')
    if (nextWeekBlocked && hardEndDate) {
      setLimitFeedback(`Semanas após ${formatDatePt(hardEndDate)} estão bloqueadas.`)
      return
    }
    setLimitFeedback('')
    setWeekStart(nextWeekStart)
  }

  if (!effectiveTeacherId) {
    return (
      <div className="p-4">
        <CAlert color="danger" className="mb-0">
          Conta de professor sem perfil associado. Contacte um admin para associar o perfil docente.
        </CAlert>
      </div>
    )
  }

  if (isLoadingHorizon) {
    return (
      <div className="p-4">
        <CCard className="border-0 shadow-sm">
          <CCardBody className="py-4 d-flex align-items-center gap-2 text-muted">
            <CSpinner size="sm" />
            A carregar o seu horário semanal...
          </CCardBody>
        </CCard>
      </div>
    )
  }

  if (hasHorizonError && !effectiveHorizon) {
    return (
      <div className="p-4">
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

  if (hasWeekError && !hasWeekFallback) {
    weekContent = (
      <div className="text-center p-5 text-danger" style={{ fontSize: '0.9rem' }}>
        Não foi possível carregar o seu horário semanal. Verifique a ligação e volte a tentar dentro de alguns minutos.
      </div>
    )
  }

  return (
    <div className="p-4">
      <div className="d-flex justify-content-between align-items-start mb-4 flex-wrap gap-3">
        <div>
          <h2 className="mb-0 fw-bold text-dark">
            <CIcon icon={cilCalendar} className="me-2 text-primary" />
            Meus Horários
          </h2>
          <small className="text-muted">
            Vista pessoal semanal do professor. Verde = dada · Vermelho = furo · Amarelo = substituída.
          </small>
        </div>
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
              title={!canSubmit ? "Apenas pode submeter a semana quando todas as aulas estiverem dadas e no passado." : ""}
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
            Limite de navegação: {minWeekStart ? `de ${formatDatePt(minWeekStart)} ` : ''}até {formatDatePt(hardEndDate)}.
          </div>

          {hasHorizonError && effectiveHorizon ? (
            <CAlert color="warning" className="mb-3">
              {HORIZON_DEGRADED_FEEDBACK_MESSAGE}
            </CAlert>
          ) : null}

          {submitError && (
            <CAlert color="danger" className="mb-3">
              {submitError}
            </CAlert>
          )}

          {hasWeekFallback ? (
            <CAlert color="warning" className="mb-3">
              {WEEK_DEGRADED_FEEDBACK_MESSAGE}
            </CAlert>
          ) : null}

          {syncFeedback ? (
            <CAlert color="info" className="mb-3">
              {syncFeedback}
            </CAlert>
          ) : null}

          {limitFeedback ? (
            <CAlert color="warning" className="mb-3">
              {limitFeedback}
            </CAlert>
          ) : null}

          {weekContent}
        </CCardBody>
      </CCard>

      <LessonLogModal
        visible={Boolean(selectedSlot)}
        onClose={() => setSelectedSlot(null)}
        slot={selectedSlot}
      />

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
