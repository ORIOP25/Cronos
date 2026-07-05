import React, { useState, useEffect } from 'react'
import PropTypes from 'prop-types'
import { useLocation } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  CCard, CCardBody, CCardHeader, CAlert, CBadge, CSpinner,
  CButton, CButtonGroup, CFormSelect, CFormLabel, CRow, CCol,
  } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import {
  cilCalendar, cilReload, cilBan,
  cilArrowLeft, cilArrowRight, cilPeople, cilUser,
} from '@coreui/icons'
import {
  useSchedulerStatus, useCurrentDraftSummary, useApproveDraft, useRejectDraft,
  useGenerateSchedule, useScheduleTaskStatus, useCancelScheduleTask,
  useClasses, useTeachers, useWeekSchedule, useClassDetails, useTimeslots,
  useCurrentMember,
} from '../hooks/useSchoolData'
import WeekGrid from '../components/WeekGrid'
import LessonLogModal from '../components/LessonLogModal'
import KPISidebar from '../components/schedules/KPISidebar'
import DraftPanel from '../components/schedules/DraftPanel'
import GenerationStatusPanel from '../components/schedules/GenerationStatusPanel'
import PreflightErrorPanel from '../components/schedules/PreflightErrorPanel'
import { useOrganization } from '@clerk/react'
import { useRole } from '../hooks/useRole'
import { getCurrentWeekMonday, addDays, formatWeekRange } from '../utils/formatUtils'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const ACTIVE_JOB_STORAGE_KEY_PREFIX = 'hz-schedule-active-job-org-'
const VIEW_STORAGE_KEY_PREFIX = 'hz-schedule-view-org-'
const STALE_DRAFT_MESSAGE = (
  'This draft is no longer current.\n\n'
  + 'Schedule conditions changed after it was generated. Regenerate the draft to continue.'
)

function getDraftMutationErrorMessage(error, fallback) {
  const detail = error?.response?.data?.detail
  if (detail?.draft_state === 'STALE') return STALE_DRAFT_MESSAGE
  return detail?.message || (typeof detail === 'string' ? detail : null) || fallback
}

function getViewStorageKey(orgId) {
  if (!orgId) return null
  return `${VIEW_STORAGE_KEY_PREFIX}${orgId}`
}

