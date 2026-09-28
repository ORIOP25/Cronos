import { useState, useEffect, useMemo } from 'react'
import { useLocation } from 'react-router-dom'
import {
  CCard, CCardBody, CCardHeader, CAlert, CBadge, CSpinner,
  CButton, CButtonGroup, CFormSelect, CFormLabel, CRow, CCol,
  } from '@coreui/react'
import CIcon from '@coreui/icons-react'
import {
  cilReload, cilBan,
  cilPeople, cilUser,
} from '@coreui/icons'
import {
  useSchedulerStatus, useCurrentDraftSummary, useApproveDraft, useRejectDraft,
  useGenerateSchedule, useScheduleTaskStatus, useCancelScheduleTask,
  useWeekSchedule,
} from '../features/scheduling/data'
import { useClasses, useClassDetails, useTimeslots, useWeekGridVersions } from '../features/catalog/data'
import { useCalendarEvents } from '../features/schoolConfig/data'
import { useTeachers } from '../features/members/data'
import WeekGrid from '../components/WeekGrid'
import WeekNavigator from '../components/WeekNavigator'
import LessonLogModal from '../components/LessonLogModal'
import KPISidebar from '../components/schedules/KPISidebar'
import DraftPanel from '../components/schedules/DraftPanel'
import GenerationStatusPanel from '../components/schedules/GenerationStatusPanel'
import ConfirmationModal from '../components/ConfirmationModal'
import PageHeader from '../components/PageHeader'
import StatePanel from '../components/StatePanel'
import { useOrganization } from '@clerk/react'
import { addDays, getCurrentWeekMonday } from '../utils/formatUtils'
import { collectInternshipDays } from '../utils/internshipDays'
import { getApiErrorMessage } from '../utils/apiErrors'
import { readExpiringValue, writeExpiringValue } from '../utils/expiringStorage'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const ACTIVE_JOB_STORAGE_KEY_PREFIX = 'hz-schedule-active-job-org-'
const VIEW_STORAGE_KEY_PREFIX = 'hz-schedule-view-org-'
const STALE_DRAFT_MESSAGE = (
  'Existem alterações mais recentes.\n\n'
  + 'Esta proposta já não pode ser aprovada. Gere uma nova proposta para continuar.'
)

const ELIGIBILITY_MESSAGES = {
  ACTIVE_JOB: 'Já existe um pedido de geração em curso.',
}

const NO_REASON_MESSAGE = (
  'Não existem alterações por aplicar ao horário. '
  + 'Pode otimizar as próximas semanas quando passarem 28 dias.'
)

function eligibilityMessage(eligibility, schoolYear) {
  if (schoolYear && !schoolYear.preferred_end_date) {
    return 'Defina a data preferencial de fim em Configuração antes de gerar o horário.'
  }
  if (!eligibility || eligibility.can_generate) return ''
  if (eligibility.blocker) {
    return ELIGIBILITY_MESSAGES[eligibility.blocker] || 'A geração não está disponível de momento.'
  }
  return NO_REASON_MESSAGE
}

function getDraftMutationErrorMessage(error, fallback) {
  const detail = error?.response?.data?.detail
  if (detail?.code === 'proposal_stale' || detail?.context?.proposal_status === 'STALE') {
    return STALE_DRAFT_MESSAGE
  }
  return getApiErrorMessage(error, fallback, 'schedule.approve')
}

function getViewStorageKey(orgId) {
  if (!orgId) return null
  return `${VIEW_STORAGE_KEY_PREFIX}${orgId}`
}

function readStoredView(storageKey) {
  if (!storageKey) return null
  try {
    return readExpiringValue(localStorage, storageKey)
  } catch {
    return null
  }
}

function writeStoredView(storageKey, viewState) {
  if (!storageKey) return
  try {
    writeExpiringValue(localStorage, storageKey, viewState)
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
    return readExpiringValue(localStorage, storageKey)
  } catch {
    return null
  }
}

