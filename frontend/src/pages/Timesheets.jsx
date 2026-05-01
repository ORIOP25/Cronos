import React, { useState, useMemo, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  CCard, CCardBody, CAlert, CBadge, CSpinner, CButton,
  CFormSelect, CRow, CCol,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import {
  cilCalendar, cilCheckCircle, cilActionUndo, cilArrowLeft, cilArrowRight,
  cilPeople, cilExternalLink, cilCalendarCheck,
} from '@coreui/icons'
import {
  useTimesheets, useUpdateTimesheetStatus, useWeekSchedule,
  useTimeslots, useTeachers,
} from '../hooks/useSchoolData'
import WeekGrid from '../components/WeekGrid'
import LessonLogModal from '../components/LessonLogModal'

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

const STATUS_BG_COLORS = {
  OPEN: '#f8f9fa',
  SUBMITTED: '#fff3cd',
  APPROVED: '#d1e7dd',
}

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

const TeacherCard = ({ teacher, isSelected, onClick }) => {
  const color = STATUS_COLORS[teacher.status] || 'secondary'
  const bg = isSelected ? (STATUS_BG_COLORS[teacher.status] || '#e7f1ff') : '#fff'
  const registered = teacher.registered_slots ?? 0
  const total = teacher.total_slots ?? 0

  return (
    <button
      type="button"
      onClick={onClick}
      className="w-100 text-start border-0 mb-2 p-3 rounded"
      style={{
        backgroundColor: bg,
        borderLeft: `4px solid var(--cui-${color})`,
        cursor: 'pointer',
        transition: 'all 0.15s ease',
        boxShadow: isSelected ? '0 0 0 2px var(--cui-primary)' : '0 1px 3px rgba(0,0,0,0.08)',
      }}
    >
      <div className="d-flex justify-content-between align-items-center mb-1">
        <span className="fw-semibold" style={{ fontSize: '0.9rem' }}>
          {teacher.teacher_name || `Prof. #${teacher.teacher_id}`}
        </span>
        <CBadge color={color} style={{ fontSize: '0.7rem' }}>
          {STATUS_LABELS[teacher.status] || teacher.status}
        </CBadge>
      </div>
      <div className="text-muted" style={{ fontSize: '0.78rem' }}>
        {total > 0 ? (
          <>
            <strong>{registered}</strong>/{total} registadas
            {teacher.completed_slots > 0 && (
              <span className="ms-2 text-success">{teacher.completed_slots} dadas</span>
            )}
            {teacher.occurrence_slots > 0 && (
              <span className="ms-2 text-danger">{teacher.occurrence_slots} ocorrências</span>
            )}
          </>
        ) : (
          'Sem aulas nesta semana'
        )}
      </div>
    </button>
  )
}

const Timesheets = () => {
  const navigate = useNavigate()
  const [weekFilter, setWeekFilter] = useState(() => toWeekMonday(new Date()))
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [selectedTeacherId, setSelectedTeacherId] = useState(null)
  const [modalSlot, setModalSlot] = useState(null)

  const statusParam = statusFilter === 'ALL' ? undefined : statusFilter
  const {
    data: timesheets = [],
    isLoading: loadingTimesheets,
    isError: timesheetsError,
  } = useTimesheets(weekFilter || undefined, statusParam)

  const { data: teachers = [] } = useTeachers()
  const { data: timeslots = [] } = useTimeslots()

  const {
    data: weekSlots = [],
    isLoading: loadingWeek,
  } = useWeekSchedule(null, selectedTeacherId, weekFilter)

  const updateMutation = useUpdateTimesheetStatus()

  // Auto-select first teacher when list loads or changes
  useEffect(() => {
    if (timesheets.length > 0 && !selectedTeacherId) {
      setSelectedTeacherId(timesheets[0].teacher_id)
    }
    if (timesheets.length > 0 && selectedTeacherId) {
      const stillExists = timesheets.some((t) => t.teacher_id === selectedTeacherId)
      if (!stillExists) {
        setSelectedTeacherId(timesheets[0].teacher_id)
      }
    }
    if (timesheets.length === 0) {
      setSelectedTeacherId(null)
    }
  }, [timesheets, selectedTeacherId])

  const selectedTeacher = useMemo(() => {
    return timesheets.find((t) => t.teacher_id === selectedTeacherId) || null
  }, [timesheets, selectedTeacherId])

  const handleUpdateStatus = async (timesheetId, status) => {
    try {
      await updateMutation.mutateAsync({ timesheetId, status })
    } catch (err) {
      alert(err.response?.data?.detail || 'Erro ao alterar estado.')
    }
  }

  const handleApprove = () => {
    if (selectedTeacher && selectedTeacher.status === 'SUBMITTED') {
      handleUpdateStatus(selectedTeacher.id, 'APPROVED')
    }
  }

  const handleReopen = () => {
    if (selectedTeacher && (selectedTeacher.status === 'SUBMITTED' || selectedTeacher.status === 'APPROVED')) {
      if (window.confirm('Tem a certeza que deseja reabrir esta semana? O professor poderá editar as aulas novamente.')) {
        handleUpdateStatus(selectedTeacher.id, 'OPEN')
      }
    }
  }

  const handleOpenSlot = (slot) => {
    setModalSlot(slot)
  }

  const handleNavigateToSchedules = () => {
    if (!selectedTeacherId || !weekFilter) return
    navigate(`/schedules?teacherId=${selectedTeacherId}&weekStart=${weekFilter}`)
  }

  const weekLabel = useMemo(() => formatWeekRange(weekFilter), [weekFilter])

  return (
    <div className="p-4">
      {/* Header */}
      <div className="d-flex justify-content-between align-items-start mb-4 flex-wrap gap-3">
        <div>
          <h2 className="mb-0 fw-bold text-dark">
            <CIcon icon={cilCalendarCheck} className="me-2 text-primary" />
            Fecho Semanal (Aprovações)
          </h2>
          <small className="text-muted">
            Selecione um professor para rever o horário e aprovar ou reabrir a semana.
          </small>
        </div>
      </div>

      {/* Filters */}
      <CCard className="border-0 shadow-sm mb-4">
        <CCardBody className="d-flex gap-3 align-items-end flex-wrap">
          <div style={{ minWidth: '220px' }}>
            <label className="form-label text-muted small fw-semibold mb-1">Filtrar por Estado</label>
            <CFormSelect value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="ALL">Todos</option>
              <option value="OPEN">Em Aberto</option>
              <option value="SUBMITTED">Pendentes de Aprovação</option>
              <option value="APPROVED">Aprovadas</option>
            </CFormSelect>
          </div>

          <div className="ms-auto">
            <label className="form-label text-muted small fw-semibold mb-1 d-block">Semana</label>
            <div className="d-flex align-items-center gap-2">
              <CButton
                color="secondary"
                variant="outline"
                size="sm"
                onClick={() => setWeekFilter((prev) => addDays(prev, -7))}
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
                onClick={() => setWeekFilter((prev) => addDays(prev, 7))}
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
            </div>
          </div>
        </CCardBody>
      </CCard>

      {timesheetsError && (
        <CAlert color="danger" className="mb-4">
          Erro ao carregar as aprovações semanais.
        </CAlert>
      )}

      {/* Two-panel layout */}
      <CRow className="g-4">
        {/* Left panel — teacher list */}
        <CCol md={4} lg={3}>
          <CCard className="border-0 shadow-sm h-100">
            <CCardBody className="p-3">
              <div className="d-flex align-items-center gap-2 mb-3">
                <CIcon icon={cilPeople} className="text-primary" />
                <span className="fw-semibold">Professores</span>
                <CBadge color="light" className="ms-auto text-dark">
                  {timesheets.length}
                </CBadge>
              </div>

              {loadingTimesheets && (
                <div className="text-center p-3">
                  <CSpinner size="sm" />
                </div>
              )}

              {!loadingTimesheets && timesheets.length === 0 && (
                <CAlert color="info" className="small py-2">
                  Nenhum professor com timesheet nesta semana.
                </CAlert>
              )}

              <div style={{ maxHeight: '70vh', overflowY: 'auto' }}>
                {timesheets.map((ts) => (
                  <TeacherCard
                    key={ts.teacher_id}
                    teacher={ts}
                    isSelected={ts.teacher_id === selectedTeacherId}
                    onClick={() => setSelectedTeacherId(ts.teacher_id)}
                  />
                ))}
              </div>
            </CCardBody>
          </CCard>
        </CCol>

        {/* Right panel — detail */}
        <CCol md={8} lg={9}>
          <CCard className="border-0 shadow-sm h-100">
            <CCardBody className="p-3">
              {!selectedTeacher ? (
                <div className="text-center p-5 text-muted">
                  <CIcon icon={cilPeople} style={{ fontSize: '2rem', opacity: 0.35 }} />
                  <div className="mt-2">Selecione um professor da lista para ver o detalhe.</div>
                </div>
              ) : (
                <>
                  {/* Teacher header */}
                  <div className="d-flex justify-content-between align-items-start flex-wrap gap-3 mb-3">
                    <div>
                      <h4 className="mb-1 fw-bold">
                        {selectedTeacher.teacher_name || `Prof. #${selectedTeacher.teacher_id}`}
                      </h4>
                      <div className="text-muted small">
                        Semana de {weekLabel} ·{' '}
                        <CBadge color={STATUS_COLORS[selectedTeacher.status]}>
                          {STATUS_LABELS[selectedTeacher.status]}
                        </CBadge>
                        {selectedTeacher.submitted_at && (
                          <span className="ms-2">
                            Submetida em {new Date(selectedTeacher.submitted_at).toLocaleString('pt-PT')}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Action buttons (7.2) */}
                    <div className="d-flex gap-2 align-items-center">
                      <CButton
                        color="primary"
                        variant="outline"
                        size="sm"
                        onClick={handleNavigateToSchedules}
                        title="Ver horário deste professor em /schedules"
                      >
                        <CIcon icon={cilExternalLink} className="me-1" />
                        Ver em Horários
                      </CButton>

                      {selectedTeacher.status === 'SUBMITTED' && (
                        <CButton
                          color="success"
                          size="sm"
                          className="text-white"
                          disabled={updateMutation.isPending}
                          onClick={handleApprove}
                        >
                          <CIcon icon={cilCheckCircle} className="me-1" />
                          Aprovar
                        </CButton>
                      )}

                      {(selectedTeacher.status === 'SUBMITTED' || selectedTeacher.status === 'APPROVED') && (
                        <CButton
                          color="warning"
                          size="sm"
                          disabled={updateMutation.isPending}
                          onClick={handleReopen}
                        >
                          <CIcon icon={cilActionUndo} className="me-1" />
                          Reabrir
                        </CButton>
                      )}

                      {selectedTeacher.status === 'OPEN' && (
                        <span className="text-muted small fst-italic">
                          Aguardar submissão do professor
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Slot counts summary */}
                  {selectedTeacher.total_slots > 0 && (
                    <div className="d-flex gap-3 mb-3 flex-wrap">
                      <div className="small">
                        <strong>{selectedTeacher.registered_slots}</strong>/{selectedTeacher.total_slots} registadas
                      </div>
                      <div className="small text-success">
                        <strong>{selectedTeacher.completed_slots}</strong> aulas dadas
                      </div>
                      <div className="small text-danger">
                        <strong>{selectedTeacher.occurrence_slots}</strong> ocorrências
                      </div>
                      <div className="small text-muted">
                        <strong>{selectedTeacher.total_slots - selectedTeacher.registered_slots}</strong> pendentes
                      </div>
                    </div>
                  )}

                  {/* WeekGrid */}
                  <WeekGrid
                    slots={weekSlots}
                    isLoading={loadingWeek}
                    baseTimeslots={timeslots}
                    weekStart={weekFilter}
                    isOperationalEnabled
                    onOpenOperationalAction={handleOpenSlot}
                  />
                </>
              )}
            </CCardBody>
          </CCard>
        </CCol>
      </CRow>

      {/* LessonLogModal for direct interaction */}
      <LessonLogModal
        visible={Boolean(modalSlot)}
        onClose={() => setModalSlot(null)}
        slot={modalSlot}
        isAdmin
      />
    </div>
  )
}

export default Timesheets