function readStoredView(storageKey) {
  if (!storageKey) return null
  try {
    const raw = localStorage.getItem(storageKey)
    if (!raw) return null
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function writeStoredView(storageKey, viewState) {
  if (!storageKey) return
  try {
    localStorage.setItem(storageKey, JSON.stringify(viewState))
  } catch {
    // no-op
  }
}

function getJobStorageKey(orgId) {
  if (!orgId) return null
  return `${ACTIVE_JOB_STORAGE_KEY_PREFIX}${orgId}`
}

function readStoredJobId(storageKey) {
  if (!storageKey) return null
  try {
    return localStorage.getItem(storageKey)
  } catch {
    return null
  }
}

function writeStoredJobId(storageKey, jobId) {
  if (!storageKey || !jobId) return
  try {
    localStorage.setItem(storageKey, String(jobId))
  } catch {
    // no-op for environments without storage access
  }
}

function clearStoredJobId(storageKey) {
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
  const location = useLocation()
  const queryClient = useQueryClient()
  const { organization } = useOrganization()
  const orgId = organization?.id ?? null
  const { isAdmin, isTeacher } = useRole()
  const { data: currentMember } = useCurrentMember()
  const teacherOwnId = currentMember?.teacher_id ?? null
  const canConsultSchedule = isAdmin || (isTeacher && Boolean(teacherOwnId))
  const jobStorageKey = getJobStorageKey(orgId)
  const viewStorageKey = getViewStorageKey(orgId)

  // Parse query params for cross-navigation (Fase 7.4)
  const urlParams = new URLSearchParams(location.search)
  const urlTeacherId = urlParams.get('teacherId')
  const urlWeekStart = urlParams.get('weekStart')
  const hasUrlParams = Boolean(urlTeacherId || urlWeekStart)

  // Restore persisted view state (admin only, URL params take priority)
  const storedView = !hasUrlParams && isAdmin ? readStoredView(viewStorageKey) : null

  // Sprint 3 state
  const [activeJobId, setActiveJobId]         = useState(null)
  const [preflightErrors, setPreflightErrors] = useState([])

  // Sprint 4 state
  const [viewMode, setViewMode]                   = useState(
    isTeacher ? 'teacher' : (storedView?.viewMode || 'class')
  )
  const [selectedClassId, setSelectedClassId]     = useState(
    storedView?.selectedClassId || ''
  )
  const [selectedTeacherId, setSelectedTeacherId] = useState(() => {
    if (isTeacher && teacherOwnId) return String(teacherOwnId)
    return storedView?.selectedTeacherId || ''
  })
  const [weekStart, setWeekStart]                 = useState(() => {
    if (urlWeekStart && /^\d{4}-\d{2}-\d{2}$/.test(urlWeekStart)) {
      return urlWeekStart
    }
    return storedView?.weekStart || getCurrentWeekMonday()
  })
  // Bug #4: Keep weekStart in sync with URL query param changes (cross-navigation)
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (urlWeekStart && /^\d{4}-\d{2}-\d{2}$/.test(urlWeekStart) && urlWeekStart !== weekStart) {
      setWeekStart(urlWeekStart)
    }
  }, [urlWeekStart, weekStart])
  /* eslint-enable react-hooks/set-state-in-effect */
  const [adminLessonLogSlot, setAdminLessonLogSlot] = useState(null)
  const [generationActionError, setGenerationActionError] = useState('')

  // Sprint 3 hooks
  const { data: schedulerStatus, refetch: refetchSchedulerStatus } = useSchedulerStatus()
  const hasPendingDraft = Boolean(schedulerStatus?.pending_draft_id)
  const { data: currentDraft, refetch: refetchCurrentDraft } = useCurrentDraftSummary(
    hasPendingDraft
  )
  const generateMutation = useGenerateSchedule()
  const cancelGenerationMutation = useCancelScheduleTask()
  const approveMutation  = useApproveDraft()
  const rejectMutation   = useRejectDraft()
  const { data: jobData } = useScheduleTaskStatus(activeJobId)

  // Sprint 4 hooks
  const { data: classes  = [] } = useClasses({ enabled: isAdmin })
  const { data: teachers = [] } = useTeachers({ enabled: isAdmin })
  const { data: timeslots = [] } = useTimeslots()

  // Apply URL query params for cross-navigation (Fase 7.4)
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!isAdmin || !urlTeacherId) return
    const teacherExists = teachers.some((t) => String(t.id) === urlTeacherId)
    if (teacherExists) {
      setViewMode('teacher')
      setSelectedTeacherId(urlTeacherId)
      setSelectedClassId('')
    }
  }, [isAdmin, urlTeacherId, teachers])
  /* eslint-enable react-hooks/set-state-in-effect */

  // Persist view state so the user returns to the same class/teacher
  useEffect(() => {
    if (!isAdmin || hasUrlParams) return
    writeStoredView(viewStorageKey, {
      viewMode,
      selectedClassId,
      selectedTeacherId,
      weekStart,
    })
  }, [isAdmin, hasUrlParams, viewStorageKey, viewMode, selectedClassId, selectedTeacherId, weekStart])

  const classId   = viewMode === 'class'   && selectedClassId   ? Number.parseInt(selectedClassId, 10)   : null
  const teacherId = viewMode === 'teacher' && selectedTeacherId ? Number.parseInt(selectedTeacherId, 10) : null

  const {
    data: weekSlots = [],
    isFetching: loadingWeek,
    isError: weekLoadError,
  } = useWeekSchedule(classId, teacherId, weekStart)
  const { data: classDetails } = useClassDetails(classId)

  const classSubjects = classDetails?.subjects ?? []

  // Refresh scheduler state after a durable generation job finishes.
  useEffect(() => {
    const status = jobData?.job_status
    const terminal = ['SUCCEEDED', 'FAILED', 'CANCELED', 'NO_VALID_OUTPUT']
    if (activeJobId && terminal.includes(status)) {
      void refetchSchedulerStatus()
      void refetchCurrentDraft()
      clearStoredJobId(jobStorageKey)
      void queryClient.invalidateQueries({ queryKey: ['weekSchedule'] })
      void queryClient.invalidateQueries({ queryKey: ['schedule'] })
    }
  }, [jobData, activeJobId, refetchSchedulerStatus, refetchCurrentDraft, queryClient, jobStorageKey])

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!isAdmin || activeJobId) {
      return
    }

    const storedJobId = readStoredJobId(jobStorageKey)
    if (storedJobId) {
      setActiveJobId(Number(storedJobId))
    }
  }, [isAdmin, activeJobId, jobStorageKey])
  /* eslint-enable react-hooks/set-state-in-effect */

  useEffect(() => {
    if (!isAdmin) {
      return
    }

    if (activeJobId) {
      writeStoredJobId(jobStorageKey, activeJobId)
    }
  }, [isAdmin, activeJobId, jobStorageKey])

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!isTeacher || !teacherOwnId) {
      return
    }

    setViewMode('teacher')
    setSelectedClassId('')
    setSelectedTeacherId(String(teacherOwnId))
  }, [isTeacher, teacherOwnId])
  /* eslint-enable react-hooks/set-state-in-effect */

  const handleGenerate = async () => {
    setGenerationActionError('')
    setPreflightErrors([])
    setActiveJobId(null)
    try {
      const result = await generateMutation.mutateAsync()
      if (result?.job_id) setActiveJobId(result.job_id)
    } catch (err) {
      const detail = err?.response?.data?.detail
      if (detail?.error === 'pending_draft_replacement_required') {
        const confirmed = window.confirm(
          'Já existe um rascunho pendente. Pretende substituí-lo por uma nova geração?'
        )
        if (confirmed) {
          try {
            const result = await generateMutation.mutateAsync({ replacePendingDraft: true })
            if (result?.job_id) setActiveJobId(result.job_id)
          } catch (replacementError) {
            const replacementDetail = replacementError?.response?.data?.detail
            setGenerationActionError(
              replacementDetail?.message
              || replacementError?.message
              || 'Erro ao iniciar a geração de substituição.'
            )
          }
        }
        return
      }
      const problems = err?.response?.data?.detail?.problems
      if (!Array.isArray(problems) && detail?.message) {
        setGenerationActionError(detail.message)
        return
      }
      if (Array.isArray(problems)) {
        setPreflightErrors(problems)
      } else {
        setGenerationActionError(err?.response?.data?.detail || err?.message || 'Erro ao iniciar a geração. Verifique a ligação e tente novamente.')
      }
    }
  }

  const handleRegenerate = async () => {
    const confirmed = window.confirm(
      'Gerar novamente irá substituir o rascunho pendente apenas quando a nova geração terminar com sucesso. Continuar?'
    )
    if (!confirmed) return
    setGenerationActionError('')
    setPreflightErrors([])
    try {
      const result = await generateMutation.mutateAsync({ replacePendingDraft: true })
      if (result?.job_id) setActiveJobId(result.job_id)
    } catch (err) {
      const detail = err?.response?.data?.detail
      setGenerationActionError(
        detail?.message || err?.message || 'Não foi possível iniciar a nova geração.'
      )
    }
  }

  const handleCancelGeneration = () => {
    if (!activeJobId) {
      return
    }

    setGenerationActionError('')
    cancelGenerationMutation.mutate(activeJobId, {
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: ['scheduler-job', orgId, activeJobId] })
      },
      onError: () => {
        setGenerationActionError('Não foi possível cancelar a geração. Tente novamente.')
      },
    })
  }

  const isGenerating = ['QUEUED', 'RUNNING', 'CANCEL_REQUESTED'].includes(
    jobData?.job_status
  )
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
      <div className="d-flex justify-content-between align-items-center mb-4 flex-wrap gap-3">
        <div>
          <h1 className="h3 mb-1" style={{ color: 'var(--brand-950)' }}>Horários escolares</h1>
        </div>

        {/* Status-driven generation controls */}
        {isAdmin && (
          <div className="d-flex align-items-center gap-2 flex-wrap">
                {!hasPendingDraft && schedulerStatus?.can_generate_new_draft && (
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
                )}
                {hasPendingDraft && schedulerStatus?.can_regenerate_with_confirmation && (
                    <CButton
                      color="secondary"
                      variant="outline"
                      size="sm"
                      disabled={isGenerating || generateMutation.isPending}
                      onClick={() => { void handleRegenerate() }}
                    >
                      <CIcon icon={cilReload} className="me-1" />
                      Gerar novamente
                    </CButton>
                )}
                {activeJobId && isGenerating && (
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
                )}
          </div>
        )}
      </div>

      {isAdmin ? (
        <>
          {preflightErrors.length > 0 && <PreflightErrorPanel problems={preflightErrors} />}
          {generationActionError && (
            <CAlert color="danger" className="mb-4" style={{ whiteSpace: 'pre-line' }}>
              {generationActionError}
            </CAlert>
          )}
          {activeJobId && <GenerationStatusPanel jobId={activeJobId} />}
          {!hasPendingDraft && schedulerStatus?.blocked_reason && !isGenerating && (
            <CAlert color="secondary" className="mb-4" style={{ whiteSpace: 'pre-line' }}>
              {schedulerStatus.blocked_reason}
            </CAlert>
          )}
          {hasPendingDraft && currentDraft && (
            <DraftPanel
              draft={currentDraft}
              onApprove={async (draftId) => {
                try { await approveMutation.mutateAsync(draftId) }
                catch (err) {
                  setGenerationActionError(
                    getDraftMutationErrorMessage(err, 'Erro ao aprovar rascunho.')
                  )
                }
              }}
              onReject={async (draftId) => {
                try { await rejectMutation.mutateAsync(draftId) }
                catch (err) {
                  setGenerationActionError(
                    getDraftMutationErrorMessage(err, 'Erro ao rejeitar rascunho.')
                  )
                }
              }}
              isApproving={approveMutation.isPending}
              isRejecting={rejectMutation.isPending}
            />
          )}
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
                {hasPendingDraft && (
                  <CBadge color="warning" className="ms-2">
                    Rascunho pendente
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
