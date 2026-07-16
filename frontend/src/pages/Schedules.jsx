import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import {
  CCard, CCardBody, CCardHeader, CAlert, CBadge, CSpinner,
  CButton, CButtonGroup, CFormSelect, CFormLabel, CRow, CCol,
  } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import {
  cilCalendar, cilReload, cilBan,
  cilPeople, cilUser,
} from '@coreui/icons'
import {
  useSchedulerStatus, useCurrentDraftSummary, useApproveDraft, useRejectDraft,
  useGenerateSchedule, useScheduleTaskStatus, useCancelScheduleTask,
  useWeekSchedule,
} from '../features/scheduling/data'
import { useClasses, useClassDetails, useTimeslots } from '../features/catalog/data'
import { useTeachers } from '../features/members/data'
import WeekGrid from '../components/WeekGrid'
import WeekNavigator from '../components/WeekNavigator'
import LessonLogModal from '../components/LessonLogModal'
import KPISidebar from '../components/schedules/KPISidebar'
import DraftPanel from '../components/schedules/DraftPanel'
import GenerationStatusPanel from '../components/schedules/GenerationStatusPanel'
import PreflightErrorPanel from '../components/schedules/PreflightErrorPanel'
import ConfirmationModal from '../components/ConfirmationModal'
import { useOrganization } from '@clerk/react'
import { getCurrentWeekMonday } from '../utils/formatUtils'
import { getApiErrorMessage } from '../utils/apiErrors'

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
  const { organization } = useOrganization()
  const orgId = organization?.id ?? null
  const jobStorageKey = getJobStorageKey(orgId)
  const viewStorageKey = getViewStorageKey(orgId)

  // Parse query params for cross-navigation (Fase 7.4)
  const urlParams = new URLSearchParams(location.search)
  const urlTeacherId = urlParams.get('teacherId')
  const urlWeekStart = urlParams.get('weekStart')
  const hasUrlParams = Boolean(urlTeacherId || urlWeekStart)

  // Restore persisted view state (admin only, URL params take priority)
  const storedView = !hasUrlParams ? readStoredView(viewStorageKey) : null

  // Sprint 3 state
  const [activeJobId, setActiveJobId]         = useState(() => {
    const storedJobId = readStoredJobId(jobStorageKey)
    return storedJobId ? Number(storedJobId) : null
  })
  const [preflightErrors, setPreflightErrors] = useState([])

  // Sprint 4 state
  const [viewMode, setViewMode]                   = useState(
    storedView?.viewMode || 'class'
  )
  const [selectedClassId, setSelectedClassId]     = useState(
    storedView?.selectedClassId || ''
  )
  const [selectedTeacherId, setSelectedTeacherId] = useState(() => {
    return storedView?.selectedTeacherId || ''
  })
  const [weekStart, setWeekStart]                 = useState(() => {
    if (urlWeekStart && /^\d{4}-\d{2}-\d{2}$/.test(urlWeekStart)) {
      return urlWeekStart
    }
    return storedView?.weekStart || getCurrentWeekMonday()
  })
  // Bug #4: Keep weekStart in sync with URL query param changes (cross-navigation)
  useEffect(() => {
    if (urlWeekStart && /^\d{4}-\d{2}-\d{2}$/.test(urlWeekStart) && urlWeekStart !== weekStart) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setWeekStart(urlWeekStart)
    }
  }, [urlWeekStart, weekStart])
  const [adminLessonLogSlot, setAdminLessonLogSlot] = useState(null)
  const [generationActionError, setGenerationActionError] = useState('')
  const [generationConfirmation, setGenerationConfirmation] = useState(null)

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
  const { data: classes  = [] } = useClasses()
  const { data: teachers = [] } = useTeachers()
  const { data: timeslots = [] } = useTimeslots()

  // Apply URL query params for cross-navigation (Fase 7.4)
  useEffect(() => {
    if (!urlTeacherId) return
    const teacherExists = teachers.some((t) => String(t.id) === urlTeacherId)
    if (teacherExists) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setViewMode('teacher')
      setSelectedTeacherId(urlTeacherId)
      setSelectedClassId('')
    }
  }, [urlTeacherId, teachers])

  // Persist view state so the user returns to the same class/teacher
  useEffect(() => {
    if (hasUrlParams) return
    writeStoredView(viewStorageKey, {
      viewMode,
      selectedClassId,
      selectedTeacherId,
      weekStart,
    })
  }, [hasUrlParams, viewStorageKey, viewMode, selectedClassId, selectedTeacherId, weekStart])

  const classId   = viewMode === 'class'   && selectedClassId   ? Number.parseInt(selectedClassId, 10)   : null
  const teacherId = viewMode === 'teacher' && selectedTeacherId ? Number.parseInt(selectedTeacherId, 10) : null

  const {
    data: weekSlots = [],
    isFetching: loadingWeek,
    isError: weekLoadError,
    refetch: refetchWeekSchedule,
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
      if (classId || teacherId) void refetchWeekSchedule()
    }
  }, [
    jobData,
    activeJobId,
    classId,
    teacherId,
    refetchSchedulerStatus,
    refetchCurrentDraft,
    refetchWeekSchedule,
    jobStorageKey,
  ])

  useEffect(() => {
    if (activeJobId) {
      writeStoredJobId(jobStorageKey, activeJobId)
    }
  }, [activeJobId, jobStorageKey])

  const startReplacementGeneration = async () => {
    setGenerationConfirmation(null)
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
        setGenerationConfirmation('replace-pending-draft')
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
        setGenerationActionError(getApiErrorMessage(err, 'Erro ao iniciar a geração. Verifique a ligação e tente novamente.'))
      }
    }
  }

  const handleRegenerate = () => {
    setGenerationConfirmation('regenerate')
  }

  const handleCancelGeneration = () => {
    if (!activeJobId) {
      return
    }

    setGenerationActionError('')
    cancelGenerationMutation.mutate(activeJobId, {
      onError: () => {
        setGenerationActionError('Não foi possível cancelar a geração. Tente novamente.')
      },
    })
  }

  const isGenerating = ['QUEUED', 'RUNNING', 'CANCEL_REQUESTED'].includes(
    jobData?.job_status
  )
  const hasSelection = Boolean(classId || teacherId)
  const showKPI      = viewMode === 'class' && Boolean(classId)
  const gridCols     = showKPI ? 8 : 12

  const openCreateOccurrenceModal = (slot) => {
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
        isOperationalEnabled
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

  return (
    <div className="p-4">

      {adminLessonLogSlot ? (
        <LessonLogModal
          key={adminLessonLogSlot.operational_block_id ?? adminLessonLogSlot.id}
          onClose={() => setAdminLessonLogSlot(null)}
          slot={adminLessonLogSlot}
          isAdmin
        />
      ) : null}

      <ConfirmationModal
        visible={Boolean(generationConfirmation)}
        onClose={() => setGenerationConfirmation(null)}
        onConfirm={() => { void startReplacementGeneration() }}
        title="Confirmar nova geração"
        message={
          generationConfirmation === 'replace-pending-draft'
            ? 'Já existe um rascunho pendente. Pretende substituí-lo por uma nova geração?'
            : 'Gerar novamente irá substituir o rascunho pendente apenas quando a nova geração terminar com sucesso. Continuar?'
        }
        confirmText="Confirmar geração"
        isLoading={generateMutation.isPending}
        variant="warning"
      />

      {/* ── Page header ── */}
      <div className="d-flex justify-content-between align-items-center mb-4 flex-wrap gap-3">
        <div>
          <h1 className="h3 mb-1" style={{ color: 'var(--brand-950)' }}>Horários escolares</h1>
        </div>

        {/* Status-driven generation controls */}
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
      </div>

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
              <WeekNavigator value={weekStart} onChange={setWeekStart} />
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
