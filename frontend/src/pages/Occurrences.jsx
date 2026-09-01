import React, { useEffect, useMemo, useRef, useState } from 'react'
import PageHeader from '../components/PageHeader'
import { useSearchParams } from 'react-router-dom'
import {
  CCard, CCardBody, CCardHeader, CCol, CRow, CAlert, CBadge, CSpinner,
  CButton, CFormSelect, CFormInput, CFormLabel, CTabs, CTabList, CTab,
  CTable, CTableHead, CTableRow, CTableHeaderCell,
  CTableBody, CTableDataCell, CModal, CModalHeader, CModalTitle,
  CModalBody, CModalFooter, CButtonGroup, CFormCheck,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilWarning, cilCheckCircle, cilBan, cilClock } from '@coreui/icons'
import {
  useOccurrences, useDebts, useUpdateOccurrence, useCancelOccurrence,
  useSubstituteRecommendations,
} from '../features/operations/data'
import { useClasses, useSubjects } from '../features/catalog/data'
import { useTeachers } from '../features/members/data'
import { formatDate, formatDateTime } from '../utils/formatUtils'
import { TXT, OPERATIONAL_STATE_LABELS, OPERATIONAL_STATE_COLORS } from '../utils/terminology'
import ConfirmationModal from '../components/ConfirmationModal'
import { getApiErrorMessage } from '../utils/apiErrors'

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
  return `${fallbackPrefix} #${id}`
}

const buildExecutionSummary = (occurrence, teacherById, subjectById) => {
  if (occurrence.status === 'GAP') {
    return 'Aula não realizada'
  }

  if (occurrence.status === 'SUBSTITUTED') {
    const teacherName = occurrence.executed_teacher_name
      ?? resolveName(teacherById, occurrence.substitute_teacher_id, 'Prof.')
    const subjectName = resolveName(subjectById, occurrence.substitute_subject_id, 'Disciplina')
    return `${teacherName} (${subjectName})`
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
    return `Membro #${occurrence.decided_by_membership_id}`
  }
  return 'Admin'
}

