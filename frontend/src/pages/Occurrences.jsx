import React, { useEffect, useMemo, useState } from 'react'
import PropTypes from 'prop-types'
import { useSearchParams } from 'react-router-dom'
import {
  CCard, CCardBody, CCardHeader, CCol, CRow, CAlert, CBadge, CSpinner,
  CButton, CFormSelect, CFormInput, CFormLabel, CTabs, CTabList, CTab,
  CTabContent, CTabPanel, CTable, CTableHead, CTableRow, CTableHeaderCell,
  CTableBody, CTableDataCell, CModal, CModalHeader, CModalTitle,
  CModalBody, CModalFooter, CButtonGroup, CFormCheck,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilWarning, cilCheckCircle, cilBan, cilPeople, cilClock } from '@coreui/icons'
import {
  useOccurrences, useDebts, useUpdateOccurrence,
  useSubstituteRecommendations, useClasses, useTeachers, useSubjects,
} from '../hooks/useSchoolData'
import { useAuthStore } from '../store'
import { formatDate, formatDateTime } from '../utils/formatUtils'
import { TXT } from '../utils/terminology'

// ---------------------------------------------------------------------------
// Constantes
// ---------------------------------------------------------------------------
const STATUS_LABELS = {
  GIVEN: 'Dada',
  GAP: 'Furo',
  SUBSTITUTED: 'Substituída',
}

const STATUS_COLORS = {
  GIVEN: 'success',
  GAP: 'danger',
  SUBSTITUTED: 'warning',
}

const STATUS_ICONS = {
  GIVEN: cilCheckCircle,
  GAP: cilBan,
  SUBSTITUTED: cilWarning,
}

const OPERATIONAL_STATE_LABELS = {
  OPEN_PENDING: 'Pendente de decisão',
  CLOSED: 'Resolvida',
}

const OPERATIONAL_STATE_COLORS = {
  OPEN_PENDING: 'info',
  CLOSED: 'secondary',
}

const OPERATIONAL_STATE_ICONS = {
  OPEN_PENDING: cilClock,
  CLOSED: cilCheckCircle,
}

const RESOLUTION_FILTERS = {
  pending: 'Pendentes',
  resolved: 'Resolvidas',
  all: 'Todas',
}

