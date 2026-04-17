import React, { useState, useEffect } from 'react'
import PropTypes from 'prop-types'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  CCard, CCardBody, CCardHeader, CAlert, CBadge, CSpinner,
  CButton, CButtonGroup, CFormSelect, CFormLabel, CRow, CCol, CProgress,
  CModal, CModalHeader, CModalTitle, CModalBody, CModalFooter,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import {
  cilCalendar, cilReload, cilCheckCircle, cilBan, cilWarning,
  cilArrowLeft, cilArrowRight, cilPeople, cilUser,
} from '@coreui/icons'
import {
  useDrafts, useScheduleDiff, useApproveDraft, useRejectDraft,
  useGenerateSchedule, useScheduleTaskStatus, useCancelScheduleTask,
  useClasses, useTeachers, useWeekSchedule, useClassDetails, useTimeslots, useCreateOccurrence,
} from '../hooks/useSchoolData'
import WeekGrid from '../components/WeekGrid'
import { getSubjectColor } from '../utils/subjectColors'
import { useAuthStore } from '../store'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const TERMINAL_STATUSES = ['SUCCESS', 'FAILURE', 'Success', 'Error', 'Impossible', 'REVOKED', 'CANCELED']
const ACTIVE_TASK_STORAGE_KEY_PREFIX = 'hz-schedule-active-task-org-'

const GENERATION_STATUS_LABELS = {
  PENDING:   'A aguardar worker…',
  FETCHING:  'A ler dados da escola…',
  SOLVING:   'CP-SAT a otimizar (pode demorar alguns minutos)…',
  EXPANDING: 'A expandir para datas reais…',
  SAVING:    'A guardar solução…',
  REVOKED:   'Cancelado.',
  CANCELED:  'Cancelado.',
  SUCCESS:   'Concluído!',
  FAILURE:   'Erro na geração.',
}

const STEP_BY_STATUS = {
  PENDING: 1,
  FETCHING: 2,
  SOLVING: 6,
  EXPANDING: 7,
  SAVING: 9,
  SUCCESS: 10,
}
const DEFAULT_TOTAL_STEPS = 10

// ---------------------------------------------------------------------------
// Module-scope helpers (SonarQube S7721)
// ---------------------------------------------------------------------------
function isPending(status) {
  return !!status && !TERMINAL_STATUSES.some(s => status.includes(s))
}

function getCurrentWeekMonday() {
  const today = new Date()
  const dayOfWeek = today.getDay()
  const diff = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
  const monday = new Date(today.getTime() + diff * 24 * 60 * 60 * 1000)
  return monday.toISOString().split('T')[0]
}

function addDays(dateStr, days) {
  const d = new Date(`${dateStr}T12:00:00`)
  d.setDate(d.getDate() + days)
  return d.toISOString().split('T')[0]
}

function formatWeekRange(weekStart) {
  const start = new Date(`${weekStart}T12:00:00`)
  const end   = new Date(`${weekStart}T12:00:00`)
  end.setDate(end.getDate() + 4)
  const short = { day: '2-digit', month: 'short' }
  const full  = { day: '2-digit', month: 'short', year: 'numeric' }
  return `${start.toLocaleDateString('pt-PT', short)} – ${end.toLocaleDateString('pt-PT', full)}`
}

