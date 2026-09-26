import { useState, useMemo } from 'react'
import PageHeader from '../components/PageHeader'
import { useNavigate } from 'react-router-dom'
import {
  CCard, CCardBody, CAlert, CBadge, CSpinner, CButton,
  CFormSelect, CRow, CCol,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilCheckCircle, cilActionUndo, cilPeople, cilExternalLink } from '@coreui/icons'
import {
  useTimesheets, useUpdateTimesheetStatus,
} from '../features/operations/data'
import { useWeekSchedule } from '../features/scheduling/data'
import { useTimeslots, useWeekGridVersions } from '../features/catalog/data'
import WeekGrid from '../components/WeekGrid'
import LessonLogModal from '../components/LessonLogModal'
import TeacherCard from '../components/timesheets/TeacherCard'
import { formatWeekRange, toWeekMonday } from '../utils/formatUtils'
import { TXT } from '../utils/terminology'
import { getApiErrorMessage } from '../utils/apiErrors'
import ConfirmationModal from '../components/ConfirmationModal'
import { getTimesheetStatus } from '../utils/presentation'
import WeekNavigator from '../components/WeekNavigator'

const Timesheets = ({ initialWeekStart, readOnly = false, allowedActions, navigationDisabled = false, referenceDate } = {}) => {
  const navigate = useNavigate()
  const [weekFilter, setWeekFilter] = useState(() => initialWeekStart || toWeekMonday(new Date()))
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [requestedTeacherId, setRequestedTeacherId] = useState(null)
  const [modalSlot, setModalSlot] = useState(null)
  const [statusActionError, setStatusActionError] = useState('')
  const [showReopenConfirm, setShowReopenConfirm] = useState(false)
  const canManageWeek = !readOnly && !Array.isArray(allowedActions)

  const statusParam = statusFilter === 'ALL' ? undefined : statusFilter
  const {
    data: timesheets = [],
    isLoading: loadingTimesheets,
    isError: timesheetsError,
  } = useTimesheets(weekFilter || undefined, statusParam)
  const selectedTeacher = useMemo(
    () => timesheets.find((item) => item.teacher_id === requestedTeacherId)
      ?? timesheets[0]
      ?? null,
    [requestedTeacherId, timesheets],
  )
  const weekLabel = formatWeekRange(weekFilter)
  const selectedTeacherId = selectedTeacher?.teacher_id ?? null

  const { data: timeslots = [] } = useTimeslots()
  const { data: weekGridVersions } = useWeekGridVersions(weekFilter)

  const {
    data: weekSlots = [],
    isLoading: loadingWeek,
  } = useWeekSchedule(null, selectedTeacherId, weekFilter)

  const updateMutation = useUpdateTimesheetStatus()

  const handleUpdateStatus = async (timesheetId, status) => {
    if (!canManageWeek) return
    setStatusActionError('')
    try {
      await updateMutation.mutateAsync({ timesheetId, status })
    } catch (err) {
      setStatusActionError(getApiErrorMessage(err, 'Erro ao alterar estado. Tente novamente.'))
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


  return (
    <div className="p-4" data-tutorial-target="timesheets-workspace">
      {/* Header */}
      <PageHeader preTitle="Operações" title="Fecho Semanal" />

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
            <WeekNavigator value={weekFilter} onChange={setWeekFilter} />
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
                    onClick={() => setRequestedTeacherId(ts.teacher_id)}
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
                        <CBadge color={getTimesheetStatus(selectedTeacher.status).color}>
                          {getTimesheetStatus(selectedTeacher.status).label}
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
                      {canManageWeek && selectedTeacher.status === 'SUBMITTED' && (
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

                      {canManageWeek && selectedTeacher.status === 'APPROVED' && (
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

                      {!navigationDisabled && <CButton
                        color="primary"
                        variant="outline"
                        size="sm"
                        className="ms-auto"
                        onClick={handleNavigateToSchedules}
                        title="Ver horário deste professor em /schedules"
                      >
                        <CIcon icon={cilExternalLink} className="me-1" />
                        Ver em Horários
                      </CButton>}
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
                    dayGrids={weekGridVersions?.days ?? null}
                    gridTransitionDate={weekGridVersions?.transition_date ?? ''}
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

      <ConfirmationModal
        visible={showReopenConfirm}
        onClose={() => setShowReopenConfirm(false)}
        onConfirm={handleConfirmReopen}
        title="Confirmar Reabertura"
        message={TXT.WEEK_REOPEN_CONFIRM}
        confirmText="Sim, reabrir"
        isLoading={updateMutation.isPending}
        variant="warning"
      />

      {/* LessonLogModal for direct interaction */}
      {modalSlot && (
          <LessonLogModal
          key={modalSlot.operational_block_id ?? modalSlot.id}
          onClose={() => setModalSlot(null)}
          slot={modalSlot}
          isAdmin
          readOnly={readOnly}
          allowedActions={allowedActions}
          referenceDate={referenceDate}
        />
      )}
    </div>
  )
}

export default Timesheets