const resolveOccurrenceStartTime = (occurrence) => {
  if (typeof occurrence?.timeslot?.start_time === 'string') {
    return occurrence.timeslot.start_time
  }
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
  const detail = error?.response?.data?.detail
  if (Array.isArray(detail) && detail.length > 0) {
    const firstItem = detail[0]
    if (typeof firstItem?.msg === 'string') return firstItem.msg
  }
  if (typeof detail === 'string' && detail.trim()) return detail
  return TXT.ERROR_SAVING
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
  if (occurrence.decided_by_user_name) {
    return occurrence.decided_by_user_name
  }
  if (occurrence.decided_by_user_id) {
    return `Utilizador #${occurrence.decided_by_user_id}`
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
  if (!occurrence.decided_at) {
    return 'OPEN_PENDING'
  }
  return 'CLOSED'
}

// ---------------------------------------------------------------------------
// Modal de edição de ocorrência
// ---------------------------------------------------------------------------
const EditOccurrenceModal = ({
  occurrence,
  onClose,
  onSave,
  isSaving,
  teacherById,
  subjectById,
  errorMessage,
}) => {
  const [status, setStatus] = useState(occurrence.status)
  const [selectedRecommendation, setSelectedRecommendation] = useState(
    occurrence.substitute_teacher_id && occurrence.substitute_subject_id
      ? `${occurrence.substitute_teacher_id}:${occurrence.substitute_subject_id}`
      : ''
  )
  const [isDecisionConfirmed, setIsDecisionConfirmed] = useState(false)
  const [showAllRecommendations, setShowAllRecommendations] = useState(false)

  const {
    data: recommendations = [],
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
    setSelectedRecommendation(`${first.teacher_id}:${first.subject_id}`)
  }, [status, selectedRecommendation, recommendations])

  useEffect(() => {
    setIsDecisionConfirmed(false)
  }, [status, selectedRecommendation])

  useEffect(() => {
    if (status !== 'SUBSTITUTED') {
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
    if (!isDecisionConfirmed) {
      return
    }
    onSave({
      id: occurrence.id,
      status,
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
    <CModal visible onClose={onClose} alignment="center">
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
              color={status === 'GIVEN' ? 'primary' : 'secondary'}
              variant={status === 'GIVEN' ? undefined : 'outline'}
              onClick={() => setStatus('GIVEN')}
            >
              Dada
            </CButton>
            <CButton
              color={status === 'GAP' ? 'danger' : 'secondary'}
              variant={status === 'GAP' ? undefined : 'outline'}
              onClick={() => setStatus('GAP')}
            >
              Furo
            </CButton>
            <CButton
              color={status === 'SUBSTITUTED' ? 'warning' : 'secondary'}
              variant={status === 'SUBSTITUTED' ? undefined : 'outline'}
              onClick={() => setStatus('SUBSTITUTED')}
            >
              Substituída
            </CButton>
          </CButtonGroup>
        </div>

        {status === 'SUBSTITUTED' && (
          <>
            <div className="mb-3">
              <CFormLabel htmlFor="substituteRecommendation">Candidato recomendado (ranking)</CFormLabel>
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
                  <CAlert color="info" className="mb-2 py-2">
                    A mostrar top 3 para decisão rápida.
                  </CAlert>
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

            {selectedRecommendationData && (
              <CAlert color="info" className="mb-0">
                {selectedRecommendationData.justification}
              </CAlert>
            )}
          </>
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

EditOccurrenceModal.propTypes = {
  occurrence: PropTypes.shape({
    id: PropTypes.number.isRequired,
    date: PropTypes.string,
    status: PropTypes.string.isRequired,
    class_id: PropTypes.number,
    class_name: PropTypes.string,
    subject_id: PropTypes.number,
    subject_name: PropTypes.string,
    timeslot_id: PropTypes.number,
    planned_teacher_id: PropTypes.number,
    planned_teacher_name: PropTypes.string,
    executed_teacher_id: PropTypes.number,
    executed_teacher_name: PropTypes.string,
    decided_by_user_id: PropTypes.number,
    decided_by_user_name: PropTypes.string,
    decided_at: PropTypes.string,
    substitute_teacher_id: PropTypes.number,
    substitute_subject_id: PropTypes.number,
  }).isRequired,
  onClose: PropTypes.func.isRequired,
  onSave: PropTypes.func.isRequired,
  isSaving: PropTypes.bool,
  teacherById: PropTypes.instanceOf(Map).isRequired,
  subjectById: PropTypes.instanceOf(Map).isRequired,
  errorMessage: PropTypes.string,
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

DebtsPanel.propTypes = {
  classId: PropTypes.oneOfType([PropTypes.number, PropTypes.string]),
}

// ---------------------------------------------------------------------------
// Painel de Ocorrências
// ---------------------------------------------------------------------------
const OccurrencesPanel = ({ classId, dateFrom, dateTo, initialOccurrenceId }) => {
  const user = useAuthStore((state) => state.user)
  const isAdmin = user?.role === 'admin'
  const [editingOccurrence, setEditingOccurrence] = useState(null)
  const [resolutionFilter, setResolutionFilter] = useState('all')
  const [saveErrorMessage, setSaveErrorMessage] = useState('')
  const [hasAppliedInitialFocus, setHasAppliedInitialFocus] = useState(false)
  const { data: occurrences = [], isLoading, isError } = useOccurrences({
    classId: classId || undefined,
    dateFrom: dateFrom || undefined,
    dateTo: dateTo || undefined,
  })
  const { data: teachers = [] } = useTeachers()
  const { data: subjects = [] } = useSubjects()
  const updateMutation = useUpdateOccurrence()

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
    () => sortedOccurrences.filter((occ) => !occ.decided_at).length,
    [sortedOccurrences]
  )
  const resolvedCount = sortedOccurrences.length - pendingCount

  const visibleOccurrences = useMemo(() => {
    if (resolutionFilter === 'pending') {
      return sortedOccurrences.filter((occ) => !occ.decided_at)
    }
    if (resolutionFilter === 'resolved') {
      return sortedOccurrences.filter((occ) => Boolean(occ.decided_at))
    }
    return sortedOccurrences
  }, [resolutionFilter, sortedOccurrences])

  useEffect(() => {
    if (!editingOccurrence) return
    const stillExists = occurrences.some((occ) => occ.id === editingOccurrence.id)
    if (!stillExists) {
      setEditingOccurrence(null)
      setSaveErrorMessage('')
    }
  }, [editingOccurrence, occurrences])

  useEffect(() => {
    setHasAppliedInitialFocus(false)
    setEditingOccurrence(null)
    setSaveErrorMessage('')
  }, [initialOccurrenceId])

  useEffect(() => {
    if (!initialOccurrenceId || hasAppliedInitialFocus) {
      return
    }
    if (isLoading) {
      return
    }

    setResolutionFilter('all')
    const targetOccurrence = occurrences.find((occ) => occ.id === initialOccurrenceId)
    if (targetOccurrence && isAdmin) {
      setEditingOccurrence(targetOccurrence)
    }
    setHasAppliedInitialFocus(true)
  }, [
    initialOccurrenceId,
    hasAppliedInitialFocus,
    isLoading,
    occurrences,
    isAdmin,
  ])

  const closeEditModal = () => {
    setEditingOccurrence(null)
    setSaveErrorMessage('')
  }

  const openEditModal = (occurrence) => {
    if (!isAdmin || occurrence.decided_at) return
    setEditingOccurrence(occurrence)
    setSaveErrorMessage('')
  }

  const handleSave = (payload) => {
    setSaveErrorMessage('')
    updateMutation.mutate(payload, {
      onSuccess: () => closeEditModal(),
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
      {!isAdmin && (
        <CAlert color="warning" className="mb-3">
          Modo de leitura: apenas admin pode confirmar decisões operacionais.
        </CAlert>
      )}

      {editingOccurrence && (
        <EditOccurrenceModal
          occurrence={editingOccurrence}
          onClose={closeEditModal}
          onSave={handleSave}
          isSaving={updateMutation.isPending}
          teacherById={teacherById}
          subjectById={subjectById}
          errorMessage={saveErrorMessage}
        />
      )}

      <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
        <div className="text-muted small">
          {pendingCount} pendentes, {resolvedCount} resolvidas
        </div>
        <CButtonGroup size="sm" role="group" aria-label="Filtro de resolução">
          <CButton
            color={resolutionFilter === 'pending' ? 'primary' : 'secondary'}
            variant={resolutionFilter === 'pending' ? undefined : 'outline'}
            onClick={() => setResolutionFilter('pending')}
          >
            {RESOLUTION_FILTERS.pending} ({pendingCount})
          </CButton>
          <CButton
            color={resolutionFilter === 'resolved' ? 'primary' : 'secondary'}
            variant={resolutionFilter === 'resolved' ? undefined : 'outline'}
            onClick={() => setResolutionFilter('resolved')}
          >
            {RESOLUTION_FILTERS.resolved} ({resolvedCount})
          </CButton>
          <CButton
            color={resolutionFilter === 'all' ? 'primary' : 'secondary'}
            variant={resolutionFilter === 'all' ? undefined : 'outline'}
            onClick={() => setResolutionFilter('all')}
          >
            {RESOLUTION_FILTERS.all} ({sortedOccurrences.length})
          </CButton>
        </CButtonGroup>
      </div>

      {visibleOccurrences.length === 0 && (
        <CAlert color="light" className="mb-0">
          {resolutionFilter === 'pending' && 'Sem ocorrências pendentes com os filtros atuais.'}
          {resolutionFilter === 'resolved' && 'Sem ocorrências resolvidas com os filtros atuais.'}
          {resolutionFilter === 'all' && 'Sem ocorrências para apresentar.'}
        </CAlert>
      )}

      {visibleOccurrences.length > 0 && (
        <CTable hover responsive className="mb-0">
        <CTableHead color="light">
          <CTableRow>
            <CTableHeaderCell>Data</CTableHeaderCell>
            <CTableHeaderCell>Turma</CTableHeaderCell>
            <CTableHeaderCell>Disciplina</CTableHeaderCell>
            <CTableHeaderCell>Estado</CTableHeaderCell>
            <CTableHeaderCell>Docente Previsto</CTableHeaderCell>
            <CTableHeaderCell>Docente Definitivo</CTableHeaderCell>
            <CTableHeaderCell>Decisão Final</CTableHeaderCell>
            <CTableHeaderCell className="text-end">Ação</CTableHeaderCell>
          </CTableRow>
        </CTableHead>
        <CTableBody>
          {visibleOccurrences.map((occ) => {
            const plannedTeacherName = resolveName(teacherById, occ.planned_teacher_id, 'Prof.')
            const executionSummary = buildExecutionSummary(occ, teacherById, subjectById)
            const decisionSummary = buildDecisionSummary(occ)
            const operationalState = getOperationalState(occ)
            const outcomeColor = STATUS_COLORS[occ.status] ?? 'secondary'
            const outcomeIcon = STATUS_ICONS[occ.status] ?? cilClock
            const classLabel = occ.class_name ?? '—'
            const subjectLabel = occ.subject_name
              ?? resolveName(subjectById, occ.subject_id, 'Disciplina')
            return (
            <CTableRow key={occ.id}>
              <CTableDataCell className="fw-semibold">{formatDate(occ.date)}</CTableDataCell>
              <CTableDataCell className="fw-semibold">{classLabel}</CTableDataCell>
              <CTableDataCell>{subjectLabel}</CTableDataCell>
              <CTableDataCell>
                <CBadge color={OPERATIONAL_STATE_COLORS[operationalState] ?? 'secondary'}>
                  <CIcon icon={OPERATIONAL_STATE_ICONS[operationalState] ?? cilClock} className="me-1" />
                  {OPERATIONAL_STATE_LABELS[operationalState] ?? operationalState}
                </CBadge>
              </CTableDataCell>
              <CTableDataCell>{plannedTeacherName}</CTableDataCell>
              <CTableDataCell className="fw-semibold">{executionSummary}</CTableDataCell>
              <CTableDataCell>
                <small className="text-muted">{decisionSummary}</small>
              </CTableDataCell>
              <CTableDataCell className="text-end">
                <CButton
                  color="primary"
                  size="sm"
                  variant="outline"
                  onClick={() => openEditModal(occ)}
                  disabled={!isAdmin || Boolean(occ.decided_at)}
                >
                  {!isAdmin ? 'Sem permissão' : (occ.decided_at ? 'Fechada' : 'Decidir')}
                </CButton>
              </CTableDataCell>
            </CTableRow>
            )
          })}
        </CTableBody>
      </CTable>
      )}
    </>
  )
}

OccurrencesPanel.propTypes = {
  classId: PropTypes.oneOfType([PropTypes.number, PropTypes.string]),
  dateFrom: PropTypes.string,
  dateTo: PropTypes.string,
  initialOccurrenceId: PropTypes.number,
}

// ---------------------------------------------------------------------------
// Página principal
// ---------------------------------------------------------------------------
const Occurrences = () => {
  const [searchParams] = useSearchParams()

  const initialClassFilter = searchParams.get('class_id') ?? ''
  const initialDateFrom = searchParams.get('date_from') ?? ''
  const initialDateTo = searchParams.get('date_to') ?? ''
  const parsedOccurrenceId = Number.parseInt(searchParams.get('occurrence_id') ?? '', 10)
  const initialOccurrenceId = Number.isNaN(parsedOccurrenceId) ? undefined : parsedOccurrenceId

  const [classFilter, setClassFilter] = useState(initialClassFilter)
  const [dateFrom, setDateFrom] = useState(initialDateFrom)
  const [dateTo, setDateTo] = useState(initialDateTo)
  const [activeTab, setActiveTab] = useState('occurrences')

  useEffect(() => {
    setClassFilter(initialClassFilter)
    setDateFrom(initialDateFrom)
    setDateTo(initialDateTo)
    setActiveTab('occurrences')
  }, [initialClassFilter, initialDateFrom, initialDateTo, initialOccurrenceId])

  const { data: classes = [] } = useClasses()

  return (
    <div className="p-4">
      {/* Cabeçalho */}
      <div className="d-flex justify-content-between align-items-center mb-4">
        <div>
          <h2 className="mb-0 fw-bold text-dark">
            <CIcon icon={cilPeople} className="me-2 text-primary" />
            Gestão de Faltas e Ocorrências
          </h2>
          <small className="text-muted">
            Registe faltas, confirme substituições e consulte dívidas de horas.
          </small>
        </div>
      </div>

      {/* Filtros globais */}
      <CCard className="border-0 shadow-sm mb-4">
        <CCardBody>
          <CRow className="g-3 align-items-end">
            <CCol md={4}>
              <CFormLabel htmlFor="classFilterOcc">Turma</CFormLabel>
              <CFormSelect
                id="classFilterOcc"
                value={classFilter}
                onChange={(e) => setClassFilter(e.target.value)}
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
                onChange={(e) => setDateFrom(e.target.value)}
              />
            </CCol>
            <CCol md={3}>
              <CFormLabel htmlFor="dateToFilter">Até</CFormLabel>
              <CFormInput
                id="dateToFilter"
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
              />
            </CCol>
          </CRow>
        </CCardBody>
      </CCard>

      {/* Tabs */}
      <CTabs activeItemKey={activeTab} onChange={setActiveTab}>
        <CTabList variant="underline-border" className="mb-3">
          <CTab itemKey="debts">
            <CIcon icon={cilWarning} className="me-1" />
            Dívidas de Horas
          </CTab>
          <CTab itemKey="occurrences">
            <CIcon icon={cilClock} className="me-1" />
            Ocorrências Registadas
          </CTab>
        </CTabList>

        <CTabContent>
          {/* Tab: Dívidas */}
          <CTabPanel className="p-0" itemKey="debts">
            <CCard className="border-0 shadow-sm">
              <CCardHeader className="bg-transparent fw-semibold">
                Resumo de Dívidas de Horas
              </CCardHeader>
              <CCardBody>
                <DebtsPanel classId={classFilter} />
              </CCardBody>
            </CCard>
          </CTabPanel>

          {/* Tab: Ocorrências */}
          <CTabPanel className="p-0" itemKey="occurrences">
            <CCard className="border-0 shadow-sm">
              <CCardHeader className="bg-transparent fw-semibold">
                Ocorrências Registadas
              </CCardHeader>
              <CCardBody>
                <OccurrencesPanel
                  classId={classFilter}
                  dateFrom={dateFrom}
                  dateTo={dateTo}
                  initialOccurrenceId={initialOccurrenceId}
                />
              </CCardBody>
            </CCard>
          </CTabPanel>
        </CTabContent>
      </CTabs>
    </div>
  )
}

export default Occurrences
