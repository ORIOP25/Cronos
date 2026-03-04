import React, { useState } from 'react'
import PropTypes from 'prop-types'
import {
  CCard, CCardBody, CCardHeader, CCol, CRow, CAlert, CBadge, CSpinner,
  CButton, CFormSelect, CFormInput, CFormLabel, CTabs, CTabList, CTab,
  CTabContent, CTabPanel, CTable, CTableHead, CTableRow, CTableHeaderCell,
  CTableBody, CTableDataCell, CModal, CModalHeader, CModalTitle,
  CModalBody, CModalFooter,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilWarning, cilCheckCircle, cilBan, cilPeople, cilClock } from '@coreui/icons'
import {
  useOccurrences, useDebts, useUpdateOccurrence,
  useAvailableSubstitutes, useClasses,
} from '../hooks/useSchoolData'

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

const formatDate = (dateStr) => {
  if (!dateStr) return '—'
  const [year, month, day] = dateStr.split('-')
  return `${day}/${month}/${year}`
}

// ---------------------------------------------------------------------------
// Modal de edição de ocorrência
// ---------------------------------------------------------------------------
const EditOccurrenceModal = ({ occurrence, onClose, onSave }) => {
  const [status, setStatus] = useState(occurrence.status)
  const [substituteTeacherId, setSubstituteTeacherId] = useState(
    occurrence.substitute_teacher_id ?? ''
  )
  const [substituteSubjectId, setSubstituteSubjectId] = useState(
    occurrence.substitute_subject_id ?? ''
  )

  const { data: substitutes = [], isLoading: loadingSubs } = useAvailableSubstitutes({
    timeslotId: occurrence.timeslot_id,
    targetDate: occurrence.date,
  })

  const handleSave = () => {
    onSave({
      id: occurrence.id,
      status,
      substituteTeacherId: status === 'SUBSTITUTED' ? Number.parseInt(substituteTeacherId, 10) : null,
      substituteSubjectId: status === 'SUBSTITUTED' && substituteSubjectId
        ? Number.parseInt(substituteSubjectId, 10)
        : null,
    })
  }

  const uniqueSubjects = substitutes.reduce((acc, sub) => {
    if (!acc.some(s => s.subject_id === sub.subject_id)) acc.push(sub)
    return acc
  }, [])

  return (
    <CModal visible onClose={onClose} alignment="center">
      <CModalHeader>
        <CModalTitle>Editar Ocorrência — {formatDate(occurrence.date)}</CModalTitle>
      </CModalHeader>
      <CModalBody>
        <div className="mb-3">
          <CFormLabel htmlFor="occurrenceStatus">Estado da aula</CFormLabel>
          <CFormSelect
            id="occurrenceStatus"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="GIVEN">Dada (aula decorreu normalmente)</option>
            <option value="GAP">Furo (professor faltou, sem substituto)</option>
            <option value="SUBSTITUTED">Substituída (outro professor cobriu)</option>
          </CFormSelect>
        </div>

        {status === 'SUBSTITUTED' && (
          <>
            <div className="mb-3">
              <CFormLabel htmlFor="substituteTeacher">Professor substituto</CFormLabel>
              {loadingSubs ? (
                <div className="text-muted small">A carregar professores disponíveis…</div>
              ) : (
                <CFormSelect
                  id="substituteTeacher"
                  value={substituteTeacherId}
                  onChange={(e) => setSubstituteTeacherId(e.target.value)}
                >
                  <option value="">— Selecionar professor —</option>
                  {[...new Map(substitutes.map(s => [s.teacher_id, s])).values()].map(sub => (
                    <option key={sub.teacher_id} value={sub.teacher_id}>
                      {sub.teacher_name} ({sub.class_name})
                    </option>
                  ))}
                </CFormSelect>
              )}
            </div>
            <div className="mb-3">
              <CFormLabel htmlFor="substituteSubject">Disciplina dada pelo substituto</CFormLabel>
              <CFormSelect
                id="substituteSubject"
                value={substituteSubjectId}
                onChange={(e) => setSubstituteSubjectId(e.target.value)}
              >
                <option value="">— Selecionar disciplina (opcional) —</option>
                {uniqueSubjects.map(sub => (
                  <option key={sub.subject_id} value={sub.subject_id}>
                    {sub.subject_name}
                  </option>
                ))}
              </CFormSelect>
            </div>
          </>
        )}
      </CModalBody>
      <CModalFooter>
        <CButton color="secondary" variant="outline" onClick={onClose}>Cancelar</CButton>
        <CButton
          color="primary"
          onClick={handleSave}
          disabled={status === 'SUBSTITUTED' && !substituteTeacherId}
        >
          Guardar
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
    timeslot_id: PropTypes.number,
    substitute_teacher_id: PropTypes.number,
    substitute_subject_id: PropTypes.number,
  }).isRequired,
  onClose: PropTypes.func.isRequired,
  onSave: PropTypes.func.isRequired,
}