const buildDecisionSummary = (occurrence) => {
  if (!occurrence.decided_at) {
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
  const availableDecisions = allowedDecisions ?? ['GIVEN', 'GAP', 'SUBSTITUTED']
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
      reason: 'Decisao operacional',
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
        <CAlert color="light" className="mb-3">
          <div><strong>Docente previsto:</strong> {plannedTeacherName}</div>
          <div><strong>Execução atual:</strong> {executionSummary}</div>
          <div><strong>Decisão final:</strong> {buildDecisionSummary(occurrence)}</div>
        </CAlert>

        {errorMessage && (
          <CAlert color="danger" className="mb-3">
            {errorMessage}
          </CAlert>
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
                <CAlert color="danger" className="mb-0">
                  Erro ao carregar ranking de elegíveis. Tente novamente.
                </CAlert>
              )}
              {!loadingRecommendations && !recommendationsError && recommendations.length === 0 && (
                <CAlert color="warning" className="mb-0">
                  Sem elegíveis para este slot. Registe como GAP.
                </CAlert>
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
                        #{rec.rank} {rec.teacher_name} — {rec.subject_name}
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
                        {showAllRecommendations ? 'Mostrar apenas top 3' : 'Ver lista completa'}
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
  if (isError) return <CAlert color="danger">{TXT.ERROR_LOADING}</CAlert>
  if (!debtData || debtData.total_gaps === 0) {
    return (
      <CAlert color="success" className="d-flex align-items-center gap-2">
        <CIcon icon={cilCheckCircle} />
        <span>Sem dívidas de horas registadas. Todas as aulas estão em dia!</span>
      </CAlert>
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
            <div className="fs-2 fw-bold text-warning">{debtData.total_hours_owed}h</div>
            <div className="text-muted small">Horas em dívida</div>
          </div>
        </CCol>
      </CRow>

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
                {item.hours_owed}h
              </CTableDataCell>
            </CTableRow>
          ))}
        </CTableBody>
      </CTable>
    </>
  )
}

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
  })
  const occurrences = occurrencesPage?.items ?? EMPTY_ARRAY
  const { data: teachers = EMPTY_ARRAY } = useTeachers()
  const { data: subjects = EMPTY_ARRAY } = useSubjects()
  const updateMutation = useUpdateOccurrence()
  const cancelMutation = useCancelOccurrence()
  const [expandedId, setExpandedId] = useState(null)
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

  const pendingCount = useMemo(
    () => sortedOccurrences.filter((occ) => getOperationalState(occ) === 'OPEN_PENDING').length,
    [sortedOccurrences]
  )
  const resolvedCount = sortedOccurrences.length - pendingCount

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
      reason: 'Reversao administrativa',
      cancelCompletedSubstituteLog: hasSubstituteLog,
    }, {
      onSuccess: () => {
        setRevertingId(null)
        setRevertConfirmation(null)
        closeEditModal()
      },
      onError: (error) => {
        setRevertingId(null)
        setRevertConfirmation(null)
        setSaveErrorMessage(buildUpdateErrorMessage(error))
      },
    })
  }

  const handleSave = (payload) => {
    if (!canDecide) return
    setSaveErrorMessage('')
    updateMutation.mutate(payload, {
      onSuccess: () => {
        closeEditModal()
      },
      onError: (error) => setSaveErrorMessage(buildUpdateErrorMessage(error)),
    })
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
      <CAlert color="danger" className="mb-0">
        Não foi possível carregar as ocorrências. Verifique a ligação e volte a tentar.
      </CAlert>
    )
  }

  if (occurrences.length === 0) {
    return (
      <CAlert color="info">
        Não foram encontradas ocorrências com os filtros selecionados.
      </CAlert>
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
        title="Confirmar reversão"
        message={
          revertConfirmation?.status === 'SUBSTITUTED'
            ? 'Reverter esta ocorrência? O histórico será preservado e poderá criar uma nova revisão para o mesmo bloco. O registo do substituto será revertido se a semana estiver aberta.'
            : 'Reverter esta ocorrência? O histórico será preservado e poderá criar uma nova revisão para o mesmo bloco.'
        }
        confirmText="Reverter"
        isLoading={cancelMutation.isPending}
        variant="warning"
      />

      <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
        <div className="text-muted small">
          {mode === 'pending' ? `${pendingCount} pendentes` : `${resolvedCount} no histórico`}
        </div>
      </div>

      {visibleOccurrences.length === 0 && (
        <CAlert color="light" className="mb-0">
          {mode === 'pending'
            ? 'Sem ocorrências pendentes com os filtros atuais.'
            : 'Sem ocorrências no histórico com os filtros atuais.'}
        </CAlert>
      )}

      {visibleOccurrences.length > 0 && (
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
            const isExpanded = expandedId === occ.id
            const hasDetail = occ.lesson_log_summary || occ.lesson_log_notes
            return (
            <React.Fragment key={occ.id}>
            <CTableRow
              className={`${occ.status === 'REVOKED' ? 'opacity-50' : ''} ${hasDetail ? 'cursor-pointer' : ''}`}
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
                  {isDecided && canRevert && (
                    <CButton
                      color="secondary"
                      size="sm"
                      variant="outline"
                      disabled={revertingId === occ.id}
                      onClick={() => handleRevert(occ)}
                    >
                      {revertingId === occ.id ? <CSpinner size="sm" className="me-1" /> : null}
                      Reverter
                    </CButton>
                  )}
                  {!isUndecided && !isDecided && (
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
              <CFormInput
                id="dateFromFilter"
                type="date"
                value={dateFrom}
                onChange={(e) => updateSearchParam('date_from', e.target.value)}
              />
            </CCol>
            <CCol md={3}>
              <CFormLabel htmlFor="dateToFilter">Até</CFormLabel>
              <CFormInput
                id="dateToFilter"
                type="date"
                value={dateTo}
                onChange={(e) => updateSearchParam('date_to', e.target.value)}
              />
            </CCol>
          </CRow>
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
          <CCardHeader className="bg-transparent fw-semibold">
            {activeTab === 'occurrences' && 'Decisões Pendentes'}
            {activeTab === 'historical' && 'Histórico de Ocorrências'}
            {activeTab === 'debts' && 'Resumo de Dívidas de Horas'}
          </CCardHeader>
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
              />
            )}
          </CCardBody>
        </CCard>
      </CTabs>
    </div>
  )
}

export default Occurrences
