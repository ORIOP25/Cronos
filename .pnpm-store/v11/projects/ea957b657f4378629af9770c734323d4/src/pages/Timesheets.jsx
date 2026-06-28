import React, { useState, useMemo, useEffect } from 'react'
import PageHeader from '../components/PageHeader'
import { useNavigate } from 'react-router-dom'
import {
  CCard, CCardBody, CAlert, CBadge, CSpinner, CButton,
  CFormSelect, CRow, CCol,
  CModal, CModalHeader, CModalTitle, CModalBody, CModalFooter,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import {
  cilCheckCircle, cilActionUndo, cilArrowLeft, cilArrowRight,
  cilPeople, cilExternalLink,
} from '@coreui/icons'
import {
  useTimesheets, useUpdateTimesheetStatus, useWeekSchedule,
  useTimeslots,
} from '../hooks/useSchoolData'
import WeekGrid from '../components/WeekGrid'
import LessonLogModal from '../components/LessonLogModal'
import TeacherCard from '../components/timesheets/TeacherCard'
import { formatWeekRange, addDays, toWeekMonday } from '../utils/formatUtils'
import { TXT } from '../utils/terminology'

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

const Timesheets = () => {
  const navigate = useNavigate()
  const [weekFilter, setWeekFilter] = useState(() => toWeekMonday(new Date()))
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [selectedTeacherId, setSelectedTeacherId] = useState(null)
  const [modalSlot, setModalSlot] = useState(null)
  const [statusActionError, setStatusActionError] = useState('')
  const [showReopenConfirm, setShowReopenConfirm] = useState(false)

  const statusParam = statusFilter === 'ALL' ? undefined : statusFilter
  const {
    data: timesheets = [],
    isLoading: loadingTimesheets,
    isError: timesheetsError,
  } = useTimesheets(weekFilter || undefined, statusParam)

  const { data: timeslots = [] } = useTimeslots()

  const {
    data: weekSlots = [],
    isLoading: loadingWeek,
  } = useWeekSchedule(null, selectedTeacherId, weekFilter)

  const updateMutation = useUpdateTimesheetStatus()

  // Auto-select first teacher when list loads or changes
  /* eslint-disable react-hooks/set-state-in-effect */
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
  /* eslint-enable react-hooks/set-state-in-effect */

  const selectedTeacher = useMemo(() => {
    return timesheets.find((t) => t.teacher_id === selectedTeacherId) || null
  }, [timesheets, selectedTeacherId])

  const handleUpdateStatus = async (timesheetId, status) => {
    setStatusActionError('')
    try {
      await updateMutation.mutateAsync({ timesheetId, status })
    } catch (err) {
      setStatusActionError(err.response?.data?.detail || 'Erro ao alterar estado. Tente novamente.')
    }
  }

  const handleApprove = () => {
    if (selectedTeacher && selectedTeacher.status === 'SUBMITTED') {
      handleUpdateStatus(selectedTeacher.id, 'APPROVED')
    }
  }

  const handleReopen = () => {
    if (selectedTeacher && (selectedTeacher.status === 'SUBMITTED' || selectedTeacher.status === 'APPROVED')) {
      setShowReopenConfirm(true)
    }
  }

  const handleConfirmReopen = () => {
    setShowReopenConfirm(false)
    if (selectedTeacher) {
      handleUpdateStatus(selectedTeacher.id, 'OPEN')
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
      <PageHeader preTitle="Operações" title={<span>Fecho <span className="text-editorial">Semanal</span></span>} />

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

      {statusActionError && (
        <CAlert color="danger" className="mb-4">
          {statusActionError}
        </CAlert>
      )}

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
              {selectedTeacher ? (
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

                    {/* Action buttons */}
                    <div className="d-flex gap-2 align-items-center">
                      {selectedTeacher.status === 'SUBMITTED' && (
                        <>
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
                          <CButton
                            color="warning"
                            size="sm"
                            className="text-white"
                            disabled={updateMutation.isPending}
                            onClick={handleReopen}
                            title="Reabrir a semana — o professor poderá editar novamente"
                          >
                            <CIcon icon={cilActionUndo} className="me-1" />
                            Reabrir
                          </CButton>
                        </>
                      )}

                      {selectedTeacher.status === 'APPROVED' && (
                        <CButton
                          color="warning"
                          size="sm"
                          className="text-white"
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

                      <CButton
                        color="primary"
                        variant="outline"
                        size="sm"
                        className="ms-auto"
                        onClick={handleNavigateToSchedules}
                        title="Ver horário deste professor em /schedules"
                      >
                        <CIcon icon={cilExternalLink} className="me-1" />
                        Ver em Horários
                      </CButton>
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
              ) : (
                <div className="text-center p-5 text-muted">
                  <CIcon icon={cilPeople} style={{ fontSize: '2rem', opacity: 0.35 }} />
                  <div className="mt-2">Selecione um professor da lista para ver o detalhe.</div>
                </div>
              )}
            </CCardBody>
          </CCard>
        </CCol>
      </CRow>

      {/* Confirmation modal for reopen */}
      <CModal visible={showReopenConfirm} onClose={() => setShowReopenConfirm(false)} alignment="center">
        <CModalHeader>
          <CModalTitle>Confirmar Reabertura</CModalTitle>
        </CModalHeader>
          <CModalBody>
          {TXT.WEEK_REOPEN_CONFIRM}
        </CModalBody>
        <CModalFooter>
          <CButton color="secondary" variant="outline" onClick={() => setShowReopenConfirm(false)}>
            {TXT.CANCEL}
          </CButton>
          <CButton
            color="warning"
            className="text-white"
            onClick={handleConfirmReopen}
            disabled={updateMutation.isPending}
          >
            {updateMutation.isPending && <CSpinner size="sm" className="me-1" />}
            Sim, reabrir
          </CButton>
        </CModalFooter>
      </CModal>

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
