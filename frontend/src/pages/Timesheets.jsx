import React, { useState, useMemo } from 'react'
import {
  CCard, CCardBody, CAlert, CBadge, CSpinner, CButton,
  CTable, CTableHead, CTableRow, CTableHeaderCell, CTableBody, CTableDataCell,
  CFormSelect,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilCalendar, cilCheckCircle, cilActionUndo, cilArrowLeft, cilArrowRight } from '@coreui/icons'
import { useTimesheets, useUpdateTimesheetStatus } from '../hooks/useSchoolData'

const STATUS_LABELS = {
  OPEN: 'Aberta',
  SUBMITTED: 'Submetida',
  APPROVED: 'Aprovada',
}

const STATUS_COLORS = {
  OPEN: 'secondary',
  SUBMITTED: 'info',
  APPROVED: 'success',
}

const formatDate = (dateStr) => {
  if (!dateStr) return '—'
  const [year, month, day] = dateStr.split('-')
  return `${day}/${month}/${year}`
}

const formatDateTime = (dateTimeStr) => {
  if (!dateTimeStr) return '—'
  const dateValue = new Date(dateTimeStr)
  if (Number.isNaN(dateValue.getTime())) return dateTimeStr
  return dateValue.toLocaleString('pt-PT', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** Returns the ISO date string of the Monday for the given Date object (no mutation). */
function toWeekMonday(dateValue) {
  const d = new Date(dateValue.getTime())
  const dayOfWeek = d.getDay()
  const offset = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
  d.setDate(d.getDate() + offset)
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function addDays(dateStr, days) {
  const d = new Date(`${dateStr}T12:00:00`)
  d.setDate(d.getDate() + days)
  return d.toISOString().split('T')[0]
}

function formatWeekRange(weekStart) {
  const start = new Date(`${weekStart}T12:00:00`)
  const end = new Date(`${weekStart}T12:00:00`)
  end.setDate(end.getDate() + 4)
  const short = { day: '2-digit', month: 'short' }
  const full = { day: '2-digit', month: 'short', year: 'numeric' }
  return `${start.toLocaleDateString('pt-PT', short)} – ${end.toLocaleDateString('pt-PT', full)}`
}

const Timesheets = () => {
  const [statusFilter, setStatusFilter] = useState('SUBMITTED')
  const [weekFilter, setWeekFilter] = useState(() => toWeekMonday(new Date()))

  const { data: timesheets = [], isLoading, isError } = useTimesheets(
    weekFilter || undefined,
    statusFilter === 'ALL' ? undefined : statusFilter
  )

  const updateMutation = useUpdateTimesheetStatus()

  const handleUpdateStatus = async (timesheetId, status) => {
    try {
      await updateMutation.mutateAsync({ timesheetId, status })
    } catch (err) {
      alert(err.response?.data?.detail || 'Erro ao alterar estado.')
    }
  }

  const weekLabel = useMemo(() => formatWeekRange(weekFilter), [weekFilter])

  return (
    <div className="p-4">
      <div className="d-flex justify-content-between align-items-center mb-4">
        <div>
          <h2 className="mb-0 fw-bold text-dark">
            <CIcon icon={cilCalendar} className="me-2 text-primary" />
            Fecho Semanal (Aprovações)
          </h2>
          <small className="text-muted">
            Verifique e aprove as semanas letivas submetidas pelos professores.
          </small>
        </div>
      </div>

      <CCard className="border-0 shadow-sm mb-4">
        <CCardBody className="d-flex gap-3 align-items-end flex-wrap">
          {/* Status filter */}
          <div style={{ minWidth: '220px' }}>
            <label className="form-label text-muted small fw-semibold mb-1">Filtrar por Estado</label>
            <CFormSelect value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="ALL">Todos</option>
              <option value="OPEN">Em Aberto (Por submeter)</option>
              <option value="SUBMITTED">Pendentes de Aprovação (Submetidas)</option>
              <option value="APPROVED">Aprovadas</option>
            </CFormSelect>
          </div>

          {/* Week navigation — identical to /schedules */}
          <div className="ms-auto">
            <label className="form-label text-muted small fw-semibold mb-1 d-block">Semana</label>
            <div className="d-flex align-items-center gap-2">
              <CButton
                color="secondary"
                variant="outline"
                size="sm"
                onClick={() => setWeekFilter(prev => addDays(prev, -7))}
                title="Semana anterior"
              >
                <CIcon icon={cilArrowLeft} />
              </CButton>
              <span className="small fw-semibold" style={{ minWidth: '200px', textAlign: 'center' }}>
                {weekLabel}
              </span>
              <CButton
                color="secondary"
                variant="outline"
                size="sm"
                onClick={() => setWeekFilter(prev => addDays(prev, 7))}
                title="Próxima semana"
              >
                <CIcon icon={cilArrowRight} />
              </CButton>
              <CButton
                color="secondary"
                variant="outline"
                size="sm"
                onClick={() => setWeekFilter(toWeekMonday(new Date()))}
                title="Semana atual"
              >
                Hoje
              </CButton>
              <CButton
                color="secondary"
                variant="outline"
                size="sm"
                onClick={() => { setStatusFilter('ALL'); setWeekFilter(toWeekMonday(new Date())) }}
              >
                Limpar
              </CButton>
            </div>
          </div>
        </CCardBody>
      </CCard>

      {isLoading && (
        <div className="text-center p-4">
          <CSpinner />
        </div>
      )}

      {isError && (
        <CAlert color="danger">
          Erro ao carregar as aprovações semanais.
        </CAlert>
      )}

      {!isLoading && !isError && timesheets.length === 0 && (
        <CAlert color="info">
          Nenhuma semana encontrada com os filtros atuais.
        </CAlert>
      )}

      {!isLoading && !isError && timesheets.length > 0 && (
        <CCard className="border-0 shadow-sm">
          <CCardBody className="p-0">
            <CTable hover responsive className="mb-0">
              <CTableHead color="light">
                <CTableRow>
                  <CTableHeaderCell className="ps-4">Professor</CTableHeaderCell>
                  <CTableHeaderCell>Semana</CTableHeaderCell>
                  <CTableHeaderCell>Estado</CTableHeaderCell>
                  <CTableHeaderCell>Data Submissão</CTableHeaderCell>
                  <CTableHeaderCell className="text-end pe-4">Ação</CTableHeaderCell>
                </CTableRow>
              </CTableHead>
              <CTableBody>
                {timesheets.map((ts) => (
                  <CTableRow key={ts.id}>
                    <CTableDataCell className="fw-semibold ps-4">
                      {ts.teacher_name || `Prof. #${ts.teacher_id}`}
                    </CTableDataCell>
                    <CTableDataCell>
                      {formatDate(ts.week_start_date)} a {formatDate(ts.week_end_date)}
                    </CTableDataCell>
                    <CTableDataCell>
                      <CBadge color={STATUS_COLORS[ts.status]}>
                        {STATUS_LABELS[ts.status]}
                      </CBadge>
                    </CTableDataCell>
                    <CTableDataCell>
                      {ts.submitted_at ? formatDateTime(ts.submitted_at) : '—'}
                    </CTableDataCell>
                    <CTableDataCell className="text-end pe-4">
                      <div className="d-flex gap-2 justify-content-end align-items-center">
                        {ts.status === 'OPEN' && (
                          <span className="text-muted small fst-italic">
                            Aguardar submissão
                          </span>
                        )}
                        {ts.status === 'SUBMITTED' && (
                          <CButton
                            color="success"
                            size="sm"
                            className="text-white"
                            disabled={updateMutation.isPending}
                            onClick={() => handleUpdateStatus(ts.id, 'APPROVED')}
                          >
                            <CIcon icon={cilCheckCircle} className="me-1" />
                            Aprovar
                          </CButton>
                        )}
                        {(ts.status === 'APPROVED' || ts.status === 'SUBMITTED') && (
                          <CButton
                            color="warning"
                            size="sm"
                            disabled={updateMutation.isPending}
                            onClick={() => {
                              if (window.confirm('Tem a certeza que deseja reabrir esta semana? O professor poderá editar as aulas novamente.')) {
                                handleUpdateStatus(ts.id, 'OPEN')
                              }
                            }}
                          >
                            <CIcon icon={cilActionUndo} className="me-1" />
                            Reabrir
                          </CButton>
                        )}
                      </div>
                    </CTableDataCell>
                  </CTableRow>
                ))}
              </CTableBody>
            </CTable>
          </CCardBody>
        </CCard>
      )}
    </div>
  )
}

export default Timesheets
