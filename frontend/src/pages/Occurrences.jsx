import React, { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'react-hot-toast'
import PageHeader from '../components/PageHeader'
import { useSearchParams } from 'react-router-dom'
import { Link } from 'react-router-dom'
import {
  CCard, CCardBody, CCol, CRow, CBadge, CSpinner,
  CButton, CFormSelect, CFormLabel, CTabs, CTabList, CTab,
  CTable, CTableHead, CTableRow, CTableHeaderCell,
  CTableBody, CTableDataCell, CModal, CModalHeader, CModalTitle,
  CModalBody, CModalFooter, CButtonGroup, CFormCheck,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilWarning, cilCheckCircle, cilBan, cilClock } from '@coreui/icons'
import {
  useOccurrences, useDebts, useUpdateOccurrence, useCancelOccurrence,
  useSubstituteRecommendations, useSubstituteDiagnostics,
} from '../features/operations/data'
import { useClasses, useSubjects } from '../features/catalog/data'
import { useTeachers } from '../features/members/data'
import { formatDate, formatDateTime, formatDurationHours, isAfterDate } from '../utils/formatUtils'
import { TXT, OPERATIONAL_STATE_LABELS, OPERATIONAL_STATE_COLORS } from '../utils/terminology'
import ConfirmationModal from '../components/ConfirmationModal'
import FeedbackBanner from '../components/FeedbackBanner'
import PortugueseDateInput from '../components/PortugueseDateInput'
import { getApiErrorMessage, isApiErrorTransient } from '../utils/apiErrors'
import { useAttemptScope } from '../hooks/useAttemptScope'

const HISTORY_TABLE_MEDIA_QUERY = '(min-width: 1000px)'

const useWideHistoryLayout = () => {
  const [isWide, setIsWide] = useState(() => (
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia(HISTORY_TABLE_MEDIA_QUERY).matches
      : true
  ))

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return undefined
    const mediaQuery = window.matchMedia(HISTORY_TABLE_MEDIA_QUERY)
    const handleChange = (event) => setIsWide(event.matches)
    mediaQuery.addEventListener('change', handleChange)
    return () => mediaQuery.removeEventListener('change', handleChange)
  }, [])

  return isWide
}

// ---------------------------------------------------------------------------
// Constantes
// ---------------------------------------------------------------------------
const EMPTY_ARRAY = []
const VALID_TABS = new Set(['occurrences', 'historical', 'debts'])

const OPERATIONAL_STATE_ICONS = {
  OPEN_PENDING: cilClock,
  DECIDED_GIVEN: cilCheckCircle,
  DECIDED_GAP: cilBan,
  DECIDED_SUBSTITUTED: cilWarning,
  REVOKED: cilClock,
}

const resolveOccurrenceStartTime = (occurrence) => {
  if (typeof occurrence?.timeslot_start_time === 'string') {
    return occurrence.timeslot_start_time
  }
  return '99:99'
}

const compareOccurrences = (left, right) => {
  const leftDate = left?.date ?? ''
  const rightDate = right?.date ?? ''
  const dateComparison = leftDate.localeCompare(rightDate)
  if (dateComparison !== 0) {
    return dateComparison
  }

  const leftStart = resolveOccurrenceStartTime(left)
  const rightStart = resolveOccurrenceStartTime(right)
  const startComparison = leftStart.localeCompare(rightStart)
  if (startComparison !== 0) {
    return startComparison
  }

  const leftId = Number(left?.id ?? 0)
  const rightId = Number(right?.id ?? 0)
  return leftId - rightId
}

const buildUpdateErrorMessage = (error) => {
  const status = error?.response?.status
  const suffix = status === 409 ? ' Atualize os dados e tente novamente.' : ''
  return `${getApiErrorMessage(error, TXT.ERROR_SAVING)}${suffix}`
}

const resolveName = (byIdMap, id, fallbackPrefix) => {
  if (!id) return '—'
  const mappedName = byIdMap.get(id)
  if (mappedName) return mappedName
  return `${fallbackPrefix} por identificar`
}

const buildExecutionSummary = (occurrence, teacherById, subjectById) => {
  if (occurrence.status === 'GAP') {
    return 'Aula não realizada'
  }

  if (occurrence.status === 'SUBSTITUTED') {
    const teacherName = occurrence.executed_teacher_name
      ?? resolveName(teacherById, occurrence.substitute_teacher_id, 'Prof.')
    const subjectName = occurrence.substitute_subject_name
      ?? resolveName(subjectById, occurrence.substitute_subject_id, 'Disciplina')
    const execution = occurrence.substitute_execution_status === 'COMPLETED'
      ? 'Concluída'
      : 'Planeada'
    return `${teacherName} (${subjectName}) — ${execution}`
  }

  const effectiveTeacherId = occurrence.executed_teacher_id ?? occurrence.planned_teacher_id
  return occurrence.executed_teacher_name
    ?? resolveName(teacherById, effectiveTeacherId, 'Prof.')
}

const buildDeciderDisplayName = (occurrence) => {
  if (occurrence.decided_by_membership_name) {
    return occurrence.decided_by_membership_name
  }
  if (occurrence.decided_by_membership_id) {
    return 'Administração'
  }
  return 'Administração'
}

