import React, { useState, useEffect } from 'react'
import PropTypes from 'prop-types'
import { useNavigate, useLocation } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  CCard, CCardBody, CCardHeader, CAlert, CBadge, CSpinner,
  CButton, CButtonGroup, CFormSelect, CFormLabel, CRow, CCol,
  CModal, CModalHeader, CModalTitle, CModalBody, CModalFooter,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import {
  cilCalendar, cilReload, cilBan,
  cilArrowLeft, cilArrowRight, cilPeople, cilUser, cilCalendarCheck,
} from '@coreui/icons'
import {
  useDrafts, useApproveDraft, useRejectDraft,
  useGenerateSchedule, useScheduleTaskStatus, useCancelScheduleTask,
  useClasses, useTeachers, useWeekSchedule, useClassDetails, useTimeslots,
} from '../hooks/useSchoolData'
import WeekGrid from '../components/WeekGrid'
import LessonLogModal from '../components/LessonLogModal'
import KPISidebar from '../components/schedules/KPISidebar'
import DraftPanel from '../components/schedules/DraftPanel'
import GenerationStatusPanel, { isPending, TERMINAL_STATUSES } from '../components/schedules/GenerationStatusPanel'
import PreflightErrorPanel from '../components/schedules/PreflightErrorPanel'
import { useAuthStore } from '../store'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const ACTIVE_TASK_STORAGE_KEY_PREFIX = 'hz-schedule-active-task-org-'

// ---------------------------------------------------------------------------
// Module-scope helpers (SonarQube S7721)
// ---------------------------------------------------------------------------
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

// ---------------------------------------------------------------------------
// Schedules — Main Page
// ---------------------------------------------------------------------------
const Schedules = () => {
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()
  const user = useAuthStore((state) => state.user)
  const orgId = user?.orgId ?? null
  const isAdmin = user?.role === 'admin'
  const isTeacher = user?.role === 'teacher'
  const teacherOwnId = user?.teacherId ?? null
  const canConsultSchedule = isAdmin || (isTeacher && Boolean(teacherOwnId))
  const taskStorageKey = getTaskStorageKey(orgId)

  // Parse query params for cross-navigation (Fase 7.4)
  const urlParams = new URLSearchParams(location.search)
  const urlTeacherId = urlParams.get('teacherId')
  const urlWeekStart = urlParams.get('weekStart')

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
  const [weekStart, setWeekStart]                 = useState(() => {
    if (urlWeekStart && /^\d{4}-\d{2}-\d{2}$/.test(urlWeekStart)) {
      return urlWeekStart
    }
    return getCurrentWeekMonday()
  })
  // Bug #4: Keep weekStart in sync with URL query param changes (cross-navigation)
  useEffect(() => {
    if (urlWeekStart && /^\d{4}-\d{2}-\d{2}$/.test(urlWeekStart) && urlWeekStart !== weekStart) {
      setWeekStart(urlWeekStart)
    }
  }, [urlWeekStart, weekStart])
  const [adminLessonLogSlot, setAdminLessonLogSlot] = useState(null)
  const [generationActionError, setGenerationActionError] = useState('')

  // Sprint 3 hooks
  const { data: drafts = [], refetch: refetchDrafts } = useDrafts()
  const generateMutation = useGenerateSchedule()
  const cancelGenerationMutation = useCancelScheduleTask()
  const approveMutation  = useApproveDraft()
  const rejectMutation   = useRejectDraft()
  const { data: taskData } = useScheduleTaskStatus(activeTaskId)

  // Sprint 4 hooks
  const { data: classes  = [] } = useClasses({ enabled: isAdmin })
  const { data: teachers = [] } = useTeachers({ enabled: isAdmin })
  const { data: timeslots = [] } = useTimeslots()

  // Apply URL query params for cross-navigation (Fase 7.4)
  useEffect(() => {
    if (!isAdmin || !urlTeacherId) return
    const teacherExists = teachers.some((t) => String(t.id) === urlTeacherId)
    if (teacherExists) {
      setViewMode('teacher')
      setSelectedTeacherId(urlTeacherId)
      setSelectedClassId('')
    }
  }, [isAdmin, urlTeacherId, teachers])

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
      if (Array.isArray(problems)) {
        setPreflightErrors(problems)
      } else {
        setGenerationActionError(err?.response?.data?.detail || err?.message || 'Erro ao iniciar a geração. Verifique a ligação e tente novamente.')
      }
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

  const openCreateOccurrenceModal = (slot) => {
    if (!isAdmin) {
      return
    }
    setAdminLessonLogSlot(slot)
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

      {adminLessonLogSlot ? (
        <LessonLogModal
          visible={Boolean(adminLessonLogSlot)}
          onClose={() => setAdminLessonLogSlot(null)}
          slot={adminLessonLogSlot}
          isAdmin={isAdmin}
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
            {isAdmin ? 'Consulte e atualize os horários da escola.' : 'Visualize o seu horário semanal.'}
            {' '}Verde = dada · Vermelho = furo · Amarelo = substituída · Cor = planeado.
          </small>
        </div>

        {isAdmin && (
          <CButton
            color="primary"
            variant="outline"
            size="sm"
            onClick={() => navigate(`/timesheets?weekStart=${weekStart}`)}
          >
            <CIcon icon={cilCalendarCheck} className="me-1" />
            Ver Aprovações
          </CButton>
        )}

        {/* Generation controls */}
        {isAdmin && (
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
        )}
      </div>

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
              onApprove={async (genId) => {
                try { await approveMutation.mutateAsync(genId) }
                catch (err) { setGenerationActionError(err.response?.data?.detail || 'Erro ao aprovar rascunho.') }
              }}
              onReject={async (genId) => {
                try { await rejectMutation.mutateAsync(genId) }
                catch (err) { setGenerationActionError(err.response?.data?.detail || 'Erro ao rejeitar rascunho.') }
              }}
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
                  color="secondary" variant="outline" size="sm"
                  onClick={() => setWeekStart(prev => addDays(prev, -7))}
                  title="Semana anterior"
                >
                  <CIcon icon={cilArrowLeft} />
                </CButton>
                <span className="small fw-semibold" style={{ minWidth: '200px', textAlign: 'center' }}>
                  {weekLabel}
                </span>
                <CButton
                  color="secondary" variant="outline" size="sm"
                  onClick={() => setWeekStart(prev => addDays(prev, 7))}
                  title="Próxima semana"
                >
                  <CIcon icon={cilArrowRight} />
                </CButton>
                <CButton
                  color="primary" variant="outline" size="sm"
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
