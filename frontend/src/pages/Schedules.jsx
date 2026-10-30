import { useState, useEffect, useMemo } from 'react'
import { toast } from 'react-hot-toast'
import { Link, useLocation } from 'react-router-dom'
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
import { usePrevalidation } from '../features/readiness/data'
import { useClasses, useClassDetails, useTimeslots, useWeekGridVersions } from '../features/catalog/data'
import { useCalendarEvents } from '../features/schoolConfig/data'
import { useTeachers } from '../features/members/data'
import WeekGrid from '../components/WeekGrid'
import WeekNavigator from '../components/WeekNavigator'
import LessonLogModal from '../components/LessonLogModal'
import KPISidebar from '../components/schedules/KPISidebar'
import DraftPanel from '../components/schedules/DraftPanel'
import GenerationStatusPanel from '../components/schedules/GenerationStatusPanel'
import ProposalPreviewToggle from '../components/schedules/ProposalPreviewToggle'
import ConfirmationModal from '../components/ConfirmationModal'
import FailureState from '../components/FailureState'
import FeedbackBanner from '../components/FeedbackBanner'
import PageHeader from '../components/PageHeader'
import StatePanel from '../components/StatePanel'
import { useOrganization } from '@clerk/react'
import { addDays, formatDate, getCurrentWeekMonday } from '../utils/formatUtils'
import { collectInternshipDays } from '../utils/internshipDays'
import { getApiErrorMessage, getApiErrorPresentation } from '../utils/apiErrors'
import { useAttemptScope } from '../hooks/useAttemptScope'
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

function eligibilityMessage(eligibility, schoolYear) {
  if (schoolYear && !schoolYear.preferred_end_date) {
    return 'Defina a data preferencial de fim em Configuração antes de gerar o horário.'
  }
  if (!eligibility || eligibility.can_generate) return ''
  if (eligibility.blocker) {
    return ELIGIBILITY_MESSAGES[eligibility.blocker] || 'A geração não está disponível de momento.'
  }
  return ''
}