const buildDecisionSummary = (occurrence) => {
  if (!occurrence.decided_at) {
    if (occurrence.status === 'GIVEN') return 'Crédito histórico sem decisão. Confirme o registo antes de o reverter.'
    return TXT.OCCURRENCE_PENDING_DECISION
  }

  return `Decidida em ${formatDateTime(occurrence.decided_at)} por ${buildDeciderDisplayName(occurrence)}`
}

const getOperationalState = (occurrence) => {
  if (occurrence.operational_state) {
    return occurrence.operational_state
  }
  if (occurrence.status === 'REVOKED') {
    return 'REVOKED'
  }
  if (!occurrence.decided_at) {
    return 'OPEN_PENDING'
  }
  // Fallback: derive from status
  const statusMap = {
    GIVEN: 'DECIDED_GIVEN',
    GAP: 'DECIDED_GAP',
    SUBSTITUTED: 'DECIDED_SUBSTITUTED',
  }
  return statusMap[occurrence.status] ?? 'OPEN_PENDING'
}

// ---------------------------------------------------------------------------
// Modal de edição de ocorrência
// ---------------------------------------------------------------------------
const EditOccurrenceModal = ({
  occurrence,
  onClose,
  onSave,
  onRevert,
  isSaving,
  teacherById,
  subjectById,
  errorMessage,
  allowedDecisions,
}) => {
  const [decisionTime] = useState(Date.now)
  const lessonNotFinished = occurrence.ends_at && Date.parse(occurrence.ends_at) > decisionTime
  const availableDecisions = (allowedDecisions ?? ['GIVEN', 'GAP', 'SUBSTITUTED'])
    .filter((decision) => decision !== 'GIVEN' || !lessonNotFinished)
  const [status, setStatus] = useState(
    availableDecisions.includes(occurrence.status) ? occurrence.status : availableDecisions[0] || occurrence.status || 'GAP'
  )
  const [selectedRecommendation, setSelectedRecommendation] = useState(
    occurrence.substitute_teacher_id && occurrence.substitute_subject_id
      ? `${occurrence.substitute_teacher_id}:${occurrence.substitute_subject_id}`
      : ''
  )
  const [isDecisionConfirmed, setIsDecisionConfirmed] = useState(false)
  const [showAllRecommendations, setShowAllRecommendations] = useState(false)

  const {
    data: recommendations = EMPTY_ARRAY,
    isLoading: loadingRecommendations,
    isError: recommendationsError,
  } = useSubstituteRecommendations({
    occurrenceId: occurrence.id,
  })
  const { data: diagnostics } = useSubstituteDiagnostics({ occurrenceId: occurrence.id })
  const exclusionMessages = useMemo(() => {
    const candidates = diagnostics?.candidates ?? []
    const seen = new Set()
    const messages = []
    for (const candidate of candidates) {
      for (const exclusion of candidate.exclusions ?? []) {
        if (seen.has(exclusion.message)) continue
        seen.add(exclusion.message)
        messages.push({ ...exclusion, teacher_id: candidate.teacher_id })
      }
    }
    return messages.slice(0, 4)
  }, [diagnostics])

  useEffect(() => {
    if (status !== 'SUBSTITUTED') {
      return
    }
    if (selectedRecommendation) {
      return
    }
    if (recommendations.length === 0) {
      return
    }
    const first = recommendations[0]
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSelectedRecommendation(`${first.teacher_id}:${first.subject_id}`)
  }, [status, selectedRecommendation, recommendations])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsDecisionConfirmed(false)
  }, [status, selectedRecommendation])

  useEffect(() => {
    if (status !== 'SUBSTITUTED') {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setShowAllRecommendations(false)
    }
  }, [status])

  const orderedRecommendations = useMemo(() => (
    [...recommendations].sort((a, b) => {
      if (a.rank !== b.rank) return a.rank - b.rank
      return a.teacher_id - b.teacher_id
    })
  ), [recommendations])

  const topRecommendations = useMemo(
    () => orderedRecommendations.slice(0, 3),
    [orderedRecommendations]
  )

  const displayedRecommendations = useMemo(() => {
    const base = showAllRecommendations ? orderedRecommendations : topRecommendations
    if (!selectedRecommendation) return base
    const alreadyVisible = base.some(
      rec => `${rec.teacher_id}:${rec.subject_id}` === selectedRecommendation
    )
    if (alreadyVisible) return base
    const selected = orderedRecommendations.find(
      rec => `${rec.teacher_id}:${rec.subject_id}` === selectedRecommendation
    )
    if (!selected) return base
    return [...base, selected]
  }, [showAllRecommendations, orderedRecommendations, topRecommendations, selectedRecommendation])

  const handleSave = () => {
    if (!isDecisionConfirmed || !availableDecisions.includes(status)) {
      return
    }
    onSave({
      id: occurrence.id,
      status,
      version: occurrence.version,
      substituteTeacherId: status === 'SUBSTITUTED' ? selectedRecommendationData?.teacher_id ?? null : null,
      substituteSubjectId: status === 'SUBSTITUTED' ? selectedRecommendationData?.subject_id ?? null : null,
    })
  }

  const selectedRecommendationData = recommendations.find(
    rec => `${rec.teacher_id}:${rec.subject_id}` === selectedRecommendation
  )

  const cannotConfirmSubstituted = status === 'SUBSTITUTED' && !selectedRecommendationData
  const plannedTeacherName = resolveName(teacherById, occurrence.planned_teacher_id, 'Prof.')
  const executionSummary = buildExecutionSummary(occurrence, teacherById, subjectById)

  return (
    <CModal visible onClose={onClose} alignment="center" data-tutorial-target="occurrence-decision">
      <CModalHeader>
        <CModalTitle>Decisão Operacional — {formatDate(occurrence.date)}</CModalTitle>
      </CModalHeader>
      <CModalBody>
        <div className="mb-3">
          <FeedbackBanner tone="info">
            <div><strong>Docente previsto:</strong> {plannedTeacherName}</div>
            <div><strong>Execução atual:</strong> {executionSummary}</div>
            <div><strong>Decisão final:</strong> {buildDecisionSummary(occurrence)}</div>
          </FeedbackBanner>
        </div>

        {errorMessage && (
          <div className="mb-3"><FeedbackBanner tone="danger">{errorMessage}</FeedbackBanner></div>
        )}

        <div className="mb-3">
          <CFormLabel>Decisão operacional</CFormLabel>
          <CButtonGroup className="w-100" role="group" aria-label="Estado da aula">
            <CButton
              color={status === 'GIVEN' ? 'success' : 'secondary'}
              variant={status === 'GIVEN' ? undefined : 'outline'}
              onClick={() => setStatus('GIVEN')}
              disabled={!availableDecisions.includes('GIVEN')}
            >
              Dada
            </CButton>
            <CButton
              color={status === 'GAP' ? 'danger' : 'secondary'}
              variant={status === 'GAP' ? undefined : 'outline'}
              onClick={() => setStatus('GAP')}
              disabled={!availableDecisions.includes('GAP')}
            >
              Furo
            </CButton>
            <CButton
              color={status === 'SUBSTITUTED' ? 'warning' : 'secondary'}
              variant={status === 'SUBSTITUTED' ? undefined : 'outline'}
              onClick={() => setStatus('SUBSTITUTED')}
              disabled={!availableDecisions.includes('SUBSTITUTED')}
              data-tutorial-target="decision-substitute"
            >
              Substituída
            </CButton>
          </CButtonGroup>
          {lessonNotFinished && (
            <p className="small text-muted mt-2" role="status">
              Só pode decidir “Dada” depois do término desta aula.
            </p>
          )}
        </div>

        {status === 'SUBSTITUTED' && (
          <div className="mb-3">
              <CFormLabel htmlFor="substituteRecommendation">Candidato recomendado</CFormLabel>
              {loadingRecommendations && (
                <div className="d-flex align-items-center gap-2 text-muted small">
                  <CSpinner size="sm" />
                  <span>A carregar recomendações…</span>
                </div>
              )}
              {!loadingRecommendations && recommendationsError && (
                <FeedbackBanner tone="danger">
                  Não foi possível carregar as sugestões de substituição. Tente novamente.
                </FeedbackBanner>
              )}
              {!loadingRecommendations && !recommendationsError && recommendations.length === 0 && (
                <FeedbackBanner tone="warning">
                  <div className="fw-semibold">Sem elegíveis para este período.</div>
                  {exclusionMessages.length > 0 && (
                    <ul className="mb-1 mt-1 ps-3 small">
                      {exclusionMessages.map((item) => (
                        <li key={`${item.teacher_id}-${item.code}`}>
                          {item.message}{' '}
                          {item.setup === 'availability' && (
                            <Link
                              to={`/members?teacher_id=${item.teacher_id}&panel=availability&on_date=${occurrence.date}`}
                              onClick={onClose}
                            >
                              Editar disponibilidade
                            </Link>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                  <div className="small">
                    Pode decidir “Furo” ou corrigir a configuração indicada.
                  </div>
                </FeedbackBanner>
              )}
              {!loadingRecommendations && !recommendationsError && recommendations.length > 0 && (
                <>
                  <CFormSelect
                    id="substituteRecommendation"
                    value={selectedRecommendation}
                    onChange={(e) => setSelectedRecommendation(e.target.value)}
                  >
                    <option value="">— Selecionar candidato —</option>
                    {displayedRecommendations.map(rec => (
                      <option
                        key={`${rec.teacher_id}-${rec.subject_id}`}
                        value={`${rec.teacher_id}:${rec.subject_id}`}
                      >
                        {rec.teacher_name} — {rec.subject_name}
                      </option>
                    ))}
                  </CFormSelect>
                  {orderedRecommendations.length > 3 && (
                    <div className="mt-2 text-end">
                      <CButton
                        color="link"
                        className="p-0"
                        onClick={() => setShowAllRecommendations(prev => !prev)}
                      >
                        {showAllRecommendations ? 'Mostrar apenas 3 sugestões' : 'Ver lista completa'}
                      </CButton>
                    </div>
                  )}
                </>
              )}
            </div>
        )}

        <div className="mt-3">
          <CFormCheck
            id="confirmOperationalDecision"
            checked={isDecisionConfirmed}
            onChange={(e) => setIsDecisionConfirmed(e.target.checked)}
            label="Confirmo esta decisão operacional para a ocorrência selecionada."
          />
        </div>
      </CModalBody>
      <CModalFooter>
        <CButton color="secondary" variant="outline" onClick={onClose}>{TXT.CANCEL}</CButton>
        {onRevert && (
          <CButton color="secondary" variant="outline" onClick={onRevert} disabled={isSaving}>
            Reverter
          </CButton>
        )}
        <CButton
          color="primary"
          onClick={handleSave}
          disabled={!isDecisionConfirmed || cannotConfirmSubstituted || isSaving}
        >
          Confirmar decisão
        </CButton>
      </CModalFooter>
    </CModal>
  )
}

// ---------------------------------------------------------------------------
// Painel de Dívidas
// ---------------------------------------------------------------------------
const DebtsPanel = ({ classId }) => {
  const { data: debtData, isLoading, isError } = useDebts({ classId: classId || undefined })

  if (isLoading) return <div className="text-center p-4"><CSpinner /></div>
  if (isError) return <FeedbackBanner tone="danger">{TXT.ERROR_LOADING}</FeedbackBanner>
  if (!debtData || debtData.total_gaps === 0) {
    return (
      <FeedbackBanner tone="success">
        Sem dívidas de horas registadas. Todas as aulas estão em dia!
      </FeedbackBanner>
    )
  }

  return (
    <>
      <CRow className="mb-3 g-3">
        <CCol sm={6} md={4}>
          <div className="p-3 bg-danger bg-opacity-10 border border-danger rounded text-center">
            <div className="fs-2 fw-bold text-danger">{debtData.total_gaps}</div>
            <div className="text-muted small">Furos acumulados</div>
          </div>
        </CCol>
        <CCol sm={6} md={4}>
          <div className="p-3 bg-warning bg-opacity-10 border border-warning rounded text-center">
            <div className="fs-2 fw-bold text-warning">{formatDurationHours(debtData.total_hours_owed)}</div>
            <div className="text-muted small">Horas em dívida</div>
          </div>
        </CCol>
      </CRow>

      <section aria-label="Dívidas por turma" className="d-md-none">
        {debtData.items.map((item) => (
          <article key={`${item.class_id}-${item.subject_id}`} className="border rounded p-3 mb-2">
            <h3 className="h6 mb-1">{item.class_name}</h3>
            <div>{item.subject_name}</div>
            <dl className="mb-0 mt-2">
              <dt>Professor</dt><dd>{item.teacher_name ?? '—'}</dd>
              <dt>Furos</dt><dd>{item.gap_occurrences}</dd>
              <dt>Horas em dívida</dt>
              <dd className="fw-bold text-danger mb-0">{formatDurationHours(item.hours_owed)}</dd>
            </dl>
          </article>
        ))}
      </section>
      <div className="d-none d-md-block">
      <CTable hover responsive className="mb-0">
        <CTableHead color="light">
          <CTableRow>
            <CTableHeaderCell>Turma</CTableHeaderCell>
            <CTableHeaderCell>Disciplina</CTableHeaderCell>
            <CTableHeaderCell>Professor</CTableHeaderCell>
            <CTableHeaderCell className="text-center">Furos</CTableHeaderCell>
            <CTableHeaderCell className="text-end">Horas em Dívida</CTableHeaderCell>
          </CTableRow>
        </CTableHead>
        <CTableBody>
          {debtData.items.map(item => (
            <CTableRow key={`${item.class_id}-${item.subject_id}`}>
              <CTableDataCell className="fw-semibold">{item.class_name}</CTableDataCell>
              <CTableDataCell>{item.subject_name}</CTableDataCell>
              <CTableDataCell className="text-muted">{item.teacher_name ?? '—'}</CTableDataCell>
              <CTableDataCell className="text-center">
                <CBadge color="danger">{item.gap_occurrences}</CBadge>
              </CTableDataCell>
              <CTableDataCell className="text-end fw-bold text-danger">
                {formatDurationHours(item.hours_owed)}
              </CTableDataCell>
            </CTableRow>
          ))}
        </CTableBody>
      </CTable>
      </div>
    </>
  )
}

// ---------------------------------------------------------------------------
// Cartões de histórico (abaixo de 1000 px)
// ---------------------------------------------------------------------------
const OccurrenceHistoryCards = ({
  occurrences,
  teacherById,
  subjectById,
  expandedId,
  setExpandedId,
  canDecide,
  canRevert,
  revertingId,
  onDecide,
  onRevert,
}) => (
  <div className="occurrence-history__cards">
    {occurrences.map((occ) => {
      const operationalState = getOperationalState(occ)
      const executionSummary = buildExecutionSummary(occ, teacherById, subjectById)
      const isUndecided = operationalState === 'OPEN_PENDING'
      const isDecided = ['DECIDED_GIVEN', 'DECIDED_GAP', 'DECIDED_SUBSTITUTED'].includes(operationalState)
      const isRevokedV1 = operationalState === 'REVOKED' && occ.creation_source === 'scheduler_v1'
      const hasDetail = Boolean(occ.lesson_log_summary || occ.lesson_log_notes)
      const isExpanded = expandedId === occ.id
      const timeRange = occ.timeslot_start_time && occ.timeslot_end_time
        ? `${occ.timeslot_start_time.slice(0, 5)}–${occ.timeslot_end_time.slice(0, 5)}`
        : ''
      return (
        <div key={occ.id} className="border rounded p-3 mb-2">
          <div className="d-flex justify-content-between align-items-start gap-2">
            <div>
              <div className="fw-semibold">
                {formatDate(occ.date)}{timeRange ? `, ${timeRange}` : ''}
              </div>
              <div className="small">
                {occ.class_name ?? '—'} · {occ.subject_name ?? '—'}
              </div>
            </div>
            <CBadge color={OPERATIONAL_STATE_COLORS[operationalState] ?? 'secondary'}>
              <CIcon icon={OPERATIONAL_STATE_ICONS[operationalState] ?? cilClock} className="me-1" />
              {OPERATIONAL_STATE_LABELS[operationalState] ?? operationalState}
            </CBadge>
          </div>
          <div className="small text-muted mt-2">
            Docente efetivo: <span className="fw-semibold text-body">{executionSummary}</span>
          </div>
          {hasDetail && (
            <>
              <CButton
                color="link"
                size="sm"
                className="px-0 mt-1"
                aria-expanded={isExpanded}
                onClick={() => setExpandedId(isExpanded ? null : occ.id)}
              >
                {isExpanded ? 'Ocultar sumário completo' : 'Ver sumário completo'}
              </CButton>
              {isExpanded && (
                <div className="small mt-1">
                  {occ.lesson_log_summary && <p className="mb-1">{occ.lesson_log_summary}</p>}
                  {occ.lesson_log_notes && (
                    <p className="mb-1 text-muted">Notas: {occ.lesson_log_notes}</p>
                  )}
                </div>
              )}
            </>
          )}
          <div className="d-flex gap-1 mt-2">
            {isUndecided && canDecide && (
              <CButton color="primary" size="sm" variant="outline" onClick={() => onDecide(occ)}>
                Decidir
              </CButton>
            )}
            {(isDecided || isRevokedV1) && canRevert && (
              <CButton
                color="secondary"
                size="sm"
                variant="outline"
                disabled={revertingId === occ.id}
                onClick={() => onRevert(occ)}
              >
                {revertingId === occ.id ? <CSpinner size="sm" className="me-1" /> : null}
                {operationalState === 'REVOKED' ? 'Reconciliar dívida' : 'Reverter'}
              </CButton>
            )}
          </div>
        </div>
      )
    })}
  </div>
)

// ---------------------------------------------------------------------------
// Painel de Ocorrências
// ---------------------------------------------------------------------------
const OccurrencesPanel = ({
  classId,
  dateFrom,
  dateTo,
  initialOccurrenceId,
  mode,
  readOnly = false,
  allowedActions,
  filtersValid = true,
}) => {
  const [editingOccurrence, setEditingOccurrence] = useState(null)
  const [saveErrorMessage, setSaveErrorMessage] = useState('')
  const focusedOccurrenceIdRef = useRef(null)
  const [revertingId, setRevertingId] = useState(null)
  const [revertConfirmation, setRevertConfirmation] = useState(null)
  const { data: occurrencesPage, isLoading, isError } = useOccurrences({
    classId: classId || undefined,
    dateFrom: dateFrom || undefined,
    dateTo: dateTo || undefined,
    status: mode === 'pending' ? 'OPEN_PENDING' : undefined,
    enabled: filtersValid,
  })
  const occurrences = occurrencesPage?.items ?? EMPTY_ARRAY
  const { data: teachers = EMPTY_ARRAY } = useTeachers()
  const { data: subjects = EMPTY_ARRAY } = useSubjects()
  const updateMutation = useUpdateOccurrence()
  const cancelMutation = useCancelOccurrence()
  const attemptScope = useAttemptScope()
  const [expandedId, setExpandedId] = useState(null)
  const isWideHistory = useWideHistoryLayout()
  const isTutorial = Array.isArray(allowedActions)
  const canDecide = !readOnly && (!isTutorial || allowedActions.includes('DECIDE_SUBSTITUTION'))
  const canRevert = !readOnly && !isTutorial

  const teacherById = useMemo(
    () => new Map(teachers.map((teacher) => [teacher.id, teacher.name])),
    [teachers]
  )
  const subjectById = useMemo(
    () => new Map(subjects.map((subject) => [subject.id, subject.name])),
    [subjects]
  )

  const sortedOccurrences = useMemo(
    () => [...occurrences].sort(compareOccurrences),
    [occurrences]
  )

  const visibleOccurrences = useMemo(
    () => sortedOccurrences.filter((occ) => mode === 'pending'
      ? getOperationalState(occ) === 'OPEN_PENDING'
      : getOperationalState(occ) !== 'OPEN_PENDING'),
    [mode, sortedOccurrences],
  )

  useEffect(() => {
    if (!editingOccurrence) return
    const stillExists = occurrences.some((occ) => occ.id === editingOccurrence.id)
    if (!stillExists) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setEditingOccurrence(null)
      setSaveErrorMessage('')
    }
  }, [editingOccurrence, occurrences])

  useEffect(() => {
    if (!initialOccurrenceId || focusedOccurrenceIdRef.current === initialOccurrenceId) {
      return
    }
    if (isLoading) {
      return
    }

    const targetOccurrence = occurrences.find((occ) => occ.id === initialOccurrenceId)
    if (targetOccurrence) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setEditingOccurrence(targetOccurrence)
    }
    focusedOccurrenceIdRef.current = initialOccurrenceId
  }, [
    initialOccurrenceId,
    isLoading,
    occurrences,
  ])

  const closeEditModal = () => {
    setEditingOccurrence(null)
    setSaveErrorMessage('')
  }

  const openEditModal = (occurrence) => {
    if (!canDecide) return
    if (getOperationalState(occurrence) === 'REVOKED') return
    setEditingOccurrence(occurrence)
    setSaveErrorMessage('')
  }

  const handleRevert = (occurrence) => {
    if (!canRevert) return
    setRevertConfirmation(occurrence)
  }

  const confirmRevert = () => {
    if (!revertConfirmation || !canRevert) return
    const occurrence = revertConfirmation
    const hasSubstituteLog = occurrence.status === 'SUBSTITUTED'
    setRevertingId(occurrence.id)
    cancelMutation.mutate({
      id: occurrence.id,
      version: occurrence.version,
      cancelCompletedSubstituteLog: hasSubstituteLog,
    }, attemptScope.guard({
      onSuccess: () => {
        setRevertingId(null)
        setRevertConfirmation(null)
        closeEditModal()
        toast.success(occurrence.status === 'REVOKED' ? 'Dívida reconciliada.' : 'Ocorrência revertida.')
      },
      onError: (error) => {
        setRevertingId(null)
        setRevertConfirmation(null)
        const message = buildUpdateErrorMessage(error)
        if (isApiErrorTransient(error)) toast.error(message)
        else setSaveErrorMessage(message)
      },
    }))
  }

  const handleSave = (payload) => {
    if (!canDecide) return
    setSaveErrorMessage('')
    updateMutation.mutate(payload, attemptScope.guard({
      onSuccess: () => {
        closeEditModal()
        toast.success('Decisão registada.')
      },
      onError: (error) => {
        const message = buildUpdateErrorMessage(error)
        if (isApiErrorTransient(error)) toast.error(message)
        else setSaveErrorMessage(message)
      },
    }))
  }

  if (isLoading) {
    return (
      <div className="text-center p-4 d-flex justify-content-center align-items-center gap-2">
        <CSpinner />
        <span className="text-muted">{TXT.LOADING}</span>
      </div>
    )
  }

  if (isError) {
    return (
      <FeedbackBanner tone="danger">
        Não foi possível carregar as ocorrências. Verifique a ligação e volte a tentar.
      </FeedbackBanner>
    )
  }

  if (occurrences.length === 0) {
    return (
      <FeedbackBanner tone="info">
        Não foram encontradas ocorrências com os filtros selecionados.
      </FeedbackBanner>
    )
  }

  return (
    <>
      {editingOccurrence && (
        <EditOccurrenceModal
          occurrence={editingOccurrence}
          onClose={closeEditModal}
          onSave={handleSave}
           onRevert={canRevert ? () => { handleRevert(editingOccurrence) } : null}
          isSaving={updateMutation.isPending || cancelMutation.isPending}
          teacherById={teacherById}
           subjectById={subjectById}
           errorMessage={saveErrorMessage}
           allowedDecisions={isTutorial ? ['SUBSTITUTED'] : undefined}
        />
      )}
      <ConfirmationModal
        visible={Boolean(revertConfirmation)}
        onClose={() => setRevertConfirmation(null)}
        onConfirm={confirmRevert}
        title={revertConfirmation?.status === 'REVOKED' ? 'Reconciliar dívida' : 'Confirmar reversão'}
        message={
          revertConfirmation?.status === 'REVOKED'
            ? 'Esta operação preserva o histórico e corrige apenas a dívida residual desta ocorrência revertida.'
            : revertConfirmation?.status === 'SUBSTITUTED'
            ? 'Reverter esta ocorrência? O histórico será preservado e poderá criar uma nova revisão para o mesmo bloco. O registo do substituto será revertido se a semana estiver aberta.'
            : 'Reverter esta ocorrência? O histórico será preservado e poderá criar uma nova revisão para o mesmo bloco.'
        }
        confirmText={revertConfirmation?.status === 'REVOKED' ? 'Reconciliar' : 'Reverter'}
        isLoading={cancelMutation.isPending}
        variant="warning"
      />

      {visibleOccurrences.length === 0 && (
        <FeedbackBanner tone="info">
          {mode === 'pending'
            ? 'Sem ocorrências pendentes com os filtros atuais.'
            : 'Sem ocorrências no histórico com os filtros atuais.'}
        </FeedbackBanner>
      )}

      {visibleOccurrences.length > 0 && (
        <div className="occurrence-history">
        {isWideHistory ? (
        <div className="occurrence-history__table">
        <CTable hover responsive className="mb-0">
        <CTableHead color="light">
          <CTableRow>
            <CTableHeaderCell>Data/Hora</CTableHeaderCell>
            <CTableHeaderCell>Turma</CTableHeaderCell>
            <CTableHeaderCell>Disciplina</CTableHeaderCell>
            <CTableHeaderCell>Estado</CTableHeaderCell>
            <CTableHeaderCell>Sumário</CTableHeaderCell>
            <CTableHeaderCell>Docente Previsto</CTableHeaderCell>
            <CTableHeaderCell>Docente Efetivo</CTableHeaderCell>
            <CTableHeaderCell className="text-end">Ações</CTableHeaderCell>
          </CTableRow>
        </CTableHead>
        <CTableBody>
          {visibleOccurrences.map((occ) => {
            const plannedTeacherName = resolveName(teacherById, occ.planned_teacher_id, 'Prof.')
            const executionSummary = buildExecutionSummary(occ, teacherById, subjectById)
            const operationalState = getOperationalState(occ)
            const classLabel = occ.class_name ?? '—'
            const subjectLabel = occ.subject_name
              ?? resolveName(subjectById, occ.subject_id, 'Disciplina')
            const timeRange = occ.timeslot_start_time && occ.timeslot_end_time
              ? `${occ.timeslot_start_time.slice(0,5)}–${occ.timeslot_end_time.slice(0,5)}`
              : ''
            const summaryPreview = occ.lesson_log_summary
              ? (occ.lesson_log_summary.length > 80 ? occ.lesson_log_summary.slice(0, 80) + '…' : occ.lesson_log_summary)
              : '—'
            const isUndecided = operationalState === 'OPEN_PENDING'
            const isDecided = ['DECIDED_GIVEN', 'DECIDED_GAP', 'DECIDED_SUBSTITUTED'].includes(operationalState)
            const isRevokedV1 = operationalState === 'REVOKED' && occ.creation_source === 'scheduler_v1'
            const isExpanded = expandedId === occ.id
            const hasDetail = occ.lesson_log_summary || occ.lesson_log_notes
            return (
            <React.Fragment key={occ.id}>
            <CTableRow
              className={`${occ.status === 'REVOKED' ? 'table-secondary' : ''} ${hasDetail ? 'cursor-pointer' : ''}`}
              onClick={() => hasDetail && setExpandedId(isExpanded ? null : occ.id)}
              role={hasDetail ? 'button' : undefined}
              tabIndex={hasDetail ? 0 : undefined}
              onKeyDown={(e) => { if (hasDetail && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); setExpandedId(isExpanded ? null : occ.id) }}}
            >
              <CTableDataCell className="fw-semibold">
                {formatDate(occ.date)}{timeRange ? `, ${timeRange}` : ''}
              </CTableDataCell>
              <CTableDataCell className="fw-semibold">{classLabel}</CTableDataCell>
              <CTableDataCell>{subjectLabel}</CTableDataCell>
              <CTableDataCell>
                <CBadge color={OPERATIONAL_STATE_COLORS[operationalState] ?? 'secondary'}>
                  <CIcon icon={OPERATIONAL_STATE_ICONS[operationalState] ?? cilClock} className="me-1" />
                  {OPERATIONAL_STATE_LABELS[operationalState] ?? operationalState}
                </CBadge>
              </CTableDataCell>
              <CTableDataCell>
                <small className={`text-muted ${hasDetail ? 'text-decoration-underline' : ''}`}>
                  {summaryPreview}
                  {hasDetail && (
                    <span className="ms-1">{isExpanded ? '▲' : '▼'}</span>
                  )}
                </small>
              </CTableDataCell>
              <CTableDataCell>{plannedTeacherName}</CTableDataCell>
              <CTableDataCell className="fw-semibold">{executionSummary}</CTableDataCell>
              <CTableDataCell className="text-end" onClick={(e) => e.stopPropagation()}>
                <div className="d-flex gap-1 justify-content-end">
                  {isUndecided && canDecide && (
                    <CButton color="primary" size="sm" variant="outline" onClick={() => openEditModal(occ)} data-tutorial-target="decision-open">
                      Decidir
                    </CButton>
                  )}
                  {(isDecided || isRevokedV1) && canRevert && (
                    <CButton
                      color="secondary"
                      size="sm"
                      variant="outline"
                      disabled={revertingId === occ.id}
                      onClick={() => handleRevert(occ)}
                    >
                      {revertingId === occ.id ? <CSpinner size="sm" className="me-1" /> : null}
                      {operationalState === 'REVOKED' ? 'Reconciliar dívida' : 'Reverter'}
                    </CButton>
                  )}
                  {!isUndecided && !isDecided && !isRevokedV1 && (
                    <span className="text-muted small">—</span>
                  )}
                </div>
              </CTableDataCell>
            </CTableRow>
            {isExpanded && (
              <CTableRow key={`${occ.id}-detail`} className="bg-light">
                <CTableDataCell colSpan={8} className="py-3">
                  <div style={{ fontSize: '0.85rem' }}>
                    {occ.lesson_log_summary && (
                      <div className="mb-2">
                        <strong>Sumário completo:</strong>
                        <p className="mb-1 mt-1 text-muted">{occ.lesson_log_summary}</p>
                      </div>
                    )}
                    {occ.lesson_log_notes && (
                      <div className="mb-2">
                        <strong>Notas:</strong>
                        <p className="mb-1 mt-1 text-muted">{occ.lesson_log_notes}</p>
                      </div>
                    )}
                    <div className="d-flex flex-wrap gap-4">
                      {occ.created_at && (
                        <div>
                          <strong>Criada:</strong>{' '}
                          <span className="text-muted">{formatDateTime(occ.created_at)}</span>
                        </div>
                      )}
                      {occ.decided_at && (
                        <div>
                          <strong>Decidida:</strong>{' '}
                          <span className="text-muted">{formatDateTime(occ.decided_at)}</span>
                        </div>
                      )}
                      {occ.decided_by_membership_id && (
                        <div>
                          <strong>Decisor:</strong>{' '}
                          <span className="text-muted">{buildDeciderDisplayName(occ)}</span>
                        </div>
                      )}
                    </div>
                  </div>
                </CTableDataCell>
              </CTableRow>
            )}
            </React.Fragment>
            )
          })}
        </CTableBody>
      </CTable>
        </div>
        ) : (
        <OccurrenceHistoryCards
          occurrences={visibleOccurrences}
          teacherById={teacherById}
          subjectById={subjectById}
          expandedId={expandedId}
          setExpandedId={setExpandedId}
          canDecide={canDecide}
          canRevert={canRevert}
          revertingId={revertingId}
          onDecide={openEditModal}
          onRevert={handleRevert}
        />
        )}
        </div>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Página principal
// ---------------------------------------------------------------------------
const Occurrences = ({
  tabOverride,
  readOnly = false,
  allowedActions,
  navigationDisabled = false,
} = {}) => {
  const [searchParams, setSearchParams] = useSearchParams()

  const classFilter = searchParams.get('class_id') ?? ''
  const dateFrom = searchParams.get('date_from') ?? ''
  const dateTo = searchParams.get('date_to') ?? ''
  const parsedOccurrenceId = Number.parseInt(searchParams.get('occurrence_id') ?? '', 10)
  const initialOccurrenceId = Number.isNaN(parsedOccurrenceId) ? undefined : parsedOccurrenceId
  const statusParam = searchParams.get('status') ?? ''
  const tabParam = tabOverride ?? searchParams.get('tab') ?? ''
  const activeTab = VALID_TABS.has(tabParam)
    ? tabParam
    : ['GAP', 'SUBSTITUTED', 'GIVEN', 'REVOKED'].includes(statusParam.toUpperCase())
      ? 'historical'
      : 'occurrences'

  const updateSearchParam = (name, value) => {
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous)
      if (value) next.set(name, value)
      else next.delete(name)
      return next
    })
  }

  const handleTabChange = (tab) => {
    if (VALID_TABS.has(tab)) updateSearchParam('tab', tab)
  }

  const { data: classes = EMPTY_ARRAY } = useClasses()
  const invalidDateRange = Boolean(dateFrom && dateTo && isAfterDate(dateFrom, dateTo))

  return (
    <div
      className="p-4"
      data-tutorial-target="occurrences-workspace"
      data-tutorial-navigation-disabled={navigationDisabled || undefined}
    >
      {/* Cabeçalho */}
      <PageHeader preTitle="Operações" title="Faltas e Ocorrências" />

      {/* Filtros globais */}
      <CCard className="border-0 shadow-sm mb-4">
        <CCardBody>
          <CRow className="g-3 align-items-end">
            <CCol md={4}>
              <CFormLabel htmlFor="classFilterOcc">Turma</CFormLabel>
              <CFormSelect
                id="classFilterOcc"
                value={classFilter}
                onChange={(e) => updateSearchParam('class_id', e.target.value)}
              >
                <option value="">— Todas as turmas —</option>
                {[...classes].sort((a, b) => a.name.localeCompare(b.name)).map(c => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </CFormSelect>
            </CCol>
            <CCol md={3}>
              <CFormLabel htmlFor="dateFromFilter">De</CFormLabel>
              <PortugueseDateInput
                id="dateFromFilter"
                value={dateFrom}
                onChange={(value) => updateSearchParam('date_from', value)}
              />
            </CCol>
            <CCol md={3}>
              <CFormLabel htmlFor="dateToFilter">Até</CFormLabel>
              <PortugueseDateInput
                id="dateToFilter"
                value={dateTo}
                onChange={(value) => updateSearchParam('date_to', value)}
              />
            </CCol>
          </CRow>
          {invalidDateRange && (
            <div className="mt-3">
              <FeedbackBanner tone="danger">
                A data “De” tem de ser anterior ou igual à data “Até”.
              </FeedbackBanner>
            </div>
          )}
        </CCardBody>
      </CCard>

      {/* Tabs */}
      <CTabs activeItemKey={activeTab} onChange={handleTabChange}>
        <CTabList variant="underline-border" className="mb-3">
          <CTab itemKey="occurrences">
            <CIcon icon={cilClock} className="me-1" />
            Decisões Pendentes
          </CTab>
          <CTab itemKey="historical">
            <CIcon icon={cilCheckCircle} className="me-1" />
            Histórico
          </CTab>
          <CTab itemKey="debts">
            <CIcon icon={cilWarning} className="me-1" />
            Dívidas de Horas
          </CTab>
        </CTabList>

        <CCard className="border-0 shadow-sm">
          <CCardBody>
            {activeTab === 'debts' ? (
              <DebtsPanel classId={classFilter} readOnly={readOnly} />
            ) : (
              <OccurrencesPanel
                classId={classFilter}
                dateFrom={dateFrom}
                dateTo={dateTo}
                initialOccurrenceId={initialOccurrenceId}
                mode={activeTab === 'historical' ? 'historical' : 'pending'}
                readOnly={readOnly}
                allowedActions={allowedActions}
                filtersValid={!invalidDateRange}
              />
            )}
          </CCardBody>
        </CCard>
      </CTabs>
    </div>
  )
}

export default Occurrences
