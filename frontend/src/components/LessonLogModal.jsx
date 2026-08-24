import { useState } from 'react'
import {
  CModal,
  CModalHeader,
  CModalTitle,
  CModalBody,
  CModalFooter,
  CButton,
  CFormTextarea,
  CAlert,
  CBadge,
  CSpinner,
} from '@coreui/react'
import CIcon from '@coreui/icons-react'
import { cilCheckCircle, cilXCircle, cilActionUndo, cilWarning } from '@coreui/icons'
import { useUpsertLessonLog, useUpdateTimesheetStatus } from '../features/operations/data'
import { getApiErrorMessage } from '../utils/apiErrors'
import { formatDateLong } from '../utils/formatUtils'
import { getLessonLogStatus } from '../utils/presentation'

const OCCURRENCE_STATUS_LABELS = {
  GIVEN:       'Dada ✓',
  GAP:         'Furo ✗',
  SUBSTITUTED: 'Substituída ↔',
  REVOKED:     'Revertida',
}

/**
 * LessonLogModal — V4 simplified registration modal.
 * PENDING  → 3 buttons: Cancelar, Criar Ocorrência (c/ confirmação), Aula Dada
 * COMPLETED → editable if week OPEN, readonly if locked
 * OCCURRENCE → readonly (always)
 */