function isPreviewableProposal(proposal) {
  return Boolean(proposal) && !proposal.is_stale && proposal.status !== 'STALE'
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
  const [generationActionError, setGenerationActionError] = useState(null)
  const [generationConfirmation, setGenerationConfirmation] = useState(null)
  const [previewedProposalId, setPreviewedProposalId] = useState(null)

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
  const attemptScope = useAttemptScope()
  const serverJobId = schedulerStatus?.active_job?.id ?? null
  const effectiveJobId = activeJobId ?? serverJobId
  const { data: jobData } = useScheduleTaskStatus(effectiveJobId)
  const eligibility = schedulerStatus?.eligibility
  const schoolYear = schedulerStatus?.school_year
  const canGenerateNow = Boolean(eligibility?.can_generate && schoolYear?.preferred_end_date)
  const isFirstGeneration = schedulerStatus?.publication_state !== 'PUBLISHED'
  const pendingProposal = schedulerStatus?.pending_proposal
  // The tutorial adapter has no proposal lessons to preview.
  const previewableProposalId = canGenerate && !isTutorial && isPreviewableProposal(pendingProposal)
    ? pendingProposal.proposal_id
    : null
  const showingProposal = previewableProposalId != null && previewedProposalId === previewableProposalId

  // Validate the same operation that the generator will run.
  const {
    data: prevalidation,
    isFetching: prevalidationLoading,
    isError: prevalidationError,
    refetch: refetchPrevalidation,
  } = usePrevalidation({
    enabled: canGenerate && Boolean(schedulerStatus),
    strategy: schedulerStatus?.default_strategy === 'ADAPTIVE_RECOVERY' ? 'ADAPTIVE_REPAIR' : 'COMPLETE_GENERATION',
  })
  const prevalidationIssues = Array.isArray(prevalidation?.issues) ? prevalidation.issues : []
  const prevalidationBlocked = prevalidation?.status === 'BLOCKED'
  const prevalidationNotReady = prevalidationLoading || prevalidationBlocked || prevalidationError

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

  // Drop a persisted class that no longer belongs to the current organization.
  useEffect(() => {
    if (!selectedClassId || classes.length === 0) return
    if (!classes.some((row) => String(row.id) === String(selectedClassId))) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelectedClassId('')
    }
  }, [classes, selectedClassId])

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
    error: weekLoadError,
    refetch: refetchWeekSchedule,
  } = useWeekSchedule(classId, teacherId, weekStart, showingProposal ? previewableProposalId : null)
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
      if (jobData?.result_code === 'INVALID_INPUT') {
        void refetchPrevalidation()
      }
    }
  }, [
    jobData,
    effectiveJobId,
    classId,
    teacherId,
    refetchSchedulerStatus,
    refetchCurrentDraft,
    refetchPrevalidation,
    refetchWeekSchedule,
    jobStorageKey,
  ])

  useEffect(() => {
    if (activeJobId) {
      writeStoredJobId(jobStorageKey, activeJobId)
    }
  }, [activeJobId, jobStorageKey])

  // A stale generation error must not follow the user into another organization.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setGenerationActionError(null)
  }, [orgId])

  const runGeneration = async () => {
    if (!canGenerate || !canGenerateNow) return
    setGenerationConfirmation(null)
    setGenerationActionError(null)
    const attempt = attemptScope.capture()
    try {
      const result = await generateMutation.mutateAsync({
        idempotencyKey: globalThis.crypto.randomUUID(),
        expectedInputRevision: schedulerStatus?.revisions?.input ?? 0,
      })
      if (!attemptScope.isCurrent(attempt)) return
      const jobId = result?.job?.id
      if (jobId) {
        setActiveJobId(jobId)
        toast.success('Geração pedida. Acompanhe o progresso nesta página.')
      }
    } catch (err) {
      if (!attemptScope.isCurrent(attempt)) return
      const detail = err?.response?.data?.detail
      if (detail?.code === 'active_job' && detail?.context?.job_id) {
        setActiveJobId(detail.context.job_id)
        return
      }
      if (['scheduler_state_changed', 'NO_ELIGIBLE_ROOM', 'TEACHER_PRESENCE_IMPOSSIBLE'].includes(detail?.code)) {
        void refetchSchedulerStatus()
        void refetchPrevalidation()
      }
      setGenerationActionError(getApiErrorPresentation(err, 'schedule.generate'))
    }
  }

  const handleGenerate = () => {
    if (!canGenerate) return
    setGenerationConfirmation(hasPendingDraft ? 'regenerate' : 'generate')
  }

  const generationConfirmationMessage = () => {
    const preferredEnd = schedulerStatus?.school_year?.preferred_end_date
    const yearLabel = preferredEnd
      ? `Ano letivo com fim previsto em ${formatDate(preferredEnd)}. `
      : ''
    const versionLabel = schedulerStatus?.active_version_id
      ? 'Já existe um horário publicado. '
      : 'Ainda não existe horário publicado. '
    const effect = hasPendingDraft
      ? 'A proposta pendente é substituída apenas quando a nova geração terminar com sucesso.'
      : isFirstGeneration
        ? 'Cria a primeira versão publicada do horário.'
        : 'Cria uma nova versão do horário; a versão atual mantém-se no histórico.'
    return `Âmbito: toda a escola. ${yearLabel}${versionLabel}${effect}`
  }

  const handleCancelGeneration = () => {
    if (!effectiveJobId) {
      return
    }

    cancelGenerationMutation.mutate(effectiveJobId, attemptScope.guard({
      onError: () => {
        toast.error('Não foi possível cancelar a geração. Tente novamente.')
      },
    }))
  }

  const isGenerating = ['QUEUED', 'RUNNING', 'VALIDATING'].includes(jobData?.status)
  const isCancelling = cancelGenerationMutation.isPending || Boolean(jobData?.cancellation_requested)
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
        isOperationalEnabled={!showingProposal}
        onOpenOperationalAction={showingProposal ? undefined : openCreateOccurrenceModal}
        internshipDays={internshipDays}
        fitViewport
      />
    )
  }

  if (hasSelection && weekLoadError) {
    weekGridContent = (
      <FailureState
        variant="inline"
        presentation={{
          ...getApiErrorPresentation(weekLoadError, 'schedule.week'),
          title: 'Não foi possível carregar o horário',
          message: 'A seleção mantém-se. Verifique a ligação e tente novamente.',
        }}
        onRetry={() => refetchWeekSchedule()}
      />
    )
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
        title={generationConfirmation === 'regenerate' ? 'Confirmar nova geração' : 'Confirmar geração'}
        message={generationConfirmationMessage()}
        confirmText="Iniciar geração"
        pendingText="A iniciar…"
        isLoading={generateMutation.isPending}
        variant="warning"
      />

      <PageHeader
        title="Horários Escolares"
      >
        {/* Status-driven generation controls */}
        <div className="d-flex align-items-center gap-2 flex-wrap">
                {canGenerateNow && !isGenerating && canGenerate && (
                  <CButton
                    color="primary" size="sm"
                    disabled={generateMutation.isPending || prevalidationNotReady}
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
                      disabled={isCancelling}
                      onClick={handleCancelGeneration}
                    >
                      {isCancelling
                        ? <><CSpinner size="sm" className="me-1" />A cancelar…</>
                        : <><CIcon icon={cilBan} className="me-1" />Cancelar geração</>
                      }
                    </CButton>
                )}
        </div>
      </PageHeader>

      <div data-tutorial-target="schedule-draft">
          {typeof generationActionError === 'string' && (
            <div className="mb-4">
              <FeedbackBanner tone="danger">{generationActionError}</FeedbackBanner>
            </div>
          )}
          {generationActionError && typeof generationActionError === 'object' && (
            <div className="mb-4">
              <FailureState
                variant="inline"
                presentation={generationActionError}
                navigationTo={generationActionError.code === 'NO_ELIGIBLE_ROOM' ? '/rooms' : generationActionError.code === 'TEACHER_PRESENCE_IMPOSSIBLE' ? '/members' : undefined}
                navigationLabel={generationActionError.code === 'TEACHER_PRESENCE_IMPOSSIBLE' ? 'Abrir Equipa' : 'Abrir Salas'}
              />
            </div>
          )}
          {prevalidationIssues.length > 0 && (
            <CAlert color={prevalidationBlocked ? 'danger' : 'warning'} className="mb-4">
              <strong>
                {prevalidationBlocked
                  ? 'Geração bloqueada antes de começar'
                  : 'Avisos antes de gerar'}
              </strong>
              <ul className="mb-0 mt-1 ps-3">
                {prevalidationIssues.map((issue, index) => (
                  <li key={`${issue.code}-${index}`}>
                    <Link to={issue.route}>{issue.message}</Link>
                  </li>
                ))}
              </ul>
            </CAlert>
          )}
          {prevalidationError && (
            <div className="mb-4">
              <FailureState
                variant="inline"
                presentation={{
                  title: 'Não foi possível verificar a preparação',
                  message: 'Não foi possível confirmar se a escola está pronta para gerar. Repita a verificação.',
                }}
                onRetry={() => void refetchPrevalidation()}
                retryLabel="Repetir verificação"
              />
            </div>
          )}
          {effectiveJobId && <GenerationStatusPanel jobId={effectiveJobId} />}
          {!hasPendingDraft && !isGenerating && eligibilityMessage(eligibility, schoolYear) && (
            <div className="mb-4">
              <FeedbackBanner tone="info">
                {eligibilityMessage(eligibility, schoolYear)}
              </FeedbackBanner>
            </div>
          )}
          {hasPendingDraft && (currentDraft || schedulerStatus?.pending_proposal) && (
            <DraftPanel
              draft={currentDraft || schedulerStatus.pending_proposal}
              onApprove={async (proposalId) => {
                const attempt = attemptScope.capture()
                try {
                  await approveMutation.mutateAsync({
                    proposalId,
                    expectedInputRevision: schedulerStatus?.revisions?.input ?? null,
                  })
                  if (!attemptScope.isCurrent(attempt)) return
                  toast.success('Proposta aprovada.')
                }
                catch (err) {
                  if (!attemptScope.isCurrent(attempt)) return
                  const message = getDraftMutationErrorMessage(err, 'Não foi possível aprovar proposta.')
                  if (message === STALE_DRAFT_MESSAGE) setGenerationActionError(message)
                  else toast.error(message)
                }
              }}
              onReject={async (proposalId) => {
                const attempt = attemptScope.capture()
                try {
                  await rejectMutation.mutateAsync(proposalId)
                  if (!attemptScope.isCurrent(attempt)) return
                  toast.success('Proposta rejeitada.')
                }
                catch (err) {
                  if (!attemptScope.isCurrent(attempt)) return
                  const message = getDraftMutationErrorMessage(err, 'Não foi possível rejeitar proposta.')
                  if (message === STALE_DRAFT_MESSAGE) setGenerationActionError(message)
                  else toast.error(message)
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
        <CCardBody className="p-0">
          {previewableProposalId != null && (
            <ProposalPreviewToggle
              showingProposal={showingProposal}
              onChange={(show) => setPreviewedProposalId(show ? previewableProposalId : null)}
            />
          )}
          {weekGridContent}
        </CCardBody>
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