// ---------------------------------------------------------------------------
// Painel de Dívidas
// ---------------------------------------------------------------------------
const DebtsPanel = ({ classId }) => {
  const { data: debtData, isLoading, isError } = useDebts({ classId: classId || undefined })

  if (isLoading) return <div className="text-center p-4"><CSpinner /></div>
  if (isError) return <CAlert color="danger">Erro ao carregar dívidas.</CAlert>
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
const OccurrencesPanel = ({ classId, dateFrom, dateTo }) => {
  const [editingOccurrence, setEditingOccurrence] = useState(null)
  const { data: occurrences = [], isLoading, isError } = useOccurrences({
    classId: classId || undefined,
    dateFrom: dateFrom || undefined,
    dateTo: dateTo || undefined,
  })
  const updateMutation = useUpdateOccurrence()

  const handleSave = (payload) => {
    updateMutation.mutate(payload, {
      onSuccess: () => setEditingOccurrence(null),
    })
  }

  if (isLoading) return <div className="text-center p-4"><CSpinner /></div>
  if (isError) return <CAlert color="danger">Erro ao carregar ocorrências.</CAlert>
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
          onClose={() => setEditingOccurrence(null)}
          onSave={handleSave}
        />
      )}
      {updateMutation.isError && (
        <CAlert color="danger" className="mb-3">
          Erro ao guardar. Verifique se o professor substituto foi selecionado.
        </CAlert>
      )}
      <CTable hover responsive className="mb-0">
        <CTableHead color="light">
          <CTableRow>
            <CTableHeaderCell>Data</CTableHeaderCell>
            <CTableHeaderCell>Estado</CTableHeaderCell>
            <CTableHeaderCell className="text-center">Horas Dadas</CTableHeaderCell>
            <CTableHeaderCell>Substituto</CTableHeaderCell>
            <CTableHeaderCell />
          </CTableRow>
        </CTableHead>
        <CTableBody>
          {[...occurrences].sort((a, b) => b.date.localeCompare(a.date)).map(occ => (
            <CTableRow key={occ.id}>
              <CTableDataCell className="fw-semibold">{formatDate(occ.date)}</CTableDataCell>
              <CTableDataCell>
                <CBadge color={STATUS_COLORS[occ.status] ?? 'secondary'}>
                  <CIcon icon={STATUS_ICONS[occ.status] ?? cilClock} className="me-1" />
                  {STATUS_LABELS[occ.status] ?? occ.status}
                </CBadge>
              </CTableDataCell>
              <CTableDataCell className="text-center">{occ.hours_given}h</CTableDataCell>
              <CTableDataCell className="text-muted">
                {occ.substitute_teacher_id ? `Prof. ID ${occ.substitute_teacher_id}` : '—'}
              </CTableDataCell>
              <CTableDataCell className="text-end">
                <CButton
                  color="primary"
                  size="sm"
                  variant="outline"
                  onClick={() => setEditingOccurrence(occ)}
                >
                  Editar
                </CButton>
              </CTableDataCell>
            </CTableRow>
          ))}
        </CTableBody>
      </CTable>
    </>
  )
}

OccurrencesPanel.propTypes = {
  classId: PropTypes.oneOfType([PropTypes.number, PropTypes.string]),
  dateFrom: PropTypes.string,
  dateTo: PropTypes.string,
}

// ---------------------------------------------------------------------------
// Datas de filtro iniciais — calculadas uma vez no load do módulo
// ---------------------------------------------------------------------------
const INITIAL_DATE_TO = new Date().toISOString().split('T')[0]
const INITIAL_DATE_FROM = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000)
  .toISOString()
  .split('T')[0]

// ---------------------------------------------------------------------------
// Página principal
// ---------------------------------------------------------------------------
const Occurrences = () => {
  const [classFilter, setClassFilter] = useState('')
  const [dateFrom, setDateFrom] = useState(INITIAL_DATE_FROM)
  const [dateTo, setDateTo] = useState(INITIAL_DATE_TO)
  const [activeTab, setActiveTab] = useState('debts')

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
            Registe faltas, substituições e consulte dívidas de horas.
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
      <CTabs activeItemKey={activeTab} onActiveItemChange={(key) => setActiveTab(key)}>
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