function writeStoredJobId(storageKey, jobId) {
  if (!storageKey || !jobId) return
  try {
    writeExpiringValue(localStorage, storageKey, String(jobId))
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
const Schedules = ({ initialClassId = '', initialWeekStart, persistView = true, readOnly = false, allowedActions, referenceDate }) => {
  const location = useLocation()
  const { organization } = useOrganization()
  const orgId = organization?.id ?? null
  const isTutorial = Array.isArray(allowedActions)
  const canGenerate = !readOnly && (!isTutorial || allowedActions.includes('GENERATE_SCHEDULE'))
  const canApprove = !readOnly && (!isTutorial || allowedActions.includes('APPROVE_SCHEDULE') || allowedActions.includes('APPROVE_RECOVERY'))
  const canReject = !readOnly && !isTutorial
  const jobStorageKey = persistView ? getJobStorageKey(orgId) : null
  const viewStorageKey = getViewStorageKey(orgId)

  // Parse query params for cross-navigation (Fase 7.4)
  const urlParams = new URLSearchParams(location.search)
  const urlTeacherId = urlParams.get('teacherId')
  const urlWeekStart = urlParams.get('weekStart')
  const hasUrlParams = Boolean(urlTeacherId || urlWeekStart)

  // Restore persisted view state (admin only, URL params take priority)
  const storedView = persistView && !hasUrlParams ? readStoredView(viewStorageKey) : null

  // Sprint 3 state
  const [activeJobId, setActiveJobId]         = useState(() => {
    const storedJobId = readStoredJobId(jobStorageKey)
    return storedJobId ? Number(storedJobId) : null
  })

  // Sprint 4 state
  const [viewMode, setViewMode]                   = useState(
    storedView?.viewMode || 'class'
  )
  const [selectedClassId, setSelectedClassId]     = useState(
    String(initialClassId || storedView?.selectedClassId || '')
  )
  const [selectedTeacherId, setSelectedTeacherId] = useState(() => {
    return storedView?.selectedTeacherId || ''
  })
  const [weekStart, setWeekStart]                 = useState(() => {
    if (urlWeekStart && /^\d{4}-\d{2}-\d{2}$/.test(urlWeekStart)) {
      return urlWeekStart
    }
    return initialWeekStart || storedView?.weekStart || getCurrentWeekMonday()
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
  const hasPendingDraft = Boolean(schedulerStatus?.pending_proposal)
  const { data: currentDraft, refetch: refetchCurrentDraft } = useCurrentDraftSummary(
    hasPendingDraft
  )
  const generateMutation = useGenerateSchedule()
  const cancelGenerationMutation = useCancelScheduleTask()
  const approveMutation  = useApproveDraft()
  const rejectMutation   = useRejectDraft()
  const serverJobId = schedulerStatus?.active_job?.id ?? null
  const effectiveJobId = activeJobId ?? serverJobId
  const { data: jobData } = useScheduleTaskStatus(effectiveJobId)
  const eligibility = schedulerStatus?.eligibility
  const schoolYear = schedulerStatus?.school_year
  const canGenerateNow = Boolean(eligibility?.can_generate && schoolYear?.preferred_end_date)
  const isFirstGeneration = schedulerStatus?.publication_state !== 'PUBLISHED'

  // Sprint 4 hooks
  const { data: classes  = [] } = useClasses()
  const { data: teachers = [] } = useTeachers()
  const { data: timeslots = [] } = useTimeslots()
  const { data: weekGridVersions } = useWeekGridVersions(weekStart)

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
    if (hasUrlParams || !persistView) return
    writeStoredView(viewStorageKey, {
      viewMode,
      selectedClassId,
      selectedTeacherId,
      weekStart,
    })
  }, [hasUrlParams, persistView, viewStorageKey, viewMode, selectedClassId, selectedTeacherId, weekStart])

  const classId   = viewMode === 'class'   && selectedClassId   ? Number.parseInt(selectedClassId, 10)   : null
  const teacherId = viewMode === 'teacher' && selectedTeacherId ? Number.parseInt(selectedTeacherId, 10) : null
  const weekEnd = addDays(weekStart, 6)

  const { data: calendarEvents = [] } = useCalendarEvents()
  const internshipDays = useMemo(
    () => collectInternshipDays(calendarEvents, classId, weekStart, weekEnd),
    [calendarEvents, classId, weekStart, weekEnd],
  )

  const {
    data: weekSlots = [],
    isFetching: loadingWeek,
    isError: weekLoadError,
    refetch: refetchWeekSchedule,
  } = useWeekSchedule(classId, teacherId, weekStart)
  const {
    data: classDetails,
    isLoading: loadingClassDetails,
    isError: classDetailsError,
  } = useClassDetails(classId)

  const classSubjects = classDetails?.subjects ?? []

  // Refresh scheduler state after a durable generation job finishes.
  useEffect(() => {
    const status = jobData?.status
    const terminal = ['SUCCEEDED', 'FAILED', 'CANCELLED', 'STALE', 'INFEASIBLE', 'INCONCLUSIVE']
    if (effectiveJobId && terminal.includes(status)) {
      void refetchSchedulerStatus()
      void refetchCurrentDraft()
      clearStoredJobId(jobStorageKey)
      if (classId || teacherId) void refetchWeekSchedule()
    }
  }, [
    jobData,
    effectiveJobId,
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

  const runGeneration = async () => {
    if (!canGenerate || !canGenerateNow) return
    setGenerationConfirmation(null)
    setGenerationActionError('')
    try {
      const result = await generateMutation.mutateAsync({
        idempotencyKey: globalThis.crypto.randomUUID(),
        expectedInputRevision: schedulerStatus?.revisions?.input ?? 0,
      })
      const jobId = result?.job?.id
      if (jobId) setActiveJobId(jobId)
    } catch (err) {
      const detail = err?.response?.data?.detail
      if (detail?.code === 'active_job' && detail?.context?.job_id) {
        setActiveJobId(detail.context.job_id)
        return
      }
      if (detail?.code === 'scheduler_state_changed') {
        void refetchSchedulerStatus()
      }
      setGenerationActionError(
        getApiErrorMessage(err, 'Não foi possível iniciar a geração.', 'schedule.generate')
      )
    }
  }

  const handleGenerate = () => {
    if (!canGenerate) return
    if (hasPendingDraft) {
      setGenerationConfirmation('regenerate')
      return
    }
    void runGeneration()
  }

  const handleCancelGeneration = () => {
    if (!effectiveJobId) {
      return
    }

    setGenerationActionError('')
    cancelGenerationMutation.mutate(effectiveJobId, {
      onError: () => {
        setGenerationActionError('Não foi possível cancelar a geração. Tente novamente.')
      },
    })
    setActiveJobId(null)
  }

  const isGenerating = ['QUEUED', 'RUNNING', 'VALIDATING'].includes(jobData?.status)
  const hasSelection = Boolean(classId || teacherId)

  const openCreateOccurrenceModal = (slot) => {
    setAdminLessonLogSlot(slot)
  }

  let weekGridContent = <StatePanel state="empty" title="Escolha uma seleção" description="Selecione uma turma ou professor para visualizar o horário da semana." />

  if (hasSelection) {
    weekGridContent = (
      <WeekGrid
        slots={weekSlots}
        isLoading={loadingWeek}
        baseTimeslots={timeslots}
        weekStart={weekStart}
        dayGrids={weekGridVersions?.days ?? null}
        gridTransitionDate={weekGridVersions?.transition_date ?? ''}
        isOperationalEnabled
        onOpenOperationalAction={openCreateOccurrenceModal}
        internshipDays={internshipDays}
        fitViewport
      />
    )
  }

  if (hasSelection && weekLoadError) {
    weekGridContent = <StatePanel state="error" title="Não foi possível carregar o horário" description="Tente novamente quando a ligação estiver disponível." action={<button type="button" className="btn btn-outline-primary" onClick={() => refetchWeekSchedule()}>Tentar novamente</button>} />
  }

  return (
    <div className="p-4 schedules-page">

      {adminLessonLogSlot ? (
        <LessonLogModal
          key={adminLessonLogSlot.operational_block_id ?? adminLessonLogSlot.id}
          onClose={() => setAdminLessonLogSlot(null)}
          slot={adminLessonLogSlot}
          isAdmin
          readOnly={readOnly}
          allowedActions={allowedActions}
          referenceDate={referenceDate}
        />
      ) : null}

      <ConfirmationModal
        visible={Boolean(generationConfirmation)}
        onClose={() => setGenerationConfirmation(null)}
        onConfirm={() => { void runGeneration() }}
        title="Confirmar nova geração"
        message="Gerar novamente irá substituir a proposta pendente apenas quando a nova geração terminar com sucesso. Continuar?"
        confirmText="Confirmar geração"
        isLoading={generateMutation.isPending}
        variant="warning"
      />

      <PageHeader
        preTitle="Operações"
        title="Horários Escolares"
      >
        {/* Status-driven generation controls */}
        <div className="d-flex align-items-center gap-2 flex-wrap">
                {canGenerateNow && !isGenerating && canGenerate && (
                  <CButton
                    color="primary" size="sm"
                    disabled={generateMutation.isPending}
                    onClick={handleGenerate}
                    data-tutorial-target={isFirstGeneration ? 'generate-schedule' : 'regenerate-schedule'}
                  >
                    <CIcon icon={cilReload} className="me-1" />
                    {isFirstGeneration ? 'Gerar horário' : 'Atualizar horário'}
                  </CButton>
                )}
                {effectiveJobId && isGenerating && canGenerate && (
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
      </PageHeader>

      <div data-tutorial-target="schedule-draft">
          {generationActionError && (
            <CAlert color="danger" className="mb-4" style={{ whiteSpace: 'pre-line' }}>
              {generationActionError}
            </CAlert>
          )}
          {effectiveJobId && <GenerationStatusPanel jobId={effectiveJobId} />}
          {!hasPendingDraft && !isGenerating && eligibilityMessage(eligibility, schoolYear) && (
            <CAlert color="secondary" className="mb-4" style={{ whiteSpace: 'pre-line' }}>
              {eligibilityMessage(eligibility, schoolYear)}
            </CAlert>
          )}
          {hasPendingDraft && (currentDraft || schedulerStatus?.pending_proposal) && (
            <DraftPanel
              draft={currentDraft || schedulerStatus.pending_proposal}
              onApprove={async (proposalId) => {
                try {
                  await approveMutation.mutateAsync({
                    proposalId,
                    expectedInputRevision: schedulerStatus?.revisions?.input ?? null,
                  })
                }
                catch (err) {
                  setGenerationActionError(
                    getDraftMutationErrorMessage(err, 'Erro ao aprovar proposta.')
                  )
                }
              }}
              onReject={async (proposalId) => {
                try { await rejectMutation.mutateAsync(proposalId) }
                catch (err) {
                  setGenerationActionError(
                    getDraftMutationErrorMessage(err, 'Erro ao rejeitar proposta.')
                  )
                }
              }}
              isApproving={approveMutation.isPending}
              isRejecting={rejectMutation.isPending}
              allowApprove={canApprove}
              allowReject={canReject}
            />
          )}
      </div>

      {/* ── Sprint 4: View controls ── */}
      <CCard className="border-0 shadow-sm mb-3 schedule-controls">
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

      <CCard className="border-0 shadow-sm mb-4 schedule-grid-card" data-tutorial-target="schedule-grid">
        <CCardHeader className="bg-transparent fw-semibold d-flex align-items-center justify-content-between py-2">
          <span>
            Grelha semanal
            {hasPendingDraft && <CBadge color="warning" className="ms-2">Proposta pendente</CBadge>}
          </span>
          {loadingWeek && <CSpinner size="sm" className="text-secondary" />}
        </CCardHeader>
        <CCardBody className="p-0">{weekGridContent}</CCardBody>
      </CCard>

      {viewMode === 'class' && Boolean(classId) && (
        <CCard className="border-0 shadow-sm">
          <CCardHeader className="bg-transparent fw-semibold">Progresso por disciplina</CCardHeader>
          <CCardBody>
            <KPISidebar
              subjects={classSubjects}
              isLoading={loadingClassDetails}
              isError={classDetailsError}
            />
          </CCardBody>
        </CCard>
      )}
    </div>
  )
}

export default Schedules