function formatOperationalDate(dateStr) {
  if (!dateStr) return '—'
  const dateValue = new Date(`${dateStr}T12:00:00`)
  if (Number.isNaN(dateValue.getTime())) return dateStr
  return dateValue.toLocaleDateString('pt-PT', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}

function buildCreateOccurrenceErrorMessage(error) {
  const detail = error?.response?.data?.detail
  if (Array.isArray(detail) && detail.length > 0 && typeof detail[0]?.msg === 'string') {
    return detail[0].msg
  }
  if (typeof detail === 'string' && detail.trim()) {
    return detail
  }
  return 'Não foi possível criar a ocorrência para este bloco. Tente novamente.'
}

function resolveAlertColor(status) {
  if (status.includes('SUCCESS') || status.includes('Success')) return 'success'
  if (status.includes('REVOKED') || status.includes('CANCELED')) return 'warning'
  if (status.includes('FAILURE') || status.includes('Error') || status.includes('Impossible')) return 'danger'
  return 'info'
}

function resolveBusinessStatus(taskData) {
  const resultStatus = taskData?.result?.status
  if (resultStatus === 'Canceled') return 'warning'
  if (resultStatus === 'Error' || resultStatus === 'Impossible') return 'danger'
  if (resultStatus === 'Success') return 'success'
  return null
}

function getTaskStorageKey(orgId) {
  if (!orgId) return null
  return `${ACTIVE_TASK_STORAGE_KEY_PREFIX}${orgId}`
}

function readStoredTaskId(storageKey) {
  if (!storageKey) return null
  try {
    return localStorage.getItem(storageKey)
  } catch {
    return null
  }
}

function writeStoredTaskId(storageKey, taskId) {
  if (!storageKey || !taskId) return
  try {
    localStorage.setItem(storageKey, taskId)
  } catch {
    // no-op for environments without storage access
  }
}

function clearStoredTaskId(storageKey) {
  if (!storageKey) return
  try {
    localStorage.removeItem(storageKey)
  } catch {
    // no-op for environments without storage access
  }
}

function resolveProgress(taskData) {
  const serverProgress = taskData?.progress ?? taskData?.result?.progress
  if (serverProgress?.current && serverProgress?.total) {
    return {
      current: serverProgress.current,
      total: serverProgress.total,
    }
  }

  const status = taskData?.status ?? ''
  const fallbackCurrent = STEP_BY_STATUS[status]
  if (fallbackCurrent) {
    return {
      current: fallbackCurrent,
      total: DEFAULT_TOTAL_STEPS,
    }
  }
  return null
}

// ---------------------------------------------------------------------------
// KPI Sidebar — Sprint 4
// ---------------------------------------------------------------------------
const KPISidebar = ({ subjects }) => {
  if (!subjects || subjects.length === 0) {
    return (
      <div className="text-muted text-center p-3" style={{ fontSize: '0.85rem' }}>
        Nenhuma disciplina com progresso disponível.
      </div>
    )
  }

  return (
    <div className="d-flex flex-column gap-3">
      {subjects.map(subj => {
        const pct   = subj.overall_percentage ?? 0
        const color = getSubjectColor(subj.id)
        return (
          <div key={subj.id}>
            <div className="d-flex justify-content-between align-items-center mb-1">
              <div
                className="fw-semibold text-truncate me-2"
                style={{ fontSize: '0.8rem', borderLeft: `3px solid ${color}`, paddingLeft: '6px' }}
              >
                {subj.name}
              </div>
              <span className="text-muted" style={{ fontSize: '0.75rem', whiteSpace: 'nowrap' }}>
                {subj.completed_hours}h / {subj.total_hours}h
              </span>
            </div>
            <progress
              value={pct}
              max={100}
              style={{ width: '100%', height: '6px', accentColor: color, borderRadius: '3px' }}
              aria-label={`${subj.name}: ${pct.toFixed(1)}%`}
            />
            <div className="text-end text-muted" style={{ fontSize: '0.7rem', marginTop: '2px' }}>
              {pct.toFixed(1)}%
            </div>
          </div>
        )
      })}
    </div>
  )
}

KPISidebar.propTypes = {
  subjects: PropTypes.arrayOf(
    PropTypes.shape({
      id:                 PropTypes.number.isRequired,
      name:               PropTypes.string.isRequired,
      completed_hours:    PropTypes.number,
      total_hours:        PropTypes.number,
      overall_percentage: PropTypes.number,
    }),
  ),
}

// ---------------------------------------------------------------------------
// DraftPanel — Sprint 3
// ---------------------------------------------------------------------------
const DraftPanel = ({ draft, onApprove, onReject, isApproving, isRejecting }) => {
  const { data: diff, isLoading } = useScheduleDiff(draft.generation_id)
  const isWorking = isApproving || isRejecting

  return (
    <CAlert color="warning" className="border border-warning mb-4">
      <div className="d-flex align-items-start justify-content-between flex-wrap gap-3">
        <div>
          <div className="fw-bold mb-1">
            <CIcon icon={cilWarning} className="me-2" />
            Rascunho de Reparação Pendente
          </div>
          <div className="text-muted small mb-2">
            Geração{' '}<code>{draft.generation_id.substring(0, 8)}…</code>
            {draft.earliest_date && (
              <span>{' '}·{' '}{draft.earliest_date} → {draft.latest_date}</span>
            )}
          </div>
          {isLoading && <CSpinner size="sm" />}
          {!isLoading && diff && (
            <div className="d-flex gap-3 flex-wrap">
              <span className="badge bg-success-subtle text-success border border-success">
                +{diff.added} blocos adicionados
              </span>
              <span className="badge bg-danger-subtle text-danger border border-danger">
                -{diff.removed} blocos removidos
              </span>
              <span className="badge bg-secondary-subtle text-secondary border border-secondary">
                {diff.unchanged} sem alteração
              </span>
            </div>
          )}
        </div>
        <div className="d-flex gap-2 align-self-center">
          <CButton
            color="danger" variant="outline" size="sm"
            disabled={isWorking}
            onClick={() => { onReject(draft.generation_id) }}
          >
            {isRejecting
              ? <CSpinner size="sm" className="me-1" />
              : <CIcon icon={cilBan} className="me-1" />
            }
            Rejeitar
          </CButton>
          <CButton
            color="success" size="sm"
            disabled={isWorking}
            onClick={() => { onApprove(draft.generation_id) }}
          >
            {isApproving
              ? <CSpinner size="sm" className="me-1" />
              : <CIcon icon={cilCheckCircle} className="me-1" />
            }
            Aprovar e Ativar
          </CButton>
        </div>
      </div>
    </CAlert>
  )
}

DraftPanel.propTypes = {
  draft: PropTypes.shape({
    generation_id: PropTypes.string.isRequired,
    count:         PropTypes.number,
    earliest_date: PropTypes.string,
    latest_date:   PropTypes.string,
  }).isRequired,
  onApprove:   PropTypes.func.isRequired,
  onReject:    PropTypes.func.isRequired,
  isApproving: PropTypes.bool,
  isRejecting: PropTypes.bool,
}

// ---------------------------------------------------------------------------
// GenerationStatusPanel — Sprint 3
// ---------------------------------------------------------------------------
const GenerationStatusPanel = ({ taskId }) => {
  const { data: taskData } = useScheduleTaskStatus(taskId)

  if (!taskData) {
    return (
      <CAlert color="info" className="d-flex align-items-center gap-2 mb-4">
        <CSpinner size="sm" />
        A aguardar resposta do servidor…
      </CAlert>
    )
  }

  const status     = taskData.status ?? ''
  const isRunning  = isPending(status)
  const businessColor = resolveBusinessStatus(taskData)
  const alertColor = businessColor ?? resolveAlertColor(status)
  const label = taskData?.result?.status ?? GENERATION_STATUS_LABELS[status] ?? status
  const detail = taskData?.detail ?? taskData?.result?.detail
  const progress = resolveProgress(taskData)
  const progressValue = progress
    ? (progress.current / progress.total) * 100
    : 0
  const result     = taskData.result

  return (
    <CAlert color={alertColor} className="mb-4">
      <div className="d-flex align-items-center gap-2 mb-2">
        {isRunning && <CSpinner size="sm" />}
        <strong>{label}</strong>
      </div>
      {progress && (
        <div className="small mb-1">
          Etapa {progress.current}/{progress.total}
        </div>
      )}
      {isRunning && (
        <CProgress
          animated
          value={progressValue}
          className="mb-2"
          style={{ height: '6px' }}
        />
      )}
      {detail && (
        <div className="small mt-1">{detail}</div>
      )}
      {result?.is_draft && (
        <div className="small mt-1">
          Rascunho criado com{' '}<strong>{result.count}</strong>{' '}blocos.
          Reveja o diff acima e aprove ou rejeite.
        </div>
      )}
      {result?.mode === 'full' && result?.count && (
        <div className="small mt-1">
          Horário ativo atualizado com{' '}<strong>{result.count}</strong>{' '}blocos.
        </div>
      )}
      {result?.message && (
        <div className="small mt-1">{result.message}</div>
      )}
    </CAlert>
  )
}

GenerationStatusPanel.propTypes = {
  taskId: PropTypes.string.isRequired,
}

// ---------------------------------------------------------------------------
// PreflightErrorPanel — Sprint 3
// ---------------------------------------------------------------------------
const PreflightErrorPanel = ({ problems }) => (
  <CAlert color="danger" className="mb-4">
    <strong>Não é possível gerar o horário — pré-validação falhou:</strong>
    <ul className="mb-0 mt-2">
      {problems.map(p => <li key={p}>{p}</li>)}
    </ul>
  </CAlert>
)

PreflightErrorPanel.propTypes = {
  problems: PropTypes.arrayOf(PropTypes.string).isRequired,
}

const CreateOccurrenceModal = ({
  slot,
  onClose,
  onCreate,
  isCreating,
  errorMessage,
}) => {
  if (!slot) return null

  const shouldCreateOccurrence = slot.can_create_occurrence !== false

  const slotTime = slot.timeslot
    ? `${slot.timeslot.start_time} - ${slot.timeslot.end_time}`
    : '—'

  return (
    <CModal visible onClose={onClose} alignment="center">
      <CModalHeader>
        <CModalTitle>{shouldCreateOccurrence ? 'Criar Ocorrência' : 'Gerir Ocorrência'}</CModalTitle>
      </CModalHeader>
      <CModalBody>
        <CAlert color="light" className="mb-3">
          <div><strong>Data:</strong> {formatOperationalDate(slot.date)}</div>
          <div><strong>Horário:</strong> {slotTime}</div>
          <div><strong>Turma:</strong> {slot.class_info?.name ?? '—'}</div>
          <div><strong>Disciplina:</strong> {slot.subject?.name ?? '—'}</div>
          <div><strong>Docente previsto:</strong> {slot.teacher?.name ?? '—'}</div>
          <div><strong>Sala:</strong> {slot.room?.name ?? '—'}</div>
        </CAlert>

        {errorMessage ? (
          <CAlert color="danger" className="mb-0">{errorMessage}</CAlert>
        ) : null}
      </CModalBody>
      <CModalFooter>
        <CButton color="secondary" variant="outline" onClick={onClose}>
          Cancelar
        </CButton>
        <CButton color="primary" onClick={onCreate} disabled={shouldCreateOccurrence && isCreating}>
          {shouldCreateOccurrence && isCreating ? (
            <>
              <CSpinner size="sm" className="me-2" />
              A criar...
            </>
          ) : (shouldCreateOccurrence ? 'Criar Ocorrência' : 'Ir para Faltas')}
        </CButton>
      </CModalFooter>
    </CModal>
  )
}

CreateOccurrenceModal.propTypes = {
  slot: PropTypes.shape({
    schedule_output_id: PropTypes.number,
    occurrence_id: PropTypes.number,
    can_create_occurrence: PropTypes.bool,
    can_decide_occurrence: PropTypes.bool,
    date: PropTypes.string,
    timeslot: PropTypes.shape({
      start_time: PropTypes.string,
      end_time: PropTypes.string,
    }),
    class_info: PropTypes.shape({ name: PropTypes.string, id: PropTypes.number }),
    subject: PropTypes.shape({ name: PropTypes.string }),
    teacher: PropTypes.shape({ name: PropTypes.string }),
    room: PropTypes.shape({ name: PropTypes.string }),
  }),
  onClose: PropTypes.func.isRequired,
  onCreate: PropTypes.func.isRequired,
  isCreating: PropTypes.bool,
  errorMessage: PropTypes.string,
}

// ---------------------------------------------------------------------------
// Schedules — Main Page
// ---------------------------------------------------------------------------
const Schedules = () => {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const user = useAuthStore((state) => state.user)
  const orgId = user?.orgId ?? null
  const isAdmin = user?.role === 'admin'
  const isTeacher = user?.role === 'teacher'
  const teacherOwnId = user?.teacherId ?? null
  const canConsultSchedule = isAdmin || (isTeacher && Boolean(teacherOwnId))
  const taskStorageKey = getTaskStorageKey(orgId)

  // Sprint 3 state
  const [mode, setMode]                       = useState('full')
  const [activeTaskId, setActiveTaskId]       = useState(null)
  const [preflightErrors, setPreflightErrors] = useState([])

  // Sprint 4 state
  const [viewMode, setViewMode]                   = useState(isTeacher ? 'teacher' : 'class')
  const [selectedClassId, setSelectedClassId]     = useState('')
  const [selectedTeacherId, setSelectedTeacherId] = useState(
    isTeacher && teacherOwnId ? String(teacherOwnId) : ''
  )
  const [weekStart, setWeekStart]                 = useState(getCurrentWeekMonday)
  const [selectedOperationalSlot, setSelectedOperationalSlot] = useState(null)
  const [createOccurrenceError, setCreateOccurrenceError] = useState('')
  const [generationActionError, setGenerationActionError] = useState('')

  // Sprint 3 hooks
  const { data: drafts = [], refetch: refetchDrafts } = useDrafts()
  const generateMutation = useGenerateSchedule()
  const cancelGenerationMutation = useCancelScheduleTask()
  const approveMutation  = useApproveDraft()
  const rejectMutation   = useRejectDraft()
  const createOccurrenceMutation = useCreateOccurrence()
  const { data: taskData } = useScheduleTaskStatus(activeTaskId)

  // Sprint 4 hooks
  const { data: classes  = [] } = useClasses({ enabled: isAdmin })
  const { data: teachers = [] } = useTeachers({ enabled: isAdmin })
  const { data: timeslots = [] } = useTimeslots()

  const classId   = viewMode === 'class'   && selectedClassId   ? Number.parseInt(selectedClassId, 10)   : null
  const teacherId = viewMode === 'teacher' && selectedTeacherId ? Number.parseInt(selectedTeacherId, 10) : null

  const {
    data: weekSlots = [],
    isFetching: loadingWeek,
    isError: weekLoadError,
  } = useWeekSchedule(classId, teacherId, weekStart)
  const { data: classDetails } = useClassDetails(classId)

  const classSubjects = classDetails?.subjects ?? []

  // Refresh drafts after a terminal generation task
  useEffect(() => {
    const status = taskData?.status ?? ''
    if (activeTaskId && TERMINAL_STATUSES.some(s => status.includes(s))) {
      void refetchDrafts()
      clearStoredTaskId(taskStorageKey)

      const businessStatus = taskData?.result?.status
      if (businessStatus === 'Success') {
        // Task accepted != schedule persisted. Refresh only when business result confirms success.
        void queryClient.invalidateQueries({ queryKey: ['weekSchedule'] })
        void queryClient.invalidateQueries({ queryKey: ['schedule'] })
        void queryClient.invalidateQueries({ queryKey: ['timeslots'] })
      }
    }
  }, [taskData, activeTaskId, refetchDrafts, queryClient, taskStorageKey])

  useEffect(() => {
    if (!isAdmin || activeTaskId) {
      return
    }

    const storedTaskId = readStoredTaskId(taskStorageKey)
    if (storedTaskId) {
      setActiveTaskId(storedTaskId)
    }
  }, [isAdmin, activeTaskId, taskStorageKey])

  useEffect(() => {
    if (!isAdmin) {
      return
    }

    if (activeTaskId) {
      writeStoredTaskId(taskStorageKey, activeTaskId)
    }
  }, [isAdmin, activeTaskId, taskStorageKey])

  useEffect(() => {
    if (!isTeacher || !teacherOwnId) {
      return
    }

    setViewMode('teacher')
    setSelectedClassId('')
    setSelectedTeacherId(String(teacherOwnId))
  }, [isTeacher, teacherOwnId])

  const handleGenerate = async () => {
    setGenerationActionError('')
    setPreflightErrors([])
    setActiveTaskId(null)
    try {
      const result = await generateMutation.mutateAsync(mode)
      if (result?.task_id) setActiveTaskId(result.task_id)
    } catch (err) {
      const problems = err?.response?.data?.detail?.problems
      if (Array.isArray(problems)) setPreflightErrors(problems)
    }
  }

  const handleCancelGeneration = () => {
    if (!activeTaskId) {
      return
    }

    setGenerationActionError('')
    cancelGenerationMutation.mutate(activeTaskId, {
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: ['schedule-task', orgId, activeTaskId] })
      },
      onError: () => {
        setGenerationActionError('Não foi possível cancelar a geração. Tente novamente.')
      },
    })
  }

  const isGenerating = isPending(taskData?.status)
  const weekLabel    = formatWeekRange(weekStart)
  const hasSelection = Boolean(classId || teacherId)
  const showKPI      = viewMode === 'class' && Boolean(classId)
  const gridCols     = showKPI ? 8 : 12

  const closeCreateOccurrenceModal = () => {
    setSelectedOperationalSlot(null)
    setCreateOccurrenceError('')
  }

  const navigateToAbsencesWithSlotContext = ({ occurrenceId, slotContext }) => {
    const params = new URLSearchParams()
    if (occurrenceId) {
      params.set('occurrence_id', String(occurrenceId))
    }
    if (slotContext?.class_info?.id) {
      params.set('class_id', String(slotContext.class_info.id))
    }
    if (slotContext?.date) {
      params.set('date_from', slotContext.date)
      params.set('date_to', slotContext.date)
    }

    const query = params.toString()
    navigate(query ? `/absences?${query}` : '/absences')
  }

  const openCreateOccurrenceModal = (slot) => {
    if (!isAdmin) {
      return
    }
    setSelectedOperationalSlot(slot)
    setCreateOccurrenceError('')
  }

  const handleCreateOccurrence = () => {
    const scheduleOutputId = selectedOperationalSlot?.schedule_output_id
    if (!scheduleOutputId) {
      return
    }

    const canCreateOccurrence = selectedOperationalSlot?.can_create_occurrence !== false
    const canDecideOccurrence = Boolean(selectedOperationalSlot?.can_decide_occurrence)
    if (!canCreateOccurrence && canDecideOccurrence) {
      navigateToAbsencesWithSlotContext({
        occurrenceId: selectedOperationalSlot?.occurrence_id,
        slotContext: selectedOperationalSlot,
      })
      closeCreateOccurrenceModal()
      return
    }

    setCreateOccurrenceError('')
    createOccurrenceMutation.mutate(
      { scheduleOutputId },
      {
        onSuccess: (occurrence) => {
          navigateToAbsencesWithSlotContext({
            occurrenceId: occurrence?.id,
            slotContext: selectedOperationalSlot,
          })
          closeCreateOccurrenceModal()
        },
        onError: (error) => {
          setCreateOccurrenceError(buildCreateOccurrenceErrorMessage(error))
        },
      }
    )
  }

  let weekGridContent = (
    <div className="text-center p-5 text-muted">
      <CIcon icon={cilCalendar} style={{ fontSize: '2rem', opacity: 0.35 }} />
      <div className="mt-2">
        Selecione uma turma ou professor para visualizar o horário da semana.
      </div>
    </div>
  )

  if (hasSelection) {
    weekGridContent = (
      <WeekGrid
        slots={weekSlots}
        isLoading={loadingWeek}
        baseTimeslots={timeslots}
        weekStart={weekStart}
        isOperationalEnabled={isAdmin}
        onOpenOperationalAction={openCreateOccurrenceModal}
      />
    )
  }

  if (hasSelection && weekLoadError) {
    weekGridContent = (
      <div className="text-center p-5 text-danger" style={{ fontSize: '0.9rem' }}>
        Erro ao carregar o horário da semana. Tente novamente.
      </div>
    )
  }

  if (!canConsultSchedule) {
    return (
      <div className="p-4">
        <CAlert color="danger" className="mb-0">
          Conta de professor sem perfil associado. Contacte um admin para associar o perfil docente.
        </CAlert>
      </div>
    )
  }

  return (
    <div className="p-4">

      {selectedOperationalSlot ? (
        <CreateOccurrenceModal
          slot={selectedOperationalSlot}
          onClose={closeCreateOccurrenceModal}
          onCreate={handleCreateOccurrence}
          isCreating={createOccurrenceMutation.isPending}
          errorMessage={createOccurrenceError}
        />
      ) : null}

      {/* ── Page header ── */}
      <div className="d-flex justify-content-between align-items-start mb-4 flex-wrap gap-3">
        <div>
          <h2 className="mb-0 fw-bold text-dark">
            <CIcon icon={cilCalendar} className="me-2 text-primary" />
            Horários Escolares
          </h2>
          <small className="text-muted">
            {isAdmin ? 'Visualize e gere horários por CP-SAT.' : 'Visualize o seu horário semanal.'}
            {' '}Verde = dado · Vermelho = furo · Amarelo = substituído · Cor = planeado.
          </small>
        </div>

        {/* Generation controls */}
        {isAdmin ? (
          <CCard className="border-0 shadow-sm">
            <CCardBody className="py-2 px-3">
              <CRow className="g-2 align-items-end">
                <CCol xs="auto">
                  <CFormLabel htmlFor="modeSelect" className="small mb-1 text-muted">Modo</CFormLabel>
                  <CFormSelect
                    id="modeSelect"
                    size="sm"
                    value={mode}
                    onChange={(e) => setMode(e.target.value)}
                    disabled={isGenerating}
                    style={{ minWidth: '160px' }}
                  >
                    <option value="full">Completo (de raiz)</option>
                    <option value="repair">Reparação (mín. alterações)</option>
                  </CFormSelect>
                </CCol>
                <CCol xs="auto">
                  <CButton
                    color="primary" size="sm"
                    disabled={isGenerating || generateMutation.isPending}
                    onClick={() => { void handleGenerate() }}
                  >
                    {isGenerating
                      ? <><CSpinner size="sm" className="me-1" />A gerar…</>
                      : <><CIcon icon={cilReload} className="me-1" />Gerar Horário</>
                    }
                  </CButton>
                </CCol>
                {activeTaskId && isGenerating && (
                  <CCol xs="auto">
                    <CButton
                      color="danger"
                      variant="outline"
                      size="sm"
                      disabled={cancelGenerationMutation.isPending}
                      onClick={handleCancelGeneration}
                    >
                      {cancelGenerationMutation.isPending
                        ? <><CSpinner size="sm" className="me-1" />A cancelar…</>
                        : <><CIcon icon={cilBan} className="me-1" />Cancelar geração</>
                      }
                    </CButton>
                  </CCol>
                )}
              </CRow>
            </CCardBody>
          </CCard>
        ) : null}
      </div>

      {/* ── Sprint 3: preflight / status / drafts ── */}
      {isAdmin ? (
        <>
          {preflightErrors.length > 0 && <PreflightErrorPanel problems={preflightErrors} />}
          {generationActionError && (
            <CAlert color="danger" className="mb-4">
              {generationActionError}
            </CAlert>
          )}
          {activeTaskId && <GenerationStatusPanel taskId={activeTaskId} />}
          {[...drafts].sort((a, b) => a.generation_id.localeCompare(b.generation_id)).map(draft => (
            <DraftPanel
              key={draft.generation_id}
              draft={draft}
              onApprove={(genId) => approveMutation.mutateAsync(genId)}
              onReject={(genId) => rejectMutation.mutateAsync(genId)}
              isApproving={approveMutation.isPending}
              isRejecting={rejectMutation.isPending}
            />
          ))}
        </>
      ) : null}

      {/* ── Sprint 4: View controls ── */}
      <CCard className="border-0 shadow-sm mb-4">
        <CCardBody className="py-2 px-3">
          <CRow className="g-3 align-items-end flex-wrap">

            {/* View mode toggle */}
            {isAdmin ? (
              <CCol xs="auto">
                <div className="small text-muted mb-1">Vista por</div>
                <CButtonGroup size="sm">
                  <CButton
                    color={viewMode === 'class' ? 'primary' : 'outline-secondary'}
                    onClick={() => setViewMode('class')}
                  >
                    <CIcon icon={cilPeople} className="me-1" />
                    Turma
                  </CButton>
                  <CButton
                    color={viewMode === 'teacher' ? 'primary' : 'outline-secondary'}
                    onClick={() => setViewMode('teacher')}
                  >
                    <CIcon icon={cilUser} className="me-1" />
                    Professor
                  </CButton>
                </CButtonGroup>
              </CCol>
            ) : (
              <CCol xs="auto">
                <div className="small text-muted mb-1">Vista</div>
                <CBadge color="info">Professor (somente próprio horário)</CBadge>
              </CCol>
            )}

            {/* Class selector */}
            {isAdmin && viewMode === 'class' && (
              <CCol xs="auto">
                <CFormLabel htmlFor="classSelect" className="small mb-1 text-muted">Turma</CFormLabel>
                <CFormSelect
                  id="classSelect"
                  size="sm"
                  value={selectedClassId}
                  onChange={(e) => setSelectedClassId(e.target.value)}
                  style={{ minWidth: '200px' }}
                >
                  <option value="">— Selecionar Turma —</option>
                  {[...classes].sort((a, b) => a.name.localeCompare(b.name)).map(c => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </CFormSelect>
              </CCol>
            )}

            {/* Teacher selector */}
            {isAdmin && viewMode === 'teacher' && (
              <CCol xs="auto">
                <CFormLabel htmlFor="teacherSelect" className="small mb-1 text-muted">Professor</CFormLabel>
                <CFormSelect
                  id="teacherSelect"
                  size="sm"
                  value={selectedTeacherId}
                  onChange={(e) => setSelectedTeacherId(e.target.value)}
                  style={{ minWidth: '200px' }}
                >
                  <option value="">— Selecionar Professor —</option>
                  {[...teachers].sort((a, b) => a.name.localeCompare(b.name)).map(t => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </CFormSelect>
              </CCol>
            )}

            {/* Week navigation */}
            <CCol xs="auto" className="ms-auto">
              <div className="d-flex align-items-center gap-2">
                <CButton
                  color="outline-secondary" size="sm"
                  onClick={() => setWeekStart(prev => addDays(prev, -7))}
                  title="Semana anterior"
                >
                  <CIcon icon={cilArrowLeft} />
                </CButton>
                <span className="small fw-semibold" style={{ minWidth: '200px', textAlign: 'center' }}>
                  {weekLabel}
                </span>
                <CButton
                  color="outline-secondary" size="sm"
                  onClick={() => setWeekStart(prev => addDays(prev, 7))}
                  title="Próxima semana"
                >
                  <CIcon icon={cilArrowRight} />
                </CButton>
                <CButton
                  color="outline-primary" size="sm"
                  onClick={() => setWeekStart(getCurrentWeekMonday())}
                  title="Ir para a semana atual"
                >
                  Hoje
                </CButton>
              </div>
            </CCol>
          </CRow>
        </CCardBody>
      </CCard>

      {/* ── Sprint 4: Grid + KPI ── */}
      <CRow className="g-4">

        {/* Week Grid */}
        <CCol lg={gridCols}>
          <CCard className="border-0 shadow-sm h-100">
            <CCardHeader className="bg-transparent fw-semibold d-flex align-items-center justify-content-between">
              <span>
                Grelha Semanal
                {drafts.length > 0 && (
                  <CBadge color="warning" className="ms-2">
                    {drafts.length} rascunho{drafts.length === 1 ? '' : 's'} pendente{drafts.length === 1 ? '' : 's'}
                  </CBadge>
                )}
              </span>
              {loadingWeek && <CSpinner size="sm" className="text-secondary" />}
            </CCardHeader>
            <CCardBody className="p-0">
              {weekGridContent}
            </CCardBody>
          </CCard>
        </CCol>

        {/* KPI Sidebar — class mode only */}
        {showKPI && (
          <CCol lg={4}>
            <CCard className="border-0 shadow-sm h-100">
              <CCardHeader className="bg-transparent fw-semibold">
                Progresso por Disciplina
              </CCardHeader>
              <CCardBody>
                <KPISidebar subjects={classSubjects} />
              </CCardBody>
            </CCard>
          </CCol>
        )}

      </CRow>
    </div>
  )
}

export default Schedules