const LessonLogModal = ({ onClose, slot, isAdmin = false }) => {
  const [summary, setSummary] = useState(() => slot.lesson_log_summary || '')
  const [notes, setNotes] = useState(() => slot.lesson_log_notes || '')
  const [errorMessage, setErrorMessage] = useState('')
  const [showReopenConfirm, setShowReopenConfirm] = useState(false)
  const [showOccurrenceConfirm, setShowOccurrenceConfirm] = useState(false)

  const upsertLogMutation = useUpsertLessonLog()
  const updateTimesheetStatusMutation = useUpdateTimesheetStatus()

  const MAX_SUMMARY_LENGTH = 2000
  const MAX_NOTES_LENGTH = 1000

  const handleSubmit = async (status) => {
    setErrorMessage('')
    try {
      await upsertLogMutation.mutateAsync({
        activeScheduleBlockId: slot.active_schedule_block_id,
        operationalBlockId: slot.operational_block_id,
        payload: { status, summary, notes },
      })
      onClose()
    } catch (err) {
      setErrorMessage(getApiErrorMessage(err, 'Erro ao guardar o registo. Tente novamente.'))
    }
  }

  const handleReopenWeek = async () => {
    setErrorMessage('')
    if (!slot.timesheet_id) {
      setErrorMessage('Não foi possível identificar a timesheet desta semana.')
      return
    }
    setShowReopenConfirm(true)
  }

  const handleConfirmReopen = async () => {
    setShowReopenConfirm(false)
    try {
      await updateTimesheetStatusMutation.mutateAsync({
        timesheetId: slot.timesheet_id,
        status: 'OPEN',
      })
      onClose()
    } catch (err) {
      setErrorMessage(getApiErrorMessage(err, 'Não foi possível reabrir a semana. Tente novamente.'))
    }
  }

  if (!slot) return null

  const currentStatus = slot.lesson_log_status || 'PENDING'
  const isCompleted = currentStatus === 'COMPLETED'
  const isOccurrence = currentStatus === 'OCCURRENCE'
  const isPending = currentStatus === 'PENDING'

  const hasActiveOccurrence = Boolean(slot.occurrence_id) && slot.occurrence_status !== 'REVOKED'
  const isOperationalBlock = slot.block_source === 'operational' || Boolean(slot.operational_block_id)
  const occurrenceDecided = Boolean(slot.occurrence_decided_at)
  const occurrenceStatusLabel = OCCURRENCE_STATUS_LABELS[slot.occurrence_status] ?? slot.occurrence_status

  let isFuture = false
  if (slot.date && slot.timeslot?.end_time) {
    const endDateTime = new Date(`${slot.date}T${slot.timeslot.end_time}`)
    isFuture = endDateTime > new Date()
  } else {
    isFuture = !slot.is_past
  }

  const isWeekLocked = slot.week_timesheet_status === 'SUBMITTED' || slot.week_timesheet_status === 'APPROVED'
  const canEdit = isCompleted && !isWeekLocked

  const statusInfo = getLessonLogStatus(currentStatus)

  return (
    <CModal visible onClose={onClose} alignment="center" data-tutorial-target="lesson-log-modal">
      <CModalHeader>
        <CModalTitle>
          Registo de Aula{' '}
          <CBadge
            color={statusInfo.badge}
            className="ms-2"
            style={{ fontSize: '0.7rem', verticalAlign: 'middle' }}
          >
            {statusInfo.label}
          </CBadge>
        </CModalTitle>
      </CModalHeader>

      <CModalBody>
        {/* Slot metadata */}
        <div
          className="mb-3 rounded px-3 py-2"
          style={{ backgroundColor: 'var(--color-bg-muted)', fontSize: '0.85rem' }}
        >
          <div><strong>Data:</strong> {formatDateLong(slot.date)}</div>
          <div><strong>Horário:</strong> {slot.timeslot ? `${slot.timeslot.start_time} – ${slot.timeslot.end_time}` : '—'}</div>
          <div><strong>Disciplina:</strong> {slot.subject?.name ?? '—'}</div>
          <div><strong>Turma:</strong> {slot.class_info?.name ?? '—'}</div>
          {isAdmin && <div><strong>Docente:</strong> {slot.teacher?.name ?? '—'}</div>}
          {slot.room && <div><strong>Sala:</strong> {slot.room?.name}</div>}
        </div>

        {/* Informative banner for occurrences */}
        {hasActiveOccurrence && !occurrenceDecided && (
          <CAlert color="warning" className="mb-3 small py-2">
            <CIcon icon={cilWarning} className="me-1" />
            Ocorrência registada. Geria em Faltas &amp; Ocorrências.
          </CAlert>
        )}
        {hasActiveOccurrence && occurrenceDecided && (
          <CAlert color="secondary" className="mb-3 small py-2">
            <CIcon icon={cilWarning} className="me-1" />
            Ocorrência decidida: {occurrenceStatusLabel}. Consulte Faltas &amp; Ocorrências.
          </CAlert>
        )}

        {/* OCCURRENCE read-only banner */}
        {isOccurrence && !hasActiveOccurrence && (
          <CAlert color="warning" className="mb-3 small py-2">
            <CIcon icon={cilWarning} className="me-1" />
            Esta aula tem uma ocorrência registada. Contacte um administrador para reverter.
          </CAlert>
        )}

        {errorMessage && (
          <CAlert color="danger" className="mb-3">
            {errorMessage}
          </CAlert>
        )}

        {isFuture && isPending && (
          <CAlert color="info" className="mb-3 small">
            Esta aula ainda não terminou. Pode preencher o sumário e criar ocorrência antecipadamente.
          </CAlert>
        )}

        {/* Locked week — read-only mode */}
        {!isFuture && isWeekLocked && (
          <CAlert color="secondary" className="mb-3 d-flex align-items-center justify-content-between flex-wrap gap-2">
            <span>
              <strong>Semana {slot.week_timesheet_status === 'SUBMITTED' ? 'submetida' : 'aprovada'}</strong>
              {' — Modo de consulta.'}
              {!isAdmin && ' Os campos estão bloqueados para edição.'}
            </span>
            {isAdmin && (
              <CButton
                color="warning"
                size="sm"
                className="text-white"
                onClick={handleReopenWeek}
                disabled={updateTimesheetStatusMutation.isPending}
              >
                {updateTimesheetStatusMutation.isPending && <CSpinner size="sm" className="me-1" />}
                <CIcon icon={cilActionUndo} className="me-1" />
                Reabrir Semana
              </CButton>
            )}
          </CAlert>
        )}

        {/* COMPLETED editable banner */}
        {canEdit && (
          <CAlert color="success" className="mb-3 small py-2">
            <CIcon icon={cilCheckCircle} className="me-1" />
            Aula registada. Pode editar o sumário e notas.
          </CAlert>
        )}

        {/* COMPLETED read-only banner (locked week) */}
        {isCompleted && isWeekLocked && (
          <CAlert color="success" className="mb-3 small py-2">
            <CIcon icon={cilCheckCircle} className="me-1" />
            Aula registada. Semana {slot.week_timesheet_status === 'SUBMITTED' ? 'submetida' : 'aprovada'} — modo de consulta.
          </CAlert>
        )}

        {/* OCCURRENCE read-only banner */}
        {isOccurrence && (
          <CAlert color="warning" className="mb-3 small py-2">
            <CIcon icon={cilXCircle} className="me-1" />
            Ocorrência registada. Não é possível alterar. Contacte um administrador para reverter em Faltas &amp; Ocorrências.
          </CAlert>
        )}

        {/* Lesson log form */}
        <div className="mb-3">
          <label htmlFor="lessonSummary" className="form-label fw-semibold">Sumário</label>
          <CFormTextarea
            id="lessonSummary"
            rows={3}
            placeholder="Sumário descritivo da aula..."
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            disabled={!canEdit && !isPending}
            maxLength={MAX_SUMMARY_LENGTH}
          />
          <div className="text-muted text-end small mt-1" style={{ fontSize: '0.7rem' }}>
            {summary.length}/{MAX_SUMMARY_LENGTH}
          </div>
        </div>
        <div className="mb-3">
          <label htmlFor="lessonNotes" className="form-label fw-semibold">Notas Opcionais</label>
          <CFormTextarea
            id="lessonNotes"
            rows={2}
            placeholder="Anotações para uso interno ou partilha com direção..."
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            disabled={!canEdit && !isPending}
            maxLength={MAX_NOTES_LENGTH}
          />
          <div className="text-muted text-end small mt-1" style={{ fontSize: '0.7rem' }}>
            {notes.length}/{MAX_NOTES_LENGTH}
          </div>
        </div>
      </CModalBody>

      {showReopenConfirm && (
        <CAlert color="warning" className="mx-3 mb-0 d-flex align-items-center justify-content-between flex-wrap gap-2">
          <span>
            <strong>Reabrir semana?</strong>{' '}
            O professor poderá editar as aulas novamente.
          </span>
          <div className="d-flex gap-2">
            <CButton color="secondary" variant="outline" size="sm" onClick={() => setShowReopenConfirm(false)}>
              Cancelar
            </CButton>
            <CButton
              color="warning" size="sm" className="text-white"
              onClick={handleConfirmReopen}
              disabled={updateTimesheetStatusMutation.isPending}
            >
              {updateTimesheetStatusMutation.isPending && <CSpinner size="sm" className="me-1" />}
              Sim, reabrir
            </CButton>
          </div>
        </CAlert>
      )}

      {showOccurrenceConfirm && (
        <CAlert color="warning" className="mx-3 mb-0 d-flex align-items-center justify-content-between flex-wrap gap-2">
          <span>
            <strong>Criar ocorrência?</strong>{' '}
            Esta ação irá gerar uma ocorrência que requer intervenção administrativa. Tem a certeza?
          </span>
          <div className="d-flex gap-2">
            <CButton color="secondary" variant="outline" size="sm" onClick={() => setShowOccurrenceConfirm(false)}>
              Cancelar
            </CButton>
            <CButton
              color="warning" size="sm" className="text-white"
              onClick={() => { setShowOccurrenceConfirm(false); handleSubmit('OCCURRENCE') }}
              disabled={upsertLogMutation.isPending}
            >
              {upsertLogMutation.isPending && <CSpinner size="sm" className="me-1" />}
              Sim, criar ocorrência
            </CButton>
          </div>
        </CAlert>
      )}

      <CModalFooter>
        <div className="d-flex gap-2">
          <CButton color="secondary" variant="outline" onClick={onClose}>
            Cancelar
          </CButton>
        </div>

        <div className="d-flex gap-2">
          {upsertLogMutation.isPending && <CSpinner size="sm" className="align-self-center" />}

          {/* PENDING — 3 buttons */}
          {isPending && (
            <>
              <CButton
                style={{ backgroundColor: 'var(--color-state-gap)', borderColor: 'var(--color-state-gap)', color: '#fff' }}
                onClick={() => setShowOccurrenceConfirm(true)}
                disabled={isOperationalBlock || isWeekLocked || upsertLogMutation.isPending}
                title="Criar ocorrência para este bloco"
              >
                <CIcon icon={cilXCircle} className="me-1" />
                Criar Ocorrência
              </CButton>

              <CButton
                style={{ backgroundColor: 'var(--color-state-given)', borderColor: 'var(--color-state-given)', color: '#fff' }}
                onClick={() => handleSubmit('COMPLETED')}
                disabled={isFuture || isWeekLocked || upsertLogMutation.isPending}
                title="Marcar aula como dada"
              >
                <CIcon icon={cilCheckCircle} className="me-1" />
                Aula Dada
              </CButton>
            </>
          )}

          {/* COMPLETED + OPEN — Guardar alterações */}
          {canEdit && (
            <CButton
              color="primary"
              onClick={() => handleSubmit('COMPLETED')}
              disabled={upsertLogMutation.isPending}
              title="Guardar alterações ao sumário e notas"
            >
              <CIcon icon={cilCheckCircle} className="me-1" />
              Guardar alterações
            </CButton>
          )}
        </div>
      </CModalFooter>
    </CModal>
  )
}

export default LessonLogModal
