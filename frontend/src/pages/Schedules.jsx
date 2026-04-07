import React, { useState, useEffect } from 'react'
import PropTypes from 'prop-types'
import { useQueryClient } from '@tanstack/react-query'
import {
  CCard, CCardBody, CCardHeader, CAlert, CBadge, CSpinner,
  CButton, CButtonGroup, CFormSelect, CFormLabel, CRow, CCol, CProgress,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import {
  cilCalendar, cilReload, cilCheckCircle, cilBan, cilWarning,
  cilArrowLeft, cilArrowRight, cilPeople, cilUser,
} from '@coreui/icons'
import {
  useDrafts, useScheduleDiff, useApproveDraft, useRejectDraft,
  useGenerateSchedule, useScheduleTaskStatus,
  useClasses, useTeachers, useWeekSchedule, useClassDetails, useTimeslots,
} from '../hooks/useSchoolData'
import WeekGrid from '../components/WeekGrid'
import { getSubjectColor } from '../utils/subjectColors'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const TERMINAL_STATUSES = ['SUCCESS', 'FAILURE', 'Success', 'Error', 'Impossible', 'REVOKED']

const GENERATION_STATUS_LABELS = {
  PENDING:   'A aguardar worker…',
  FETCHING:  'A ler dados da escola…',
  SOLVING:   'CP-SAT a otimizar (pode demorar alguns minutos)…',
  EXPANDING: 'A expandir para datas reais…',
  SAVING:    'A guardar solução…',
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

function resolveAlertColor(status) {
  if (status.includes('SUCCESS') || status.includes('Success')) return 'success'
  if (status.includes('FAILURE') || status.includes('Error') || status.includes('Impossible')) return 'danger'
  return 'info'
}

function resolveBusinessStatus(taskData) {
  const resultStatus = taskData?.result?.status
  if (resultStatus === 'Error' || resultStatus === 'Impossible') return 'danger'
  if (resultStatus === 'Success') return 'success'
  return null
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

// ---------------------------------------------------------------------------
// Schedules — Main Page
// ---------------------------------------------------------------------------
const Schedules = () => {
  const queryClient = useQueryClient()

  // Sprint 3 state
  const [mode, setMode]                       = useState('full')
  const [activeTaskId, setActiveTaskId]       = useState(null)
  const [preflightErrors, setPreflightErrors] = useState([])

  // Sprint 4 state
  const [viewMode, setViewMode]                   = useState('class')
  const [selectedClassId, setSelectedClassId]     = useState('')
  const [selectedTeacherId, setSelectedTeacherId] = useState('')
  const [weekStart, setWeekStart]                 = useState(getCurrentWeekMonday)

  // Sprint 3 hooks
  const { data: drafts = [], refetch: refetchDrafts } = useDrafts()
  const generateMutation = useGenerateSchedule()
  const approveMutation  = useApproveDraft()
  const rejectMutation   = useRejectDraft()
  const { data: taskData } = useScheduleTaskStatus(activeTaskId)

  // Sprint 4 hooks
  const { data: classes  = [] } = useClasses()
  const { data: teachers = [] } = useTeachers()
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

      const businessStatus = taskData?.result?.status
      if (businessStatus === 'Success') {
        // Task accepted != schedule persisted. Refresh only when business result confirms success.
        void queryClient.invalidateQueries({ queryKey: ['weekSchedule'] })
        void queryClient.invalidateQueries({ queryKey: ['schedule'] })
        void queryClient.invalidateQueries({ queryKey: ['timeslots'] })
      }
    }
  }, [taskData, activeTaskId, refetchDrafts, queryClient])

  const handleGenerate = async () => {
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

  const isGenerating = isPending(taskData?.status)
  const weekLabel    = formatWeekRange(weekStart)
  const hasSelection = Boolean(classId || teacherId)
  const showKPI      = viewMode === 'class' && Boolean(classId)
  const gridCols     = showKPI ? 8 : 12

  let weekGridContent = (
    <div className="text-center p-5 text-muted">
      <CIcon icon={cilCalendar} style={{ fontSize: '2rem', opacity: 0.35 }} />
      <div className="mt-2">
        Selecione uma turma ou professor para visualizar o horário da semana.
      </div>
    </div>
  )

  if (hasSelection) {
    weekGridContent = <WeekGrid slots={weekSlots} isLoading={loadingWeek} baseTimeslots={timeslots} weekStart={weekStart} />
  }

  if (hasSelection && weekLoadError) {
    weekGridContent = (
      <div className="text-center p-5 text-danger" style={{ fontSize: '0.9rem' }}>
        Erro ao carregar o horário da semana. Tente novamente.
      </div>
    )
  }

  return (
    <div className="p-4">

      {/* ── Page header ── */}
      <div className="d-flex justify-content-between align-items-start mb-4 flex-wrap gap-3">
        <div>
          <h2 className="mb-0 fw-bold text-dark">
            <CIcon icon={cilCalendar} className="me-2 text-primary" />
            Horários Escolares
          </h2>
          <small className="text-muted">
            Visualize e gere horários por CP-SAT.
            {' '}Verde = dado · Vermelho = furo · Amarelo = substituído · Cor = planeado.
          </small>
        </div>

        {/* Generation controls */}
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
            </CRow>
          </CCardBody>
        </CCard>
      </div>

      {/* ── Sprint 3: preflight / status / drafts ── */}
      {preflightErrors.length > 0 && <PreflightErrorPanel problems={preflightErrors} />}
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

      {/* ── Sprint 4: View controls ── */}
      <CCard className="border-0 shadow-sm mb-4">
        <CCardBody className="py-2 px-3">
          <CRow className="g-3 align-items-end flex-wrap">

            {/* View mode toggle */}
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

            {/* Class selector */}
            {viewMode === 'class' && (
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
            {viewMode === 'teacher' && (
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
